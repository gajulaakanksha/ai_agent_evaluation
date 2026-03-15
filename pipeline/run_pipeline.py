"""
Part 3 — The Architect
Prompt iteration pipeline.

Usage:
    python pipeline/run_pipeline.py --prompt system-prompt.md --transcripts transcripts/
    python pipeline/run_pipeline.py --prompt system-prompt-fixed.md --transcripts transcripts/
    python pipeline/run_pipeline.py --prompt system-prompt.md --prompt system-prompt-fixed.md --transcripts transcripts/

Compares prompts if multiple are given.
"""

import json
import os
import sys
import argparse
import re
import time
from pathlib import Path
from datetime import datetime

# Add parent dir to path so we can import the evaluator
sys.path.insert(0, str(Path(__file__).parent.parent))
from detective.evaluate import load_transcript, score_call
from llm_utils import get_backend, call_llm, call_llm_with_system

# ── Prompt template filling ──────────────────────────────────────────────────

def fill_prompt_template(prompt_text: str, transcript: dict) -> str:
    customer = transcript.get("customer", {})
    replacements = {
        "{{customer_name}}": customer.get("name", "Borrower"),
        "{{pending_amount}}": customer.get("pending_amount", "unknown"),
        "{{due_date}}": "overdue",
        "{{today_date}}": "March 15, 2026",
        "{{today_day}}": "Sunday",
        "{{pos}}": customer.get("closure_amount", customer.get("pending_amount", "unknown")),
        "{{tos}}": customer.get("pending_amount", "unknown"),
        "{{dpd}}": customer.get("dpd", "180"),
        "{{loan_id}}": "DEMO-LOAN-001",
        "{{settlement_amount}}": customer.get("settlement_amount", "unknown"),
    }
    result = prompt_text
    for k, v in replacements.items():
        result = result.replace(k, str(v))
    return result


# ── Simulate a conversation ──────────────────────────────────────────────────

def simulate_conversation(transcript: dict, prompt_text: str,
                           backend, client, max_turns=10) -> list[dict]:
    """Run borrower messages through the LLM using the given prompt."""
    system_prompt = fill_prompt_template(prompt_text, transcript)

    borrower_turns = [t for t in transcript.get("transcript", [])
                      if t["speaker"] == "customer"][:max_turns]

    simulated_turns = []
    history = []

    for bt in borrower_turns:
        history.append({"role": "user", "content": bt["text"]})
        agent_response = call_llm_with_system(backend, client, system_prompt,
                                               history, max_tokens=300)
        if agent_response:
            history.append({"role": "assistant", "content": agent_response})
            simulated_turns.append({"speaker": "agent", "text": agent_response})
        simulated_turns.append({"speaker": "customer", "text": bt["text"]})

    return simulated_turns


# ── Score a simulated conversation ──────────────────────────────────────────

def score_simulated(original_transcript: dict, simulated_turns: list[dict]) -> dict:
    """Build a synthetic transcript dict and score it."""
    synthetic = dict(original_transcript)
    synthetic["transcript"] = simulated_turns
    # Keep function_calls empty for simulated (agent didn't call functions)
    synthetic["function_calls"] = []
    return score_call(synthetic, use_llm=False)


# ── Run pipeline for one prompt ──────────────────────────────────────────────

def run_prompt(prompt_path: str, transcript_paths: list[str],
               backend, client, use_simulation: bool) -> dict:
    prompt_text = Path(prompt_path).read_text(encoding="utf-8")
    prompt_name = Path(prompt_path).name

    results = []
    for tp in transcript_paths:
        transcript = load_transcript(tp)

        if use_simulation and backend:
            simulated = simulate_conversation(transcript, prompt_text, backend, client)
            score_result = score_simulated(transcript, simulated)
            score_result["simulated"] = True
        else:
            score_result = score_call(transcript, use_llm=False)
            score_result["simulated"] = False

        score_result["prompt"] = prompt_name
        results.append(score_result)

    scores = [r["score"] for r in results]
    good_count = sum(1 for r in results if r["verdict"] == "good")

    return {
        "prompt": prompt_name,
        "prompt_path": prompt_path,
        "results": results,
        "aggregate": {
            "mean_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "good_count": good_count,
            "bad_count": len(results) - good_count,
            "total_calls": len(results),
            "good_rate": round(good_count / len(results) * 100, 1) if results else 0,
        }
    }


# ── Suggest improvements (bonus) ────────────────────────────────────────────

IMPROVEMENT_PROMPT = """You are an expert prompt engineer for AI debt collection agents.

You have been given:
1. A system prompt used by the agent
2. Scoring results showing which calls failed and why

Your task: Identify 3 specific, actionable improvements to the system prompt that would
address the most common failure modes. Be concrete — quote the exact section to change
and what to change it to.

Format your response as JSON:
{
  "improvements": [
    {
      "issue": "what is wrong",
      "location": "which section of the prompt",
      "current_text": "the problematic text (first 100 chars)",
      "suggested_fix": "what to replace it with or add"
    }
  ]
}

SYSTEM PROMPT (first 3000 chars):
{{PROMPT}}

FAILURE SUMMARY:
{{FAILURES}}
"""


def suggest_improvements(prompt_text: str, results: list[dict],
                          backend, client) -> dict:
    if not backend:
        return {"improvements": [], "note": "No LLM available for suggestions"}

    failures = []
    for r in results:
        if r["verdict"] == "bad":
            flags = r.get("penalty_flags", [])
            worst = [m.get("category", "") for m in r.get("worst_messages", [])]
            failures.append(f"- {r['call_id']}: score={r['score']}, flags={flags}, issues={worst}")

    failure_text = "\n".join(failures) if failures else "No failures detected"
    prompt = IMPROVEMENT_PROMPT.replace("{{PROMPT}}", prompt_text[:3000])
    prompt = prompt.replace("{{FAILURES}}", failure_text)

    raw = call_llm(backend, client, prompt, max_tokens=1024)

    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass

    return {"improvements": [], "raw": raw[:500]}


# ── Report generation ────────────────────────────────────────────────────────

def generate_report(prompt_runs: list[dict], suggest: dict = None) -> str:
    lines = []
    lines.append("# Pipeline Report")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    for run in prompt_runs:
        agg = run["aggregate"]
        lines.append(f"## Prompt: {run['prompt']}")
        lines.append(f"- Mean score: {agg['mean_score']}/100")
        lines.append(f"- Good/Bad: {agg['good_count']}/{agg['bad_count']} ({agg['good_rate']}% good)")
        lines.append(f"- Score range: {agg['min_score']} – {agg['max_score']}\n")

        lines.append("| Call | Score | Verdict | Key Issues |")
        lines.append("|------|-------|---------|------------|")
        for r in run["results"]:
            flags = "; ".join(r.get("penalty_flags", []))[:60]
            lines.append(f"| {r['call_id']} | {r['score']} | {r['verdict']} | {flags} |")
        lines.append("")

    # Comparison if multiple prompts
    if len(prompt_runs) > 1:
        lines.append("## Prompt Comparison")
        lines.append("| Prompt | Mean Score | Good Rate |")
        lines.append("|--------|-----------|-----------|")
        for run in prompt_runs:
            agg = run["aggregate"]
            lines.append(f"| {run['prompt']} | {agg['mean_score']} | {agg['good_rate']}% |")

        # Winner
        best_score = max(r["aggregate"]["mean_score"] for r in prompt_runs)
        winners = [r for r in prompt_runs if r["aggregate"]["mean_score"] == best_score]
        if len(winners) > 1:
            lines.append(f"\n**Result: Tie** — all prompts scored {best_score}. Use `--simulate` with an API key for a meaningful comparison.")
        else:
            lines.append(f"\n**Winner: {winners[0]['prompt']}** (mean score: {best_score})")
        lines.append("")

    # Suggestions
    if suggest and suggest.get("improvements"):
        lines.append("## Suggested Prompt Improvements (Auto-generated)")
        for i, imp in enumerate(suggest["improvements"], 1):
            lines.append(f"\n### {i}. {imp.get('issue', 'Issue')}")
            lines.append(f"- Location: {imp.get('location', 'unknown')}")
            lines.append(f"- Current: `{imp.get('current_text', '')[:100]}`")
            lines.append(f"- Fix: {imp.get('suggested_fix', '')}")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Prompt iteration pipeline")
    parser.add_argument("--prompt", nargs="+", required=True,
                        help="System prompt file(s) to evaluate")
    parser.add_argument("--transcripts", default="transcripts",
                        help="Folder of transcript JSON files")
    parser.add_argument("--simulate", action="store_true",
                        help="Simulate conversations with the prompt (uses LLM, costs money)")
    parser.add_argument("--suggest", action="store_true",
                        help="Auto-suggest prompt improvements (bonus feature)")
    parser.add_argument("--output", default="results/pipeline_report.md",
                        help="Output report file")
    parser.add_argument("--scores-output", default="results/pipeline_scores.json",
                        help="Output scores JSON file")
    parser.add_argument("--gemini-key", help="Gemini API key (overrides GEMINI_API_KEY env var)")
    args = parser.parse_args()

    folder = Path(args.transcripts)
    transcript_paths = sorted([str(p) for p in folder.glob("call_*.json")])
    if not transcript_paths:
        print(f"No transcripts found in {folder}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(transcript_paths)} transcripts", file=sys.stderr)

    backend, client = get_backend(args.gemini_key)
    if args.simulate and not backend:
        print("WARNING: --simulate requires an API key. Set GEMINI_API_KEY in .env or pass --gemini-key.",
              file=sys.stderr)
        args.simulate = False

    prompt_runs = []
    for prompt_path in args.prompt:
        if not Path(prompt_path).exists():
            print(f"Prompt file not found: {prompt_path}", file=sys.stderr)
            continue
        print(f"\nEvaluating prompt: {prompt_path}", file=sys.stderr)
        run = run_prompt(prompt_path, transcript_paths, backend, client, args.simulate)
        prompt_runs.append(run)
        agg = run["aggregate"]
        print(f"  Mean score: {agg['mean_score']} | Good: {agg['good_count']}/{agg['total_calls']}",
              file=sys.stderr)

    if not prompt_runs:
        print("No prompts evaluated.", file=sys.stderr)
        sys.exit(1)

    suggestions = None
    if args.suggest and backend:
        print("\nGenerating improvement suggestions...", file=sys.stderr)
        prompt_text = Path(prompt_runs[0]["prompt_path"]).read_text(encoding="utf-8")
        suggestions = suggest_improvements(prompt_text, prompt_runs[0]["results"], backend, client)

    # Generate report
    report = generate_report(prompt_runs, suggestions)
    print("\n" + report)

    # Save outputs
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    scores_path = Path(args.scores_output)
    with open(scores_path, "w", encoding="utf-8") as f:
        json.dump(prompt_runs, f, indent=2, ensure_ascii=False)

    print(f"\nReport saved to {out_path}", file=sys.stderr)
    print(f"Scores saved to {scores_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

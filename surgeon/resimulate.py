"""
Part 2 — The Surgeon
Re-simulates 3 bad calls using the fixed system prompt.
Shows before/after comparison.

Usage:
    python surgeon/resimulate.py --no-llm          # static analysis, no API needed
    python surgeon/resimulate.py                   # LLM re-simulation
    python surgeon/resimulate.py --calls call_02 call_03 call_07
"""

import json
import os
import sys
import argparse
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_utils import get_backend, call_llm_with_system


# ── Load resources ──────────────────────────────────────────────────────────

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_text(path):
    return Path(path).read_text(encoding="utf-8")


# ── Build system prompt ──────────────────────────────────────────────────────

def build_system_prompt(fixed_prompt_text: str, transcript: dict) -> str:
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
    result = fixed_prompt_text
    for k, v in replacements.items():
        result = result.replace(k, str(v))
    return result


# ── LLM re-simulation ────────────────────────────────────────────────────────

def resimulate_call(transcript: dict, fixed_prompt_text: str,
                    backend: str, client) -> list[dict]:
    system_prompt = build_system_prompt(fixed_prompt_text, transcript)
    # Truncate system prompt to stay within small-model token limits
    # but keep the customer context block (last ~500 chars) intact
    if len(system_prompt) > 2000:
        system_prompt = system_prompt[:1600] + "\n[... truncated ...]\n" + system_prompt[-400:]

    borrower_turns = [t for t in transcript.get("transcript", [])
                      if t["speaker"] == "customer"][:8]  # cap at 8 turns

    simulated = []
    history = []

    for i, bt in enumerate(borrower_turns):
        history.append({"role": "user", "content": bt["text"][:300]})
        agent_response = call_llm_with_system(
            backend, client, system_prompt, history, max_tokens=200
        )
        history.append({"role": "assistant", "content": agent_response})
        simulated.append({
            "turn": i + 1,
            "borrower": bt["text"],
            "agent_fixed": agent_response
        })
        import time; time.sleep(1)  # avoid TPM rate limit

    return simulated


# ── Static no-LLM analysis ───────────────────────────────────────────────────

def static_analysis(transcript: dict) -> str:
    turns = transcript.get("transcript", [])
    fcs = transcript.get("function_calls", [])
    lines = []

    # Flaw 1: Language switch ignored
    lang_signals = [t for t in turns if t["speaker"] == "customer"
                    and any(kw in t["text"].lower() for kw in
                            ["hindi", "हिंदी", "हिन्दी", "tamil", "தமிழ்", "telugu", "kannada"])]
    switch_calls = [fc for fc in fcs if fc["function"] == "switch_language"]
    if lang_signals and not switch_calls:
        lines.append("  [FLAW 1 — Language Switch Missing]")
        lines.append(f"    Borrower asked: \"{lang_signals[0]['text'][:80]}\"")
        lines.append("    Original agent: never called switch_language(), kept responding in English.")
        lines.append("    Fixed prompt: explicit rule to call switch_language() immediately on request.\n")

    # Flaw 2: Pressure after sensitive disclosure
    for i, t in enumerate(turns):
        if t["speaker"] == "customer" and any(kw in t["text"].lower() for kw in
                ["death", "died", "passed away", "jobless", "unemployed", "no job"]):
            agent_after = [turns[j]["text"].lower() for j in range(i+1, min(i+4, len(turns)))
                           if turns[j]["speaker"] == "agent"]
            pressure = any(kw in a for a in agent_after
                           for kw in ["credit score", "npa", "legal", "days past due", "negative"])
            lines.append("  [FLAW 2 — Empathy / Sensitive Disclosure]")
            lines.append(f"    Borrower disclosed: \"{t['text'][:80]}\"")
            if pressure:
                lines.append("    Original agent: immediately applied credit/legal pressure after disclosure.")
                lines.append("    Fixed prompt: mandatory empathy acknowledgment, pause negotiation, offer callback.\n")
            else:
                lines.append("    Original agent: showed some empathy but no structured follow-through.")
                lines.append("    Fixed prompt: structured empathy + hardship plan before resuming negotiation.\n")
            break

    # Flaw 3: Connection drop / disposition mismatch / no callback
    end_call = next((fc for fc in fcs if fc["function"] == "end_call"), None)
    schedule_cb = next((fc for fc in fcs if fc["function"] == "schedule_callback"), None)
    disposition = transcript.get("disposition", "")

    if disposition == "BLANK_CALL" and len(turns) > 10:
        lines.append("  [FLAW 3 — Disposition Mismatch]")
        lines.append(f"    Call has {len(turns)} turns but disposition = BLANK_CALL.")
        lines.append("    Original agent: used wrong disposition for a real conversation.")
        lines.append("    Fixed prompt: BLANK_CALL reserved only for truly silent/no-audio calls.\n")
    elif end_call and not schedule_cb:
        hello_spam = sum(1 for t in turns[-6:] if t["speaker"] == "agent"
                         and t["text"].lower().strip() in {"hello?", "are you there?", "are you still there?"})
        if hello_spam >= 2:
            lines.append("  [FLAW 3 — Connection Drop, No Recovery]")
            lines.append(f"    Agent sent {hello_spam} 'Hello?' messages then ended call without scheduling callback.")
            lines.append("    Fixed prompt: on connection drop, schedule_callback() required before end_call().\n")

    if not lines:
        lines.append("  No major flaw triggers detected in this transcript.")
        lines.append("  General improvements from fixed prompt: clearer phase transitions,")
        lines.append("  better discovery questions, explicit closure amount disclosure.\n")

    return "\n".join(lines)


# ── Format comparisons ───────────────────────────────────────────────────────

def format_comparison_llm(transcript: dict, simulated: list[dict]) -> str:
    call_id = transcript.get("call_id", "unknown")
    customer_name = transcript.get("customer", {}).get("name", "Borrower")
    disposition = transcript.get("disposition", "")

    lines = [f"\n{'='*70}",
             f"CALL: {call_id} | Customer: {customer_name} | Disposition: {disposition}",
             f"{'='*70}",
             "\n--- ORIGINAL (broken prompt) ---\n"]

    for t in transcript.get("transcript", [])[:30]:
        lines.append(f"  [{t['speaker'].upper()}]: {t['text'][:120]}")

    lines.append("\n--- SIMULATED (fixed prompt) ---\n")
    for s in simulated:
        if s["borrower"]:
            lines.append(f"  [BORROWER]: {s['borrower'][:120]}")
        if s["agent_fixed"]:
            lines.append(f"  [AGENT]:    {s['agent_fixed'][:200]}")
        lines.append("")

    return "\n".join(lines)


def format_comparison_static(transcript: dict) -> str:
    call_id = transcript.get("call_id", "unknown")
    customer_name = transcript.get("customer", {}).get("name", "Borrower")
    disposition = transcript.get("disposition", "")

    lines = [f"\n{'='*70}",
             f"CALL: {call_id} | Customer: {customer_name} | Disposition: {disposition}",
             f"{'='*70}",
             "\n--- ORIGINAL (broken prompt) ---\n"]

    for t in transcript.get("transcript", [])[:30]:
        lines.append(f"  [{t['speaker'].upper()}]: {t['text'][:120]}")

    lines.append("\n--- EXPECTED IMPROVEMENTS (fixed prompt — static analysis) ---\n")
    lines.append(static_analysis(transcript))

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Re-simulate bad calls with fixed prompt")
    parser.add_argument("--calls", nargs="+", default=["call_02", "call_03", "call_07"],
                        help="Call IDs to re-simulate")
    parser.add_argument("--transcripts", default="transcripts", help="Transcripts folder")
    parser.add_argument("--fixed-prompt", default="system-prompt-fixed.md",
                        help="Fixed system prompt file")
    parser.add_argument("--output", default="results/surgeon_comparisons.md",
                        help="Output file")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip LLM — show static before/after analysis instead")
    parser.add_argument("--gemini-key", help="Gemini API key")
    args = parser.parse_args()

    fixed_prompt_text = load_text(args.fixed_prompt)

    backend, client = None, None
    if not args.no_llm:
        backend, client = get_backend(args.gemini_key)
        if not backend:
            print("No LLM available — falling back to static analysis mode.", file=sys.stderr)
            args.no_llm = True
        else:
            print(f"Using LLM: {backend}", file=sys.stderr)

    if args.no_llm:
        print("Running in static analysis mode (no LLM).", file=sys.stderr)

    output_lines = ["# Surgeon — Before/After Comparisons\n"]
    mode = "static analysis" if args.no_llm else "LLM re-simulation"
    output_lines.append(f"Mode: {mode}\n")

    for call_id in args.calls:
        path = Path(args.transcripts) / f"{call_id}.json"
        if not path.exists():
            print(f"Transcript not found: {path}", file=sys.stderr)
            continue

        print(f"Processing {call_id}...", file=sys.stderr)
        transcript = load_json(path)

        if args.no_llm:
            comparison = format_comparison_static(transcript)
        else:
            simulated = resimulate_call(transcript, fixed_prompt_text, backend, client)
            comparison = format_comparison_llm(transcript, simulated)

        print(comparison)
        output_lines.append(comparison)
        output_lines.append("\n")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"\nComparisons saved to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

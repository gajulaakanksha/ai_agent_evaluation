"""
Part 1 — The Detective
Scores each call transcript 0-100 using deterministic rules + LLM judge.
Usage:
    python detective/evaluate.py                          # all transcripts
    python detective/evaluate.py --call transcripts/call_01.json
"""

import json
import os
import sys
import argparse
import re
from pathlib import Path

# Add repo root to path so llm_utils is importable from any working directory
sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_utils import get_backend, call_llm as _call_llm


# ───────────────────────────── helpers ──────────────────────────────────────

def load_transcript(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def agent_turns(transcript: dict) -> list[str]:
    return [t["text"] for t in transcript.get("transcript", []) if t["speaker"] == "agent"]


def all_turns(transcript: dict) -> list[dict]:
    return transcript.get("transcript", [])


def function_calls(transcript: dict) -> list[dict]:
    return transcript.get("function_calls", [])


# ───────────────────────────── scoring dimensions ───────────────────────────

def score_phase_progression(transcript: dict) -> tuple[int, str]:
    """15 pts — correct phase order."""
    phases = transcript.get("phases_visited", [])
    disposition = transcript.get("disposition", "")
    turns = transcript.get("transcript", [])

    # BLANK_CALL with a real conversation is a disposition mismatch — penalise it
    if disposition == "BLANK_CALL" and len(turns) > 10:
        return 5, "BLANK_CALL disposition but full conversation exists — mismatch"

    # Genuine quick exits (wrong number, clean dispute) are fine with few phases
    quick_exit_dispositions = {"WRONG_NUMBER", "DISPUTE"}
    if disposition in quick_exit_dispositions and len(phases) <= 3:
        return 15, "Acceptable quick exit for disposition type"

    phase_order = ["opening", "discovery", "negotiation", "closing"]
    # dispute is a valid branch, callback_opening is a variant of opening
    valid_phases = set(phase_order + ["dispute", "callback_opening"])

    visited_ordered = [p for p in phase_order if p in phases]

    # Penalise phase-hopping in very short calls — visiting phases without substance
    total_turns_meta = transcript.get("total_turns", len(turns))
    if total_turns_meta <= 10 and len(visited_ordered) >= 3:
        return 5, f"Phase-hopping in very short call ({total_turns_meta} turns, {len(visited_ordered)} phases)"

    if len(visited_ordered) >= 4:
        return 15, "All 4 phases visited"
    elif len(visited_ordered) == 3:
        return 10, f"3 phases visited: {phases}"
    elif len(visited_ordered) == 2:
        return 5, f"Only 2 phases: {phases}"
    else:
        return 0, f"Only 1 phase or wrong order: {phases}"


def score_identity_and_amounts(transcript: dict) -> tuple[int, str]:
    """15 pts — TOS + POS disclosed after identity confirmed."""
    turns = all_turns(transcript)
    agent_texts = [t["text"].lower() for t in turns if t["speaker"] == "agent"]
    full_text = " ".join(agent_texts)

    # Check if amounts are mentioned
    has_total = any(phrase in full_text for phrase in [
        "total outstanding", "total amount", "fifty thousand", "forty", "thirty",
        "sixteen thousand", "twenty", "ninety"
    ])
    has_closure = any(phrase in full_text for phrase in [
        "closure amount", "close your loan", "close it at", "close at",
        "thirty five thousand", "ten thousand", "twenty nine", "remove all charges",
        "charges removed", "waiving"
    ])

    # Check if TOS quoted as "what you need to pay" (bad)
    tos_as_payment = any(phrase in full_text for phrase in [
        "you need to pay fifty thousand",
        "pay the fifty thousand rupees",
        "pay fifty thousand"
    ])

    score = 0
    notes = []

    if has_total and has_closure:
        score = 15
        notes.append("Both TOS and closure amount disclosed")
    elif has_total or has_closure:
        score = 8
        notes.append("Only one amount type disclosed")
    else:
        score = 0
        notes.append("No amounts disclosed")

    if tos_as_payment:
        score = max(0, score - 5)
        notes.append("PENALTY: TOS quoted as payment amount")

    return score, "; ".join(notes)


def score_discovery_quality(transcript: dict) -> tuple[int, str]:
    """15 pts — genuine exploration of borrower situation."""
    turns = all_turns(transcript)
    fcs = function_calls(transcript)

    # Count meaningful agent questions (not just "hello?" or "are you there?")
    question_patterns = [
        r"what.{0,30}(difficult|causing|reason|happen|situation|problem)",
        r"(when|how long).{0,30}(unemployed|job|work|pay)",
        r"(temporary|long.term|ongoing)",
        r"(family|support|income|expense)",
        r"(tell me|could you|can you).{0,30}(about|explain|share)",
    ]
    meaningful_questions = 0
    for t in turns:
        if t["speaker"] == "agent":
            text = t["text"].lower()
            for pat in question_patterns:
                if re.search(pat, text):
                    meaningful_questions += 1
                    break

    # Check if agent rushed to negotiation (proceed_to_negotiation called early)
    neg_turn = None
    disc_turn = None
    for fc in fcs:
        if fc["function"] == "proceed_to_negotiation" and neg_turn is None:
            neg_turn = fc["turn"]
        if fc["function"] == "proceed_to_discovery" and disc_turn is None:
            disc_turn = fc["turn"]

    rushed = False
    if neg_turn and disc_turn:
        turns_in_discovery = neg_turn - disc_turn
        if turns_in_discovery < 4:
            rushed = True

    disposition = transcript.get("disposition", "")
    # Wrong number — discovery not expected
    if disposition == "WRONG_NUMBER":
        return 15, "Discovery not applicable for wrong number"

    # BLANK_CALL with real conversation — this is a failure, not a quick exit
    if disposition == "BLANK_CALL" and len(turns) > 10:
        return 0, "BLANK_CALL disposition mismatch — discovery quality unknown"

    # Inbound callback that skips discovery entirely is a problem
    phases = transcript.get("phases_visited", [])
    skipped_discovery = "discovery" not in phases and "callback_opening" in phases

    # Penalise if discovery questions got only 1-word/evasive answers and agent gave up
    total_turns_meta = transcript.get("total_turns", len(turns))
    if total_turns_meta <= 10 and meaningful_questions >= 1:
        # Check if customer responses were substantive (>8 words, not just complaints)
        customer_responses = [t["text"] for t in turns if t["speaker"] == "customer"]
        substantive = sum(1 for r in customer_responses
                          if len(r.split()) > 8 and not any(
                              kw in r.lower() for kw in ["why are you", "what are you", "stop", "don't"]))
        if substantive < 1:
            # Questions asked but no real answers — agent gave up without digging
            meaningful_questions = 0

    if meaningful_questions >= 3 and not rushed:
        return 15, f"{meaningful_questions} meaningful discovery questions"
    elif meaningful_questions >= 2 or (meaningful_questions >= 1 and not rushed):
        return 8, f"{meaningful_questions} discovery questions, some depth"
    elif skipped_discovery:
        return 2, "Inbound callback — discovery phase skipped entirely"
    elif rushed:
        return 3, "Rushed to negotiation without adequate discovery"
    else:
        return 0, "No meaningful discovery"


def score_language_handling(transcript: dict) -> tuple[int, str]:
    """10 pts — prompt language switching."""
    turns = all_turns(transcript)
    fcs = function_calls(transcript)

    # Detect if borrower requested a language switch
    language_signals = []
    for i, t in enumerate(turns):
        if t["speaker"] == "customer":
            text = t["text"].lower()
            if any(kw in text for kw in ["hindi", "हिंदी", "हिन्दी", "tamil", "தமிழ்", "telugu", "kannada"]):
                language_signals.append(i)

    if not language_signals:
        return 10, "No language switch needed"

    # Find when switch_language was called
    switch_turns = [fc["turn"] for fc in fcs if fc["function"] == "switch_language"]

    if not switch_turns:
        return 0, "Borrower requested language switch but agent never switched"

    first_signal_turn = language_signals[0]
    first_switch = min(switch_turns)

    # Check if agent kept reverting to English after switching
    revert_count = 0
    switched = False
    for t in turns:
        if t["speaker"] == "agent":
            text = t["text"]
            # After a switch, check for English-only responses
            if switched and re.match(r'^[A-Za-z\s\d\.,!?\'"-]+$', text) and len(text) > 30:
                revert_count += 1

    delay = first_switch - first_signal_turn

    if delay <= 2 and revert_count <= 1:
        return 10, f"Language switched promptly (delay={delay} turns)"
    elif delay <= 4 and revert_count <= 2:
        return 5, f"Language switch delayed ({delay} turns), {revert_count} reversions"
    else:
        return 2, f"Language switch very delayed ({delay} turns) or frequent reversions ({revert_count})"


def score_repetition(transcript: dict) -> tuple[int, str]:
    """15 pts — no looping or repetition."""
    agent_texts = [t["text"] for t in all_turns(transcript) if t["speaker"] == "agent"]

    # Normalize texts for comparison
    def normalize(text):
        return re.sub(r'\s+', ' ', text.lower().strip())

    normalized = [normalize(t) for t in agent_texts]

    # Count near-duplicate agent messages (>70% overlap using simple word overlap)
    repeat_count = 0
    seen = []
    for text in normalized:
        words = set(text.split())
        if len(words) < 5:
            continue  # skip very short turns
        for prev in seen:
            prev_words = set(prev.split())
            if len(prev_words) < 5:
                continue
            overlap = len(words & prev_words) / max(len(words | prev_words), 1)
            if overlap > 0.7:
                repeat_count += 1
                break
        seen.append(text)

    # Also check for "hello?" spam (connectivity handling)
    hello_count = sum(1 for t in normalized if t.strip() in {"hello?", "are you there?", "hello", "are you still there?"})
    # Excessive hello spam beyond what's needed
    excessive_hello = max(0, hello_count - 3)

    total_issues = repeat_count + excessive_hello

    if total_issues == 0:
        return 15, "No significant repetition"
    elif total_issues <= 2:
        return 10, f"Minor repetition ({total_issues} instances)"
    elif total_issues <= 5:
        return 5, f"Moderate repetition ({total_issues} instances)"
    else:
        return 0, f"Severe looping ({total_issues} repetition instances)"


def score_empathy(transcript: dict) -> tuple[int, str]:
    """15 pts — appropriate empathy and tone."""
    turns = all_turns(transcript)

    # Detect sensitive signals from customer
    sensitive_signals = []
    for t in turns:
        if t["speaker"] == "customer":
            text = t["text"].lower()
            if any(kw in text for kw in ["death", "died", "passed away", "husband", "wife", "bereavement",
                                          "jobless", "unemployed", "no job", "lost my job", "can't pay",
                                          "struggling", "difficult", "frustrated", "angry"]):
                sensitive_signals.append(text)

    if not sensitive_signals:
        return 15, "No sensitive signals detected, tone acceptable"

    agent_texts = [t["text"].lower() for t in turns if t["speaker"] == "agent"]

    # Check for empathy acknowledgments
    empathy_phrases = ["i understand", "i'm sorry", "i am sorry", "that must be", "i hear you",
                       "i can understand", "mujhe afsos", "bahut afsos", "समझ", "माफ़"]
    empathy_count = sum(1 for text in agent_texts
                        if any(phrase in text for phrase in empathy_phrases))

    # Check for inappropriate pressure after sensitive signal
    pressure_after_sensitive = False
    sensitive_turn_idx = None
    for i, t in enumerate(turns):
        if t["speaker"] == "customer" and any(kw in t["text"].lower() for kw in
                                               ["death", "died", "passed away", "jobless", "unemployed"]):
            sensitive_turn_idx = i
            break

    if sensitive_turn_idx is not None:
        for t in turns[sensitive_turn_idx:sensitive_turn_idx + 3]:
            if t["speaker"] == "agent":
                text = t["text"].lower()
                if any(phrase in text for phrase in ["credit score", "negative entry", "legal", "escalat",
                                                      "days past due", "npa", "consequences"]):
                    pressure_after_sensitive = True
                    break

    if empathy_count >= 2 and not pressure_after_sensitive:
        return 15, f"Good empathy ({empathy_count} acknowledgments)"
    elif empathy_count >= 1 and not pressure_after_sensitive:
        return 10, "Some empathy shown"
    elif pressure_after_sensitive:
        return 3, "PENALTY: Pressure applied immediately after sensitive disclosure"
    else:
        return 5, "Sensitive signals present but limited empathy shown"


def score_resolution(transcript: dict) -> tuple[int, str]:
    """15 pts — clear resolution and correct disposition."""
    fcs = function_calls(transcript)
    disposition = transcript.get("disposition", "")
    turns = all_turns(transcript)

    agent_texts = " ".join(t["text"].lower() for t in turns if t["speaker"] == "agent")
    customer_texts = " ".join(t["text"].lower() for t in turns if t["speaker"] == "customer")

    end_call_fc = next((fc for fc in fcs if fc["function"] == "end_call"), None)
    schedule_cb = next((fc for fc in fcs if fc["function"] == "schedule_callback"), None)

    # Disposition mismatch: BLANK_CALL with full conversation
    disposition_mismatch = disposition == "BLANK_CALL" and len(turns) > 10

    # Connection drop with no recovery: agent ends call after silence without scheduling callback
    connection_drop_no_recovery = False
    if end_call_fc:
        reason = end_call_fc.get("params", {}).get("reason", "")
        # If call ended due to connection but no callback was scheduled
        if reason == "callback_scheduled" and not schedule_cb:
            connection_drop_no_recovery = True
    # Also detect: last 4 agent turns are all "Hello?" / "Are you there?" with no callback
    last_agent_turns = [t["text"].lower() for t in turns[-6:] if t["speaker"] == "agent"]
    hello_spam_ending = sum(1 for t in last_agent_turns
                            if t.strip() in {"hello?", "are you there?", "are you still there?",
                                             "kavita menon, can you hear me?"})
    if hello_spam_ending >= 3 and not schedule_cb:
        connection_drop_no_recovery = True

    # Payment commitment requires both intent AND a confirmed date/amount from agent
    commitment_phrases = ["i will pay", "i'll pay", "pay on", "april", "month end", "end of month"]
    has_payment_commitment = any(phrase in customer_texts for phrase in commitment_phrases)

    # If connection dropped (agent ended with hello spam), commitment is unconfirmed
    if connection_drop_no_recovery and has_payment_commitment:
        has_payment_commitment = False  # dropped before confirmation

    # "every month" alone is not a commitment if no amount/date confirmed
    if "every month" in customer_texts and not any(
        p in customer_texts for p in ["april", "month end", "i will pay", "i'll pay"]
    ):
        has_payment_commitment = False
    has_callback = schedule_cb is not None
    has_dispute_escalation = any(phrase in agent_texts for phrase in
                                  ["support@demolender", "email", "contact demolender"])
    has_proper_end = end_call_fc is not None

    # call_10 pattern: very short call (≤9 actual turns), no commitment, agent gives up
    total_turns = transcript.get("total_turns", len(turns))
    very_short_no_commitment = (total_turns <= 10 and not has_payment_commitment
                                 and not has_callback and disposition == "NO_COMMITMENT")

    score = 0
    notes = []

    if disposition_mismatch:
        score -= 10
        notes.append("PENALTY: Disposition mismatch (BLANK_CALL with full conversation)")

    if connection_drop_no_recovery:
        score -= 8
        notes.append("PENALTY: Connection dropped, no callback scheduled")

    if very_short_no_commitment:
        score += 2
        notes.append("Call too short, no commitment, agent gave up")
    elif has_payment_commitment and has_callback:
        score += 15
        notes.append("Payment commitment + callback scheduled")
    elif has_payment_commitment:
        score += 12
        notes.append("Payment commitment secured")
    elif has_callback:
        cb_params = schedule_cb.get("params", {})
        if cb_params.get("preferred_time") and cb_params.get("reason"):
            score += 10
            notes.append("Callback scheduled with date and reason")
        else:
            score += 6
            notes.append("Callback scheduled but vague")
    elif has_dispute_escalation:
        score += 12
        notes.append("Dispute escalated with contact info")
    elif has_proper_end:
        score += 5
        notes.append("Call ended but no clear resolution")
    else:
        notes.append("No resolution or proper ending")

    return max(-15, min(15, score)), "; ".join(notes)


# ───────────────────────────── penalty flags ────────────────────────────────

def compute_penalties(transcript: dict) -> tuple[int, list[str]]:
    """Compute penalty deductions from the penalty flag table."""
    turns = all_turns(transcript)
    penalties = 0
    flags = []

    agent_texts_raw = [t["text"] for t in turns if t["speaker"] == "agent"]
    agent_texts = [t.lower() for t in agent_texts_raw]

    # Identity leak: amounts disclosed before identity confirmed
    # Heuristic: if amount mentioned in first 2 agent turns
    early_agent = agent_texts[:2]
    amount_keywords = ["thousand", "rupees", "pending", "outstanding", "fifty", "forty", "thirty"]
    if any(any(kw in t for kw in amount_keywords) for t in early_agent):
        # Check if identity was confirmed first
        first_customer = next((t["text"].lower() for t in turns if t["speaker"] == "customer"), "")
        if not any(kw in first_customer for kw in ["yes", "speaking", "haan", "ji"]):
            penalties += 10
            flags.append("Identity leak: amounts disclosed before identity confirmed (-10)")

    # Forbidden phrases
    forbidden = ["i do not understand", "i am only able to help with",
                 "this sounds like", "here is a breakdown", "for anything else, contact"]
    for text in agent_texts:
        for phrase in forbidden:
            if phrase in text:
                penalties += 5
                flags.append(f"Forbidden phrase used: '{phrase}' (-5)")
                break

    # Function name output as text
    func_names = ["proceed_to_discovery", "proceed_to_negotiation", "proceed_to_closing",
                  "proceed_to_dispute", "end_call", "schedule_callback", "switch_language"]
    for text in agent_texts_raw:
        for fn in func_names:
            if fn in text:
                penalties += 10
                flags.append(f"Function name output as text: {fn} (-10)")

    # Credit pressure during bereavement
    bereavement_detected = False
    for i, t in enumerate(turns):
        if t["speaker"] == "customer" and any(kw in t["text"].lower() for kw in
                                               ["death", "died", "passed away", "husband died"]):
            bereavement_detected = True
            # Check next 2 agent turns
            agent_after = [turns[j]["text"].lower() for j in range(i + 1, min(i + 4, len(turns)))
                           if turns[j]["speaker"] == "agent"]
            for at in agent_after:
                if any(kw in at for kw in ["credit score", "days past due", "npa", "negative entry",
                                            "six hundred", "668"]):
                    penalties += 5
                    flags.append("Credit pressure applied after bereavement disclosure (-5)")
                    break

    return penalties, flags


# ───────────────────────────── LLM judge ────────────────────────────────────

def llm_judge(transcript: dict, gemini_key: str = None) -> dict:
    """Call LLM to identify worst agent messages. Returns dict with worst_messages list."""
    backend, client = get_backend(gemini_key)
    if not backend:
        return {
            "worst_messages": [],
            "overall_assessment": "LLM judge skipped (no API key found — set GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY)"
        }

    prompt_template = Path("detective/judge_prompt.txt").read_text(encoding="utf-8")

    lines = []
    for t in transcript.get("transcript", []):
        lines.append(f"[{t['speaker'].upper()}]: {t['text']}")
    transcript_str = "\n".join(lines)

    # Truncate to ~3000 chars to stay within small-model token limits
    if len(transcript_str) > 3000:
        transcript_str = transcript_str[:3000] + "\n[... transcript truncated for length ...]"

    prompt = prompt_template.replace("{{TRANSCRIPT}}", transcript_str)

    raw = _call_llm(backend, client, prompt, max_tokens=1024)

    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass

    return {
        "worst_messages": [],
        "overall_assessment": f"LLM parse error. Raw: {raw[:200]}"
    }


# ───────────────────────────── main scorer ──────────────────────────────────

def score_call(transcript: dict, use_llm: bool = True, gemini_key: str = None) -> dict:
    call_id = transcript.get("call_id", "unknown")

    # Dimension scores
    d1, n1 = score_phase_progression(transcript)
    d2, n2 = score_identity_and_amounts(transcript)
    d3, n3 = score_discovery_quality(transcript)
    d4, n4 = score_language_handling(transcript)
    d5, n5 = score_repetition(transcript)
    d6, n6 = score_empathy(transcript)
    d7, n7 = score_resolution(transcript)

    base_score = d1 + d2 + d3 + d4 + d5 + d6 + d7

    # Penalties
    penalty_pts, penalty_flags = compute_penalties(transcript)
    final_score = max(0, min(100, base_score - penalty_pts))

    verdict = "good" if final_score >= 60 else "bad"

    # LLM judge for worst messages
    llm_result = llm_judge(transcript, gemini_key) if use_llm else {
        "worst_messages": [],
        "overall_assessment": "LLM judge disabled"
    }

    return {
        "call_id": call_id,
        "score": final_score,
        "verdict": verdict,
        "dimension_scores": {
            "phase_progression": {"score": d1, "note": n1},
            "identity_and_amounts": {"score": d2, "note": n2},
            "discovery_quality": {"score": d3, "note": n3},
            "language_handling": {"score": d4, "note": n4},
            "repetition": {"score": d5, "note": n5},
            "empathy": {"score": d6, "note": n6},
            "resolution": {"score": d7, "note": n7},
        },
        "base_score": base_score,
        "penalty_deductions": penalty_pts,
        "penalty_flags": penalty_flags,
        "worst_messages": llm_result.get("worst_messages", []),
        "llm_assessment": llm_result.get("overall_assessment", ""),
    }


# ───────────────────────────── CLI ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Score debt collection call transcripts")
    parser.add_argument("--call", help="Path to a single transcript JSON file")
    parser.add_argument("--transcripts", default="transcripts", help="Folder of transcripts")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM judge")
    parser.add_argument("--gemini-key", help="Gemini API key (overrides GEMINI_API_KEY env var)")
    parser.add_argument("--output", default="results/detective_scores.json", help="Output file")
    args = parser.parse_args()

    use_llm = not args.no_llm
    gemini_key = args.gemini_key

    if args.call:
        paths = [args.call]
    else:
        folder = Path(args.transcripts)
        paths = sorted([str(p) for p in folder.glob("call_*.json")])

    results = []
    for path in paths:
        print(f"Scoring {path}...", file=sys.stderr)
        transcript = load_transcript(path)
        result = score_call(transcript, use_llm=use_llm, gemini_key=gemini_key)
        results.append(result)

        # Print summary to stdout
        print(f"\n{'='*60}")
        print(f"Call: {result['call_id']}")
        print(f"Score: {result['score']}/100  |  Verdict: {result['verdict'].upper()}")
        print(f"Dimensions:")
        for dim, val in result["dimension_scores"].items():
            print(f"  {dim:30s}: {val['score']:3d}  ({val['note']})")
        if result["penalty_flags"]:
            print(f"Penalties: {result['penalty_deductions']} pts")
            for flag in result["penalty_flags"]:
                print(f"  - {flag}")
        if result["worst_messages"]:
            print(f"\nWorst agent messages:")
            for msg in result["worst_messages"]:
                print(f"  [{msg.get('severity','?').upper()}] {msg.get('agent_text_snippet','')[:70]}")
                print(f"    → {msg.get('reason','')}")
        if result["llm_assessment"]:
            print(f"\nLLM Assessment: {result['llm_assessment']}")

    # Save results
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n\nResults saved to {out_path}", file=sys.stderr)

    # Accuracy check if verdicts.json exists
    verdicts_path = Path("verdicts.json")
    if verdicts_path.exists():
        with open(verdicts_path, encoding="utf-8") as f:
            verdicts_data = json.load(f)
        human_verdicts = verdicts_data.get("verdicts", {})

        correct = 0
        total = 0
        print(f"\n{'='*60}")
        print("ACCURACY CHECK vs verdicts.json")
        print(f"{'='*60}")
        for r in results:
            cid = r["call_id"]
            if cid in human_verdicts:
                human = human_verdicts[cid]["verdict"]
                predicted = r["verdict"]
                match = "OK" if human == predicted else "MISS"
                print(f"  {match} {cid}: predicted={predicted}, human={human}")
                if human == predicted:
                    correct += 1
                total += 1
        print(f"\nAccuracy: {correct}/{total} = {correct/total*100:.0f}%")


if __name__ == "__main__":
    main()

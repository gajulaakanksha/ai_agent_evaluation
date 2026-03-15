# Evaluator Scoring Criteria

## Overview
Each call is scored 0–100 across 7 deterministic dimensions.
A score ≥ 60 → verdict "good". Score < 60 → verdict "bad".

---

## Dimensions & Weights

### 1. Phase Progression (15 pts)
Does the agent move through phases in the correct order (Opening → Discovery → Negotiation → Closing)?
- All 4 phases visited in order: 15
- 3 phases visited correctly: 10
- 2 phases: 5
- 1 phase or wrong order: 0
- Special: wrong_number / dispute_unresolved with ≤2 phases is acceptable (full 15 pts)

### 2. Identity & Amount Disclosure (15 pts)
Does the agent correctly disclose TOS and POS (closure amount) after identity confirmation?
- Both TOS and POS disclosed clearly: 15
- Only one amount disclosed: 8
- No amounts disclosed (or amounts disclosed before identity confirmed): 0
- Deduct 5 if agent quotes TOS as "what you need to pay" instead of leading with POS

### 3. Discovery Quality (15 pts)
Does the agent genuinely explore the borrower's situation before jumping to negotiation?
- Asks follow-up questions, identifies root cause, classifies borrower: 15
- Some discovery but shallow: 8
- Skips discovery entirely or rushes to payment: 0
- Deduct 5 if agent proceeds to negotiation after <2 meaningful exchanges

### 4. Language Handling (10 pts)
Does the agent switch language promptly when the borrower signals a preference?
- No language switch needed (English throughout): 10
- Language switch triggered promptly (within 1-2 turns of signal): 10
- Language switch triggered but delayed (3+ turns after signal): 5
- Language switch triggered but agent keeps reverting to English: 2
- Language switch never triggered despite clear signal: 0

### 5. Repetition & Looping (15 pts)
Does the agent avoid repeating the same phrases/questions and make forward progress?
- No significant repetition, clear progression: 15
- Minor repetition (1-2 instances): 10
- Moderate repetition (3-5 instances): 5
- Severe looping (same content repeated 5+ times, no progress): 0

### 6. Empathy & Tone (15 pts)
Does the agent respond appropriately to emotional signals (job loss, bereavement, frustration)?
- Acknowledges emotional context, adjusts tone, does not pressure inappropriately: 15
- Partial empathy (acknowledges but then immediately pivots to pressure): 8
- Ignores emotional signals entirely: 3
- Applies pressure in clearly inappropriate context (e.g., bereavement): 0

### 7. Resolution & Closing (15 pts)
Does the call end with a clear, appropriate resolution?
- Payment committed / callback scheduled with specific date+amount: 15
- Callback scheduled but vague (no date or amount): 8
- Dispute escalated correctly with email/contact provided: 12
- Call ends abruptly without resolution or next step: 0
- Wrong disposition recorded vs. actual conversation: -10 (penalty)

---

## Penalty Flags (applied after base score)

| Flag | Deduction |
|------|-----------|
| Agent discloses loan details before confirming identity | -10 |
| Agent says "I do not understand" (forbidden phrase) | -5 |
| Agent outputs function name as text (e.g., "proceed_to_discovery") | -10 |
| Agent uses forbidden phrases ("I am only able to help with...") | -5 |
| Disposition in metadata contradicts actual conversation outcome | -10 |
| Agent fails to offer escalation path in dispute scenario | -5 |
| Agent applies credit score pressure during bereavement/death disclosure | -5 |

---

## Verdict Threshold
- Score ≥ 60 → "good"
- Score < 60 → "bad"

---

## LLM Judge Prompt
See `judge_prompt.txt` for the exact prompt used when calling the LLM for per-message analysis.

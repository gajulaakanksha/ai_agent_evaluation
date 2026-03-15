# Pipeline Report
Generated: 2026-03-15 18:55:58

## Prompt: system-prompt.md
- Mean score: 65.2/100
- Good/Bad: 5/5 (50.0% good)
- Score range: 40 – 93

| Call | Score | Verdict | Key Issues |
|------|-------|---------|------------|
| call_01 | 93 | good |  |
| call_02 | 53 | bad |  |
| call_03 | 40 | bad |  |
| call_04 | 85 | good |  |
| call_05 | 73 | good | Identity leak: amounts disclosed before identity confirmed ( |
| call_06 | 78 | good |  |
| call_07 | 48 | bad |  |
| call_08 | 73 | good |  |
| call_09 | 54 | bad |  |
| call_10 | 55 | bad |  |

## Prompt: system-prompt-fixed.md
- Mean score: 65.2/100
- Good/Bad: 5/5 (50.0% good)
- Score range: 40 – 93

| Call | Score | Verdict | Key Issues |
|------|-------|---------|------------|
| call_01 | 93 | good |  |
| call_02 | 53 | bad |  |
| call_03 | 40 | bad |  |
| call_04 | 85 | good |  |
| call_05 | 73 | good | Identity leak: amounts disclosed before identity confirmed ( |
| call_06 | 78 | good |  |
| call_07 | 48 | bad |  |
| call_08 | 73 | good |  |
| call_09 | 54 | bad |  |
| call_10 | 55 | bad |  |

## Prompt Comparison
| Prompt | Mean Score | Good Rate |
|--------|-----------|-----------|
| system-prompt.md | 65.2 | 50.0% |
| system-prompt-fixed.md | 65.2 | 50.0% |

**Result: Tie** — all prompts scored 65.2. Use `--simulate` with an API key for a meaningful comparison.

## Suggested Prompt Improvements (Auto-generated)

### 1. Insufficient urgency conveyed about payment
- Location: CORE PRINCIPLES section
- Current: `The borrower needs to understand that failure to pay will result in serious consequences for their f`
- Fix: The borrower needs to understand that failure to pay will result in severe financial penalties, including damage to their credit score and potential legal action.

### 2. Inadequate handling of amount disputes
- Location: CORE PRINCIPLES section
- Current: `Never insist on your numbers. Say 'Let me verify' or 'I will check the exact figures.'`
- Fix: If the borrower disputes the amount, say 'I understand your concern. Let me verify the exact figures and provide a revised breakdown.'

### 3. Lack of clear transition to negotiation phase
- Location: FUNCTION CALLING section
- Current: `Use the function calling mechanism ONLY. NEVER output code, tool_code, print(), or function names as`
- Fix: Use the function calling mechanism to transition to the negotiation phase: 'Let's discuss possible payment arrangements. What options are you considering?'
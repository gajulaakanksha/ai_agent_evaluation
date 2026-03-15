# Surgeon — Flaw Analysis

## The 3 Serious Flaws in system-prompt.md

---

### Flaw 1: Language Switching is Reactive, Not Proactive — and Has No Persistence Guarantee

**Where in the prompt:** Global System Prompt has no language instruction. Phase prompts have no language instruction. The `switch_language` function exists but the prompt never tells the agent *when* to call it or *how to stay in that language*.

**What goes wrong:** The agent switches language only after the borrower explicitly complains multiple times. Even after switching, it reverts to English mid-conversation because the phase prompts are all written in English and the agent defaults back to them.

**Transcripts that prove it:**
- **call_02 (Rahul Verma):** The borrower says "हिंदी में बात करिए" (speak in Hindi) repeatedly. The agent switches to Hindi but then delivers a long English paragraph: *"I am so sorry to hear about your husband's passing... Resolving the payment does not mean giving up the dispute..."* — after the borrower had already complained 3 times about English. The `switch_language` function was called 3 separate times in the same call, proving the agent kept forgetting.
- **call_03 (Anjali Reddy):** Borrower starts in Tamil. Agent switches to Tamil, then switches to Hindi mid-call, then back to Tamil. The `switch_language` function is called 4 times. The borrower explicitly says *"आपका तमिल आराम से कुछ समझ में नहीं आ रहा"* (your Tamil is not understandable) — the agent's Tamil was broken because it was transliterating rather than genuinely switching.
- **call_07 (Meera Joshi):** Borrower asks "do you know Tamil?" at turn 28. Agent only switches at turn 19 (function call), but the Tamil responses are incoherent and the agent never escalates to a human or schedules a callback when communication completely breaks down.

**Root cause in prompt:** The prompt says nothing about: (a) detecting language preference proactively from the borrower's first message, (b) staying in the switched language for the rest of the call, (c) what to do when the language barrier makes the call unproductive (no fallback strategy).

---

### Flaw 2: No Protocol for "Already Paid" / Payment Dispute Claims — Agent Loops Indefinitely

**Where in the prompt:** The Discovery phase says *"Loan closed/cancelled: apologize, end call."* That's it. One line. There is no guidance on: how to handle a UTR number claim, what to tell the borrower about verification, how many times to attempt verification before escalating, or what the escalation path is.

**What goes wrong:** When a borrower claims they already paid and provides a UTR number, the agent has no script. It loops — asking for the UTR, saying it can't find it, asking again, saying it can't find it — for 15 minutes without ever offering a concrete next step.

**Transcript that proves it:**
- **call_03 (Anjali Reddy):** The borrower provides UTR number "CM552522" multiple times. The agent says *"मुझे इस नंबर से भी कोई भुगतान नहीं मिल रहा है"* (I can't find this payment) repeatedly — at least 4 times. The agent never: offers to escalate to a payment verification team, provides an email to send the payment screenshot, or schedules a callback for verification. The call runs 901 seconds (15 minutes) with the agent flagged as `is_repeating: true`. The borrower ends up frustrated and the call ends without resolution.
- **call_02 (Rahul Verma):** The borrower's husband allegedly paid the loan before dying. The agent eventually provides `support@demolender.com` but only after 60+ turns. The prompt gives no guidance on bereavement + payment dispute scenarios.

**Root cause in prompt:** The Discovery phase's "Loan closed/cancelled: apologize, end call" is dangerously incomplete. It assumes the agent can instantly verify payment, which it cannot. There's no UTR verification workflow, no escalation path, no maximum loop count before handing off.

---

### Flaw 3: The "Urgency" Instructions Cause Inappropriate Pressure in Sensitive Situations

**Where in the prompt:** Global System Prompt: *"You MUST convey urgency about payment. The borrower needs to understand that failure to pay will result in serious consequences for their financial future."* and *"If the borrower hesitates, remind them firmly: 'This is a pending obligation that requires immediate attention.'"*

Discovery phase: *"A) Financial hardship → emphasize closure at reduced amount, remind them this is their best option before things get worse"*

Negotiation phase: *"TONE: Professional and firm. Make sure the borrower understands the gravity of the situation."*

**What goes wrong:** The urgency instructions have no exception for sensitive contexts. When a borrower discloses bereavement, job loss, or a legitimate dispute, the agent is still instructed to "convey urgency" and "remind them firmly." This causes the agent to apply credit score pressure immediately after a borrower mentions their husband died.

**Transcript that proves it:**
- **call_02 (Rahul Verma):** After the borrower reveals her husband died 7 March 2025 (one year ago), the agent says: *"I am so sorry to hear about your husband's passing... at six hundred and sixty-eight days past due, every month adds another negative entry to the credit report. Banks only see an unpaid loan. Resolving the payment does not mean giving up the dispute."* — This is the urgency script firing in a bereavement context. The borrower had just disclosed a death and the agent pivoted to credit score consequences in the same breath.
- **call_03 (Anjali Reddy):** After the borrower vents about paying for a course that didn't deliver value, the agent says: *"उनके भुगतान में देरी के अब तीन सौ तैंतीस दिन हो गए हैं"* (333 days past due) — applying DPD pressure while the borrower is trying to explain a legitimate grievance.
- **call_10 (Ravi Gupta):** The agent rushes to closing after just 9 turns with no real discovery, citing "credit score" and "negative entry" to a borrower who hasn't even explained their situation yet.

**Root cause in prompt:** The urgency mandate is unconditional. There is no instruction to pause urgency when: (a) borrower discloses bereavement, (b) borrower has a legitimate payment dispute, (c) borrower is in acute financial hardship. The empathy instruction ("say 'I understand' to show empathy") is cosmetic — it doesn't actually suppress the urgency behavior.

---

## Summary Table

| # | Flaw | Calls Affected | Severity |
|---|------|---------------|----------|
| 1 | No language persistence / no fallback for language barrier | call_02, call_03, call_07 | High |
| 2 | No protocol for already-paid / UTR dispute claims | call_02, call_03 | High |
| 3 | Unconditional urgency fires in sensitive contexts | call_02, call_03, call_10 | High |

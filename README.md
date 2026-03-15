# AI Agent Evaluation & Prompt Optimization

## Project Summary

This project evaluates and improves the behavior of an AI voice agent used for education loan debt collection calls.
The agent interacts with borrowers through multiple conversation phases and attempts to guide them toward resolving outstanding loan payments.

The repository implements a full workflow to:

- Detect problematic conversations

- Identify flaws in the system prompt

- Fix the prompt and validate improvements

- Build a reusable prompt evaluation pipeline

The result is an automated evaluation framework for conversational AI systems.

## Problem Statement

AI debt collection agents must carefully balance several goals:

- clearly explain loan obligations

- understand borrower circumstances

- negotiate repayment options

- remain professional and empathetic

- avoid harassment or repetitive messaging

Poor prompt design can cause issues such as:

- ignoring borrower concerns

- repeating payment demands

- skipping discovery questions

- pressuring borrowers during distress

Manual monitoring of calls does not scale, so an automated evaluation system is needed.


## Setup

```bash
pip install -r requirements.txt
```

Set your API key in `.env` (copy from `.env.example`). Groq is recommended — it's free, fast, and has no daily quota issues:

```bash
# Option 1: Groq (free, recommended) — get key at https://console.groq.com
GROQ_API_KEY=your_groq_key_here

# Option 2: Gemini (free tier) — get key at https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your_gemini_key_here

# Option 3: Anthropic / OpenAI as fallback
ANTHROPIC_API_KEY=your_key
OPENAI_API_KEY=your_key
```

The scripts auto-detect whichever key is set. Priority: Groq → Gemini → Anthropic → OpenAI.

---

## System Architecture

The system is designed as a modular evaluation pipeline that separates conversation scoring, prompt analysis, and prompt experimentation.

This modular design allows new prompts to be tested without modifying the evaluation logic.

### Architecture Overview
                +----------------------+
                |   System Prompt      |
                |  (Original / Fixed)  |
                +----------+-----------+
                           |
                           v
                +----------------------+
                | Conversation Simulator|
                |  (LLM generates      |
                |   agent responses)   |
                +----------+-----------+
                           |
                           v
                +----------------------+
                |  Conversation Logs   |
                | (agent + borrower)   |
                +----------+-----------+
                           |
                           v
                +----------------------+
                |      Evaluator       |
                |  - Rule-based score  |
                |  - Optional LLM judge|
                +----------+-----------+
                           |
                           v
                +----------------------+
                |   Score Aggregator   |
                |   Accuracy Analysis  |
                +----------+-----------+
                           |
                           v
                +----------------------+
                |     Final Report     |
                | Pipeline Metrics     |
                +----------------------+


## Part 1 — The Detective

### Goal

Create an evaluator that determines how well the AI agent handled each call.

For every transcript the evaluator produces:

a score (0–100)

problematic agent responses

a verdict: good / bad

Scores all 10 calls and checks accuracy against verdicts.json:

```bash
python detective/evaluate.py
```

Without LLM (deterministic only, faster):

```bash
python detective/evaluate.py --no-llm
```

Single call:

```bash
python detective/evaluate.py --call transcripts/call_03.json
```

Output saved to `results/detective_scores.json`.

**Scoring criteria:** See `detective/criteria.md`
**LLM judge prompt:** See `detective/judge_prompt.txt`

### Results (deterministic scoring)

| Call | Score | Predicted | Human | Match |
|------|-------|-----------|-------|-------|
| call_01 | 93 | good | good | ✓ |
| call_02 | 53 | bad | bad | ✓ |
| call_03 | 40 | bad | bad | ✓ |
| call_04 | 85 | good | good | ✓ |
| call_05 | 73 | good | good | ✓ |
| call_06 | 78 | good | good | ✓ |
| call_07 | 48 | bad | bad | ✓ |
| call_08 | 73 | good | good | ✓ |
| call_09 | 54 | bad | bad | ✓ |
| call_10 | 55 | bad | bad | ✓ |

**Accuracy: 10/10 = 100%** (deterministic scoring, no LLM needed)

---

## Part 2 — The Surgeon

### Goal

Identify flaws in the original system prompt that caused failures.

### Flaws found

See `surgeon/flaw_analysis.md` for full analysis. Summary:

1. **No language persistence** — agent switches language but keeps reverting to English (call_02, call_03, call_07)
2. **No already-paid protocol** — agent loops asking for UTR with no escalation path (call_02, call_03)
3. **Unconditional urgency** — credit score pressure fires even during bereavement (call_02, call_03, call_10)

Fixed prompt: `system-prompt-fixed.md`

### Re-simulate bad calls

```bash
python surgeon/resimulate.py
# or pick specific calls:
python surgeon/resimulate.py --calls call_02 call_03 call_07
```

Output saved to `results/surgeon_comparisons.md`.

---

## Part 3 — The Architect
### Goal

Build a reusable pipeline to evaluate prompts automatically.

This allows rapid prompt iteration and objective comparison.

Score a prompt against all transcripts:

```bash
python pipeline/run_pipeline.py --prompt system-prompt.md --transcripts transcripts/
```

Compare two prompts:

```bash
python pipeline/run_pipeline.py \
  --prompt system-prompt.md system-prompt-fixed.md \
  --transcripts transcripts/
```

With auto-improvement suggestions (bonus):

```bash
python pipeline/run_pipeline.py \
  --prompt system-prompt.md \
  --transcripts transcripts/ \
  --suggest
```

Output saved to `results/pipeline_report.md` and `results/pipeline_scores.json`.

> **Note:** Without `--simulate`, the pipeline scores the *original* transcripts against both prompts — scores will be identical since the transcripts don't change. The real difference shows up with `--simulate` (requires API key), which re-runs each borrower turn through the LLM using the new prompt and scores the simulated responses.

---

## Pipeline Workflow
```
Prompt + Transcripts
        ↓
Conversation Simulation
        ↓
Generated Agent Responses
        ↓
Evaluator
        ↓
Score Aggregation
        ↓
Performance Report
```
Outputs:
```
results/pipeline_report.md
results/pipeline_scores.json
```

## Key Insights

Analysis of the transcripts revealed several systemic issues:

- Agents often fail when borrowers express emotional distress

- Language switching requires explicit persistence rules

- Lack of escalation logic leads to repetitive loops

- Negotiation strategies must adapt to borrower responses

Prompt improvements addressing these issues lead to more natural and effective conversations.

## Repo Structure

```
├── README.md
├── system-prompt.md          # Original (broken) prompt
├── system-prompt-fixed.md    # Fixed prompt
├── transcripts/              # 10 call transcripts
├── verdicts.json             # Human verdicts (ground truth)
├── detective/
│   ├── evaluate.py           # Evaluator script
│   ├── criteria.md           # Scoring criteria (documented)
│   └── judge_prompt.txt      # LLM judge prompt
├── surgeon/
│   ├── flaw_analysis.md      # 3 flaws + transcript evidence
│   └── resimulate.py         # Before/after re-simulation
├── pipeline/
│   └── run_pipeline.py       # Reusable prompt iteration pipeline
└── results/                  # All outputs
```

---

## What I'd do with more time

- Add per-language scoring (Hindi/Tamil calls need language-aware repetition detection)
- Build a regression test suite so prompt changes can't silently break passing calls
- Add a confidence score to each verdict (some calls are borderline)
- Track cost per evaluation run to stay within budget automatically

## Conclusion

This project demonstrates a complete workflow for improving conversational AI systems:

detect failures automatically

diagnose root causes

improve prompt behavior

build infrastructure for continuous evaluation

The resulting pipeline enables safe and scalable prompt iteration for AI agents in production environments.

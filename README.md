# Prompt Engineer Assignment

AI voice agent evaluator, prompt fixer, and iteration pipeline for debt collection calls.

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

## Part 1 — The Detective

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

## Part 3 — The Pipeline

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

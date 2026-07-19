# L52: Auto-Evaluator Reliability — Biases, Calibration, Jury

**Code:** `13_quality/auto_evaluator_reliability.py`
**Reflection:** [`level-52-reflection.md`](../../.claude/learnings/reflections/level-52-reflection.md)

### Level 52: Auto-Evaluator Reliability — Biases, Calibration, Jury
**Goal:** Empirically test the failure modes of LLM-as-judge (verbosity bias, self-preference bias, calibration against a quality spectrum) and show whether a jury of multiple judges reduces variance enough to be trusted in production

**Depends on:** L51 (Evals Methodology — auto-evaluator is the test type this level probes)
**Unlocks:** L54 (Prompt Refactoring — cannot trust the refactoring safety net until the judge itself is calibrated)

**Why this level exists:**
L51 proved the auto-evaluator detects *obvious* quality failures. ThoughtWorks Radar Vol.33 says to "treat this technique with caution" because of position bias, verbosity bias, and self-preference ("a model family favors its own outputs"). Fowler says "evaluate the Evaluator." L52 tests these claims empirically.

**Four hypotheses to prove:**

| Hypothesis | Test |
|-----------|------|
| Verbosity bias: longer responses score higher regardless of quality | Generate equal-accuracy summaries at 3 length tiers; measure score vs length |
| Self-preference bias: same-model judge inflates its own outputs | Compare haiku-judges-haiku vs gemini-judges-haiku scores on same outputs |
| Calibration: judge ranking matches a constructed quality ladder | Build 5-tier quality spectrum with known ranking; verify judge respects it |
| Jury reduces variance: N judges agree more than 1 judge alone | Run 3 judges, measure variance of individual scores vs consensus score |

**Key concepts:**
- ThoughtWorks (Vol.33): "a model family favors its own outputs — and preference leakage, blurring the boundary between training and testing"
- ThoughtWorks (Vol.33): "using LLMs as a jury (employing multiple models for consensus)"
- Fowler: "evaluate the Evaluator to check for false positives and false negatives"
- Evaluator calibration = does the judge's 4/5 reliably mean better than 3/5? Without calibration, scores are ordinal labels, not measurements

**Sources:**
- [ThoughtWorks Radar Vol.33: LLM as a Judge — Assess](https://www.thoughtworks.com/radar/techniques/llm-as-a-judge) ✓ — position bias, verbosity bias, self-preference, jury approach
- [Martin Fowler: Engineering Practices for LLM Application Development](https://martinfowler.com/articles/engineering-practices-llm.html) ✓ — "evaluate the Evaluator"
- [arxiv:2502.01534](https://arxiv.org/abs/2502.01534) — scaling contamination
- [arxiv:2404.18796](https://arxiv.org/abs/2404.18796) — LLMs as jury

---

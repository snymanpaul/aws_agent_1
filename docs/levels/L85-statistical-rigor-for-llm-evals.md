# L85: Statistical rigor for LLM evals

**Code:** `13_quality/eval_significance.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md)

### L85 — Statistical rigor for LLM evals
- **Closes:** zero significance testing; single-run curriculum evals.
- **Builds on:** `evals_methodology.py` (L51), `auto_evaluator_reliability.py` (L52), `evals_harness.py` (L49).
- **Empirical objective:** re-run prior eval comparisons at N≥30 with bootstrap 95% CIs + a significance
  test; add a power analysis (runs needed to detect a given effect).
- **Verify:** report which prior single-run "findings" are significant; **assert at least one prior claim
  is shown NON-significant** (honest negative). **Guardrail:** CIs from real repeated runs, not assumed σ.

# L86: Unified, reusable eval harness (in `tools/`)

**Code:** `tools/eval_harness.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md)

### L86 — Unified, reusable eval harness (in `tools/`)
- **Closes:** 4+ non-composable bespoke harnesses.
- **Builds on:** `adk_patterns/_harness.py` (multi-run+tokens), L49 baseline-diff, L51/L52 judges, L45f RAG.
- **Empirical objective:** one composable harness = datasets + pluggable evaluators + multi-run +
  significance (L85) + cost/latency gating + regression baseline.
- **Verify:** run it over L49+L51+L52 datasets and **reproduce their headline numbers within CI**; assert
  it **gates** a deliberately-regressed prompt on **both** quality and cost. **Guardrail:** must consume
  existing level datasets unmodified (proves generality, not a fresh bespoke fit).

---

# L91: Native Trace-Level Evaluators — Run Locally

**Code:** `13_quality/native_trace_evaluators.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md) (Extension section)

**Status:** Done (extension of the L78–L87 track).

Trace-level evaluators run **locally** via `@eval_task(TracedHandler())` — a plain dict scores 0.00
while a real traced session scores 1.0. This **corrects L35's assumption**: the requirement is a
captured Session, not cloud ADOT. Also verified that `ToolSelectionAccuracy` judges
*appropriateness*, not match-to-`expected_trajectory` — know what your judge actually scores.
Cross-model: a Nova judge scores the same traced session 1.0 (L93).

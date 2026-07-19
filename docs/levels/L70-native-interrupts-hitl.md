# L70: Native Interrupts — Human-in-the-Loop Approval Gates

**Code:** `12_orchestration/interrupts_hitl.py`
**Reflection:** [`level-70-reflection.md`](../../.claude/learnings/reflections/level-70-reflection.md)

**Status:** Done (Tier 19, verified on Gemini 2.5 Flash).

**Empirical findings (probe-validated):** interrupts are fully wired in the SDK —
`event.interrupt(name, reason)` raises (pauses the run) and then returns the human's response on
resume; `event.cancel_tool` enforces a deny; the interrupt is portable JSON keyed by `id`
(`event.interrupt` / `result.interrupts` / resume by id). Supersedes the tool-based checkpoint
pattern of L47 for SDK-native flows.

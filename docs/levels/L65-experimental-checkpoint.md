# L65: Experimental Checkpoint — Contract + Hook Realization

**Code:** `13_state_persistence/checkpoint.py`
**Reflection:** [`level-65-reflection.md`](../../.claude/learnings/reflections/level-65-reflection.md)

**Status:** Done (Tier 19, verified on Gemini 2.5 Flash).

**Empirical finding (probe-validated):** `strands.experimental.checkpoint` is TYPES-ONLY in SDK
v1.42 — `AgentResult` has no `checkpoint` field, nothing sets `stop_reason="checkpoint"`, and there
is no resume parameter. Durable execution was realized instead via `AfterModelCallEvent` /
`AfterToolCallEvent` hooks combined with L64 snapshots. The auto-runtime needs Temporal (see L48).

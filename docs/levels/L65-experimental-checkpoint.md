# L65: Experimental Checkpoint — Contract + Hook Realization

**Code:** `13_state_persistence/checkpoint.py`
**Reflection:** [`level-65-reflection.md`](../../.claude/learnings/reflections/level-65-reflection.md)

**Status:** Done (Tier 19, verified on Gemini 2.5 Flash).

> **Update 2026-07-18:** the finding below was true at SDK v1.42 and is superseded at v1.43+ —
> checkpoint is now a wired runtime (`AgentResult.checkpoint`, `stop_reason="checkpoint"`, resume
> via `checkpointResume`; precedence interrupt > checkpoint > cancel). See the
> [v1.42→v1.48 delta report](../work/research/reports/2026-07-18_strands-ecosystem-delta-v142-to-v148.md)
> §1 and planned L95. The hook-based realization below remains valid as the 1.42-era workaround.

**Empirical finding (probe-validated at v1.42):** `strands.experimental.checkpoint` is TYPES-ONLY in SDK
v1.42 — `AgentResult` has no `checkpoint` field, nothing sets `stop_reason="checkpoint"`, and there
is no resume parameter. Durable execution was realized instead via `AfterModelCallEvent` /
`AfterToolCallEvent` hooks combined with L64 snapshots. The auto-runtime needs Temporal (see L48).

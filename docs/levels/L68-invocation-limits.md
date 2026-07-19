# L68: Invocation Limits

**Code:** `14_token_economics/invocation_limits.py`
**Reflection:** [`level-68-reflection.md`](../../.claude/learnings/reflections/level-68-reflection.md)

**Status:** Done (Tier 18, SDK v1.42).

Per-invocation `Limits(turns / output_tokens / total_tokens)` with a graceful `stop_reason` when a
cap is hit — bounded agent runs as a first-class SDK feature. Builds on L63 (tool offload) in the
token-economics theme.

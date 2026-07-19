# L66: AgentCore Memory — Async Mode + LTM Metadata Filter

**Code:** `14_agentcore_platform/memory_async_ltm.py`
**Reflection:** [`level-66-reflection.md`](../../.claude/learnings/reflections/level-66-reflection.md)

**Status:** Done (Tier 18, AgentCore 1.12 facet).

AgentCore Memory `async_mode` configuration plus `MemoryMetadataFilter` (LTM prefilter, max 5
filters). The end-to-end filtered-retrieval proof (provisioned LTM extraction strategy, filter
discriminates cohorts) is L80 — this level hit the extraction-gated wall that L80's foundation work
(F1) later removed.

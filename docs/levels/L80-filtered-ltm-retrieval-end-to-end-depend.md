# L80: Filtered LTM retrieval, end-to-end (depends on F1)

**Code:** `14_agentcore_platform/ltm_filtered_retrieval.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md)

### L80 — Filtered LTM retrieval, end-to-end (depends on F1)
- **Closes:** `memory_async_ltm.py` extraction-gated gap.
- **Empirical objective:** write episodic events tagged to two cohorts; after extraction, a
  **metadata-filtered** `RetrieveMemoryRecords(filter={cohort=X})` returns only cohort-X records.
- **Verify:** assert filter **discriminates** — returns ≥1 cohort-X record and **zero** cohort-Y.
  **Guardrail:** must fail if the filter is ignored (i.e., a no-op filter returning everything fails).

## Foundation prerequisite

### F1 — Provision AgentCore Memory **with an LTM extraction strategy**
- **Closes:** the L66 extraction-gated wall (filtered retrieval impossible on an STM-only store).
- **Builds on:** `14_agentcore_platform/memory_async_ltm.py`, `11_platform/ltm_streaming.py` (L37 proved
  *unfiltered* retrieval works live).
- **Empirical objective:** create a Memory resource with a configured LTM strategy; write 20 episodic
  events; **after extraction completes, `RetrieveMemoryRecords` returns extracted LTM records** (not the
  `ValidationException: Filter key not valid` from L66).
- **Verify:** assert ≥1 LTM record exists post-extraction AND its `memoryStrategyId` matches the
  provisioned strategy. **Guardrail:** poll for real extraction; do not assert against injected records.

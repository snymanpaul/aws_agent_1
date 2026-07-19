# L81: Long-horizon memory dynamics: consolidation, forgetting, conflict

**Code:** `06_memory/long_horizon_memory.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md)

### L81 — Long-horizon memory dynamics: consolidation, forgetting, conflict
- **Closes:** no accumulation-at-scale, consolidation, eviction, or cross-source conflict resolution.
- **Builds on:** `graph_memory_benchmark.py` (L17 temporal invalidation), F1.
- **Empirical objective:** at N=10/100/1000 memories, measure recall@k + p50/p95 retrieval latency;
  apply consolidation/importance-weighted eviction; inject a contradicting fact.
- **Verify:** (a) plot/record recall+latency vs N (answers the repo's open Q `level-16-reflection.md:163`);
  (b) post-consolidation recall maintained with fewer records; (c) after a contradiction, the **stale
  fact is not returned** (superseded). **Guardrail:** real store growth, real timings — no synthetic curves.

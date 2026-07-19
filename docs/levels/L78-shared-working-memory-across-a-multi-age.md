# L78: Shared working memory across a multi-agent team

**Code:** `06_memory/shared_agent_memory.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md)

### L78 — Shared working memory across a multi-agent team
- **Closes:** zero usage of `Swarm.shared_context` / `GraphState` for real cross-agent memory.
- **Builds on:** `03_multi_agent/swarm_example.py`, `graph_workflow.py`, `artifacts/adk_patterns/p2,p3`.
- **Empirical objective:** Agent A writes a fact to shared memory; Agent B (no prompt-chain edge to A)
  reads it and uses it.
- **Iterations:** (1) `Swarm.shared_context` read/write; (2) `GraphBuilder` shared state across
  non-adjacent nodes; (3) a `SharedMemoryPort` adapter (in-platform) both wrap.
- **Verify:** generate a unique sentinel at runtime, have A write it to the store, assert it appears in
  **B's input + the store** but **not** on any A→B edge. **Guardrail:** sentinel is runtime-random, so a
  hardcoded pass is impossible; assert there is NO direct edge carrying it.

# L82: Durable resume of a multi-agent harness

**Code:** `13_state_persistence/durable_multiagent_resume.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md)

### L82 — Durable resume of a multi-agent harness
- **Closes:** durable resume proven only for a single agent (L65/L70/L48), never a swarm/graph.
- **Builds on:** `checkpoint.py` (L65), `interrupts_hitl.py` (L70), `durable_execution.py` (L48), L78.
- **Empirical objective:** kill a 5-node graph at node 3; resume; nodes 1–3 are **not** re-run and node 4
  sees shared memory from nodes 1–2.
- **Verify:** assert idempotent skip of completed nodes (via an execution ledger) AND shared-memory
  presence in node 4's input. **Guardrail:** real crash (process kill or raised mid-run), not a flag.

---

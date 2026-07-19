# L87: Memory-backed multi-agent harness, agentically graded

**Code:** `06_memory/memory_value_capstone.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md)

### L87 — Memory-backed multi-agent harness, agentically graded
- **Ties both tracks together** — the real proof the original pain is resolved.
- **Builds on:** L78–L82 (memory) + L83–L86 (evals).
- **Empirical objective:** an agentic harness using shared + cross-session memory, graded by the
  trajectory + goal-success + significance stack.
- **Verify:** assert the memory-backed harness **beats a memoryless baseline on goal-success at p<0.05**
  (L85) AND its trajectory quality is judged higher (L83) — across N runs, with the full audit trace
  (L82/`_trace.py`) attached. **Guardrail:** the baseline must be identical except memory disabled.

---

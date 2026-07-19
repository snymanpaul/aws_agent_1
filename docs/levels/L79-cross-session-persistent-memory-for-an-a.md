# L79: Cross-session persistent memory for an agentic harness

**Code:** `06_memory/cross_session_memory.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md)

### L79 — Cross-session persistent memory for an agentic harness
- **Closes:** simulated multi-agent persistence; the quarantined DynamoDB design.
- **Builds on:** un-archive `_archive_hallucinated_l27/dynamodb_persistence.py` **OR** AgentCore Memory
  (F1) + `RepositorySessionManager` (`session_management.py:184-332`).
- **Empirical objective:** a 3-agent task writes memory in **process 1**, which is then **killed**;
  **process 2 (fresh)** recalls it without re-doing the work.
- **Verify:** process 1 writes sentinel + partial result, `kill -9`; process 2 asserts recall of the
  sentinel from the live store. **Guardrail:** separate OS processes (not in-process re-instantiation —
  the `unified_memory.py:1126` trap); store must be external (DynamoDB/AgentCore), not a local dict.

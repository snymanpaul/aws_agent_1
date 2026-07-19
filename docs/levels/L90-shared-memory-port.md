# L90: SharedMemoryPort — Adapters Behind Ports, Executable

**Code:** `14_agentcore_platform/shared_memory_port.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md) (Extension section)

**Status:** Done (extension of the L78–L87 track).

One `SharedMemoryPort` interface, two real adapters (in-process and AgentCore LTM), both passing the
same cross-agent contract test. This makes the architecture recommendation "AgentCore services as
adapters behind your own ports" empirically executable rather than aspirational. Model-agnostic by
construction (store-side; not re-run in L93).

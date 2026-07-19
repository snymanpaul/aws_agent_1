# L63: Tool Result Offload

**Code:** `14_token_economics/tool_offload.py`
**Reflection:** [`level-63-reflection.md`](../../.claude/learnings/reflections/level-63-reflection.md)

**Status:** Done (Tier 17).

`ContextOffloader` with three storage backends (InMemory / File / S3): large tool results are moved
out of the context window and replaced with a reference the agent can dereference on demand.
Demo output lands in `artifacts/l63_demo/` (gitignored — generated payload dumps).

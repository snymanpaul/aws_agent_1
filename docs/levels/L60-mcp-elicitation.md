# L60: MCP Elicitation — Server-Requested User Input

**Code:** `11_2026_updates/mcp_elicitation.py`
**Reflection:** [`level-60-reflection.md`](../../.claude/learnings/reflections/level-60-reflection.md)

**Status:** Done (Tier 16, SDK v1.35).

MCP elicitation: the server side of an MCP integration requests structured input from the user
mid-call, instead of failing or guessing. The inverse direction of L9 (agent consumes MCP tools) and
a protocol-level cousin of L47/L70 human-in-the-loop patterns.

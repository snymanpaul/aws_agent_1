# L64: SDK Snapshots — Selective In-Memory State Capture

**Code:** `13_state_persistence/sdk_snapshots.py`
**Reflection:** [`level-64-reflection.md`](../../.claude/learnings/reflections/level-64-reflection.md)

**Status:** Done (Tier 19, verified on Gemini 2.5 Flash).

`take_snapshot` / `load_snapshot`: selective in-memory agent state capture and restore, JSON
round-trip, and branching (fork a conversation from a snapshot). Contrast with L57 sessions
(auto-managed persistence) — snapshots are explicit and selective.

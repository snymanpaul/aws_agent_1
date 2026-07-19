# L57: Session Management — Providers, Lifecycle Hooks

**Code:** `11_2026_updates/session_management.py`
**Reflection:** [`level-57-reflection.md`](../../.claude/learnings/reflections/level-57-reflection.md)

**Status:** Done (Tier 16, SDK v1.35).

Session providers and lifecycle hooks introduced in SDK v1.35: pluggable session storage
(`RepositorySessionManager` and friends) with hooks on session create/load/save. Contrast with L5
(file/S3 session managers) and the L64 snapshot approach (Tier 19).

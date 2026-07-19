# L92: Ship Gate — One Auditable GO/NO-GO

**Code:** `tools/ship_gate.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md) (Extension section)

**Status:** Done — the synthesis of the whole evals arc.

One auditable **GO/NO-GO** verdict over N real (paid) runs: quality + cost + permutation
significance compose into a single reproducible decision with cited reasons and a JSON verdict
artifact. A good candidate ships; a regressed one is blocked with the evidence attached. This is the
"paid, audit-reproducible gate" the original review-gate question asked for, built from L83–L86.

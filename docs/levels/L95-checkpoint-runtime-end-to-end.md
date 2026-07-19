# L95: Checkpoint Runtime End-to-End

**Code:** `13_state_persistence/checkpoint_runtime.py`
**Reflection:** [`level-95-reflection.md`](../../.claude/learnings/reflections/level-95-reflection.md)

**Status:** Done (Tier 22, 2026-07-18, gemini-2.5-flash, SDK 1.48).

The v1.43-wired checkpoint runtime proven across real OS processes, closing L65's deferred
auto-runtime:

- **Resume loop:** `Agent(checkpointing=True)` pauses twice per tool cycle — observed
  `after_model,0 → after_tools,0 → after_model,1 → after_tools,1` — driven to completion with
  exactly-once tool effects (JSONL ledger).
- **Real crash:** worker SIGKILLed (`rc=-9`) at `after_tools`; a fresh process resumed via
  `{"checkpointResume": {"checkpoint": ...}}` with the same `FileSessionManager` session:
  completed tool NOT re-executed, and a runtime sentinel known only to the dead process appeared
  in the resumed final answer.
- **Negative control:** the same checkpoint without the session fails to recover state
  (`Checkpoint` = position + cycle_index + schema_version, nothing else). Checkpoint says WHERE,
  session says WHAT.
- **Precedence:** a `BeforeToolCallEvent` interrupt during a checkpointing cycle wins —
  `stops=[checkpoint×3, interrupt]` (interrupt > checkpoint). Cancel precedence not exercised
  (no reachable cancel API surface in this setup).
- **Cost note:** two pauses per cycle with no per-boundary opt-out; budget resume round-trips.

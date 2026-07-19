# L58: Sliding Window Per-Turn + Token Tracking

**Code:** `11_2026_updates/sliding_window_tokens.py`
**Reflection:** [`level-58-reflection.md`](../../.claude/learnings/reflections/level-58-reflection.md)

**Status:** Done (Tier 16, SDK v1.35).

The v1.35 `per_turn` sliding-window conversation manager plus token usage tracking across turns.
Connects to L15 (context management) — this is the SDK-native counterpart to the hand-rolled
budget/compression patterns built there.

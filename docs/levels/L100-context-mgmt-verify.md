# L100: Agentic Context Management — Verify the Launch-Post Numbers

**Code:** `13_quality/context_mgmt_verify.py`
**Reflection:** [`level-100-reflection.md`](../../.claude/learnings/reflections/level-100-reflection.md)

**Status:** Done (Tier 22 — the closer, 2026-07-19, gemini-2.5-flash, local). Grounded in the SDK
source (`_context_manager/modes/agentic/agentic_context.py`, `agent.py:_resolve_context_manager`).

Tests the Strands launch post's two headline claims for context management (~55% fewer tokens; 68%→
98% accuracy) against the actual SDK, three ways (`none` = `NullConversationManager` / `auto` /
`agentic`) over an identical long task (a codename stated once, then 8 bloating tool-result turns,
then a recall question), N=5.

| Arm | End context (tokens) | Recall | Model called ctx tools |
|-----|---------------------|--------|------------------------|
| none (`NullConversationManager`) | ~20,600 | 1.00 | — |
| **auto** | **~8,900 (−56%)** | 1.00 | n/a (deterministic) |
| agentic | ~20,600 | 1.00 | **0 / 5 runs** |

**Result — one claim reproduced, one didn't, both grounded:**
- **Token claim ✔ reproduced:** `auto` cut end-of-run context tokens **~56%** (post claimed ~55%).
  Source: `auto` = `SummarizingConversationManager(summary_ratio=0.3, proactive_compression @
  0.85×window)` + `ContextOffloader(1500)` — it compresses **deterministically**, no model
  cooperation needed.
- **Accuracy lift — did NOT reproduce (honest negative):** all three arms recalled the fact 1.00.
  Gemini's real window is 1,048,576 tokens, so the unmanaged conversation still fits and a capable
  model recalls the early fact; the 68→98% degradation regime requires a smaller window or a model
  that degrades on long context. The claim is regime-specific, not universal.
- **`auto` vs `agentic`:** `agentic` injects `summarize_context`/`truncate_context`/`pin_context` +
  a `<context-status>` middleware and leaves compression to the model — and Gemini **never called
  them** (0/5), so its context stayed as large as `none`. Use `auto` for guaranteed token control;
  `agentic` only helps with a model that reliably self-manages.

**Method:** Gemini's 1M window never pressures a modest task, so the pressured regime was reached
transparently by capping the *reported* `context_window_limit` to 16,000 via a `CappedModel`
subclass (the real model unchanged; disclosed in the output) — a legitimate experimental control,
not a simulation.

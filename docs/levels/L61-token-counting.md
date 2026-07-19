# L61: Token Counting + Pre-Call Estimate

**Code:** `14_token_economics/token_counting.py`
**Reflection:** [`level-61-reflection.md`](../../.claude/learnings/reflections/level-61-reflection.md)

**Status:** Done (Tiers 17/19, verified live on Gemini 2.5 Flash).

Async `count_tokens` for look-before-you-leap cost estimates, heuristic vs native.

> **Re-verified 2026-07-18 at SDK 1.48** (`_sandbox/probe_l94_count_tokens.py`): the finding holds.
> With tiktoken installed, `count_tokens` still returns exactly `ceil(chars/4)` on all test strings;
> `models/model.py` at 1.48 contains no tiktoken code path — the "when available" language exists
> only in docstrings. The docstring/code mismatch is upstream, unchanged since 1.42.

**Empirical findings (probe-validated):**
- The base `count_tokens` docstring claims tiktoken `cl100k_base`, but the v1.42 code path is a char
  heuristic (`ceil(chars/4)`).
- Gemini's native count equals the actually billed `inputTokens` exactly.
- The chars/4 heuristic under-counts code by ~40%, CJK by ~50%, punctuation-heavy text by ~75%.

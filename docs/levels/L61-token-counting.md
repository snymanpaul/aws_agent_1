# L61: Token Counting + Pre-Call Estimate

**Code:** `14_token_economics/token_counting.py`
**Reflection:** [`level-61-reflection.md`](../../.claude/learnings/reflections/level-61-reflection.md)

**Status:** Done (Tiers 17/19, verified live on Gemini 2.5 Flash).

Async `count_tokens` for look-before-you-leap cost estimates, heuristic vs native.

**Empirical findings (probe-validated):**
- The base `count_tokens` docstring claims tiktoken `cl100k_base`, but the v1.42 code path is a char
  heuristic (`ceil(chars/4)`).
- Gemini's native count equals the actually billed `inputTokens` exactly.
- The chars/4 heuristic under-counts code by ~40%, CJK by ~50%, punctuation-heavy text by ~75%.

# L62: Bedrock Prompt Caching (TTL) + `strict_tools`

**Code:** `14_token_economics/cache_and_strict.py`
**Reflection:** [`level-62-reflection.md`](../../.claude/learnings/reflections/level-62-reflection.md)

**Status:** Done — demonstrated live after the Bedrock use-case form unlocked Claude.

`CacheConfig.ttl` / `CacheToolsConfig` prompt caching plus Bedrock `strict_tools` on Claude.

**Empirical findings:**
- Bedrock entitlement gotcha: Claude was gated behind an unfilled use-case form
  (`Model use case details have not been submitted`); the `agreementAvailability` metadata was
  misleading — a real Converse call is the truth.
- `strict_tools` is Claude-only: Nova, Llama, and Mistral all reject it.

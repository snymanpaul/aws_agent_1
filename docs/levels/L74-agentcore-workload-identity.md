# L74: AgentCore Workload Identity — Vaulted Secrets

**Code:** `17_agentcore_identity/workload_identity.py`
**Reflection:** [`level-74-reflection.md`](../../.claude/learnings/reflections/level-74-reflection.md)

**Status:** Done (Tier 20, live AWS; self-tearing-down).

**Empirical findings (live-validated):**
- `create_api_key_credential_provider` vaults the key in AWS-managed Secrets Manager; `Get` calls
  return only ARNs, never the raw key.
- `@requires_api_key(provider_name=…)` injects the vaulted key at call time (works locally); the
  sibling `requires_access_token` covers OAuth2 M2M / user federation.
- **Gotcha:** the decorator caches its workload identity in `./.agentcore.json` — a stale cache
  (deleted identity or different account) → `AccessDeniedException`; clear it (gitignored) when
  switching accounts.

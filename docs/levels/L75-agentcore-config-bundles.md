# L75: AgentCore Config Bundles — Versioned Resource Config

**Code:** `18_agentcore_config/config_bundles.py`
**Reflection:** [`level-75-reflection.md`](../../.claude/learnings/reflections/level-75-reflection.md)

**Status:** Done (Tier 20, live AWS; self-tearing-down).

**Empirical findings (live-validated):**
- Config bundle components are keyed by a real resource ARN (a gateway ARN was accepted; a
  workload-identity ARN was rejected).
- Gateway component config shape is `{configuration:{toolOverrides:{tool:{description}}}}` — no
  `document` wrapper.
- create/update = commits (`commitMessage` + `parentVersionIds` + `branchName`) → Git-like version
  lineage; `get_configuration_bundle_version` reads any past version (rollback).
- A minimal gateway (name + role + AWS_IAM + MCP, no target) suffices; the role trusts
  `bedrock-agentcore.amazonaws.com`.

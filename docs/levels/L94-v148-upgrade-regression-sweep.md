# L94: SDK v1.48 Upgrade + Regression Sweep

**Code:** `_sandbox/probe_l94_v148_surface.py`, `_sandbox/probe_l94_count_tokens.py` (no lesson .py — Tier-18 precedent for pure upgrade levels)
**Reflection:** [`level-94-reflection.md`](../../.claude/learnings/reflections/level-94-reflection.md)

**Status:** Done (Tier 22, 2026-07-18).

Upgraded the full stack in one lock refresh: strands 1.42.0 → 1.48.0, tools 0.7.0 → 0.8.4,
bedrock-agentcore 1.12 → 1.18.1, strands-agents-evals 0.1.16 → 1.0.2. Zero lesson-code changes
required.

**Verified at runtime (surface probe, ALL PASS):** `checkpoint` + `cancelled` StopReason literals,
`AgentResult.checkpoint`, interventions (5 hooks, 5 actions), `MemoryManager`, `Storage` protocol
with 3 impls, sandbox namespace (Docker/Ssh in submodules), steering deprecation shim (PEP-562,
warns on name access), evals classic API intact at 1.0.2.

**Regression sweep:** pytest 21/21; `no_sim_check` clean; smoke lessons L70 (interrupts), L64
(snapshots), L68 (limits), L78 (shared memory incl. negative control) all pass on the new stack.

**Findings:**
- **L61 vindicated.** `count_tokens` is `ceil(chars/4)` exactly, with tiktoken installed or
  poisoned — `models/model.py` has no tiktoken code path at 1.48; the "when available" language is
  docstring-only. The delta report's contrary claim was a docstring-read and has been corrected.
- **Alias rot ≠ regression.** `hello_agent.py` 404s because Anthropic retired
  `claude-sonnet-4-20250514`; the proxy `claude-sonnet-4` alias (used by 46 lesson files) needs a
  one-line repoint to `anthropic/claude-sonnet-4-6` in the proxy config (user infra).

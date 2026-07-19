# L96: Interventions — The Control Plane Unified

**Code:** `08_production/interventions_unified.py`
**Reflection:** [`level-96-reflection.md`](../../.claude/learnings/reflections/level-96-reflection.md)

**Status:** Done (Tier 22, 2026-07-18, gemini-2.5-flash, SDK 1.48).

`Agent(interventions=[...])` collapses four separately-taught control stories into one first-party
primitive, each proven live with a runtime side-effect sentinel and a positive/negative control:

- **Deny** (L22 guardrail): destructive tool blocked below the model; marker file absent, while the
  unguarded positive-control call fired.
- **Guide** (L29 steering): a misdirected `temp_celsius` call redirected to `temp_fahrenheit`
  (hits celsius=0, fahrenheit=1). Model-sensitive → cross-model pending.
- **Confirm** (L47/L70 HITL): `HumanInTheLoop(ask=...)` — approved wire executed, denied wire
  blocked.
- **Transform**: a tool argument rewritten in place; the executed value equals the canonical
  rewrite.
- **CedarAuthorization** (vs L33 gateway): the same Cedar policy language enforced **in-process**;
  a per-user policy permitted `alice` (ran=1) and denied `bob` (ran=0).

**Gotchas found (see reflection):** `InterventionHandler` has an abstract `name` property; Cedar
`principal` is a `dict` (`TypeAndId`), not a tuple; Cedar maps a tool call to
`Action::"<tool_name>"` / `Resource::"agent"`; `on_error="deny"` fails closed and can mask config
bugs as authorization denials (debugged by calling `cedarpy.is_authorized` directly).

**Cross-model validated (2026-07-19, Bedrock Nova Lite, `13_quality/crossmodel_nova_l96_l99.py`):**
all four intervention behaviors are **framework-inherent** — Deny/Transform/Cedar hold by
construction (enforcement below the model), and Guide even replicated (Nova re-reasoned to the
correct tool after guidance).

**Deferred:** the a2a `agent_factory` multi-tenancy iteration (shared-agent server leaks caller
context vs `agent_factory` isolation) — needs a live A2A server+client pair; mechanism captured in
the delta report §8, candidate for an L96b / L32 revisit.

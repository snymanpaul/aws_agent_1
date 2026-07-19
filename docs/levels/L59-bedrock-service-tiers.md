# L59: Bedrock Service Tiers — Cost/Latency Control

**Code:** `11_2026_updates/service_tiers.py`
**Reflection:** [`level-59-reflection.md`](../../.claude/learnings/reflections/level-59-reflection.md)

**Status:** Done (Tier 16, SDK v1.35).

Bedrock service-tier selection (standard vs priority-style tiers) as a cost/latency control knob on
the model call itself. Pairs with L55 (SLM routing): tiering is the same trade made at the
infrastructure layer instead of the model-choice layer.

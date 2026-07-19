# L77: ADK Multi-Agent Patterns — Ported to Strands, Verified on Two Models

**Code:** `artifacts/adk_patterns/` (`p1_sequential.py` … `p8_composite.py`, `run_all.py`)
**Reflections:** [`level-77-reflection.md`](../../.claude/learnings/reflections/level-77-reflection.md),
[`level-77-crossmodel-validation-reflection.md`](../../.claude/learnings/reflections/level-77-crossmodel-validation-reflection.md)

**Status:** Done — 8/8 patterns pass on Gemini 2.5 Flash AND 8/8 on Bedrock Claude Haiku 4.5.

Google ADK's eight orchestration patterns (sequential, coordinator, parallel, hierarchical,
generator-critic, iterative refinement, human-in-the-loop, composite) rebuilt on Strands primitives
(Graph + conditions + cycles, Swarm, agents-as-tools) and mechanically verified.

The real documentation lives with the code: `artifacts/adk_patterns/README.md` (pattern-by-pattern
notes) and `HANDOVER.md` (verification protocol). Bedrock run traces are committed in
`artifacts/adk_patterns/traces_bedrock_claude_haiku_2026-06-03/`.

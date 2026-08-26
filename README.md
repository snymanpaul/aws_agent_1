# AWS Strands Agents Learning Project

A progressive learning path through the AWS Strands Agents SDK. 101 levels (L1 to L100, plus L97b), built December 2025 to July 2026, from a basic agent up through multi-agent orchestration, agentic memory, agentic evals, and the AWS AgentCore platform.

The bar is that every lesson runs live against real services, with no substituted integrations and no hardcoded success paths. `tools/no_sim_check.py` is the gate that enforces it. The repo does not fully clear that bar, and the gate says so: a scan reports 56 hits across the 272 tracked Python files it inspects, as of 2026-08-26, down from 133 before the gate's own precision was repaired. Findings that depend on model behaviour were re-run on a second provider before I recorded them as findings.

## How this was built

I did not hand-write 101 lessons, and I am not going to pretend otherwise. The engineering here sits one level up. I used Claude Code as the build harness and taught it, through an iterated instruction set, to draft the learning plan for the topic, execute each level against live services, append every observation to a raw log, and write a per-level reflection covering what broke and why. My role was direction and quality control: setting the anti-simulation bar, auditing claims against the runs behind them, sending back work that could not cite its evidence, and deciding which findings needed validation on a second model before they counted.

The working parts of that method are all in the repo. The instruction set that steers the agent is `CLAUDE.md`. The raw observation log is `.claude/learnings/observations.jsonl`, roughly 900 append-only entries. The per-level write-ups are in `.claude/learnings/reflections/`. The quality gates the agent has to pass are in `tools/`.

The repo therefore serves two purposes: a reference implementation of Strands patterns I can reuse in future projects, and a worked example of directing an AI agent through a months-long engineering programme with evidence standards enforced by tooling rather than trust.

## What came out of it

**Provider portability.** Google's ADK ships a dedicated class per orchestration pattern. Strands covers the same eight patterns (sequential, coordinator, parallel, hierarchical, generator-critic, iterative refinement, human-in-the-loop, composite) with a few primitives: Graph with conditions and cycles, Swarm, and agents-as-tools. I rebuilt all eight on Strands and ran them on Gemini 2.5 Flash and on Bedrock Claude Haiku. The patterns held on both models. The Bedrock run traces are committed in `artifacts/adk_patterns/`.

**Reproducibility.** Setting temperature to 0 did not make agent runs reproducible once tools and multi-turn state were involved. Typed structured outputs, capped loops, and explicit guard conditions in the control flow around the model did far more for run-to-run stability than any sampling setting.

**Anti-simulation enforcement.** `no_sim_check.py` flags substitute-object vocabulary, fake-success returns, deferral comments, and a `return True` straight out of an `except`. The tests themselves are built so they cannot pass by accident: runtime sentinels that only the real service can produce, real process crashes for the durability lessons, and paired positive and negative controls on every evaluator.

The gate went untested for most of its life, which is its own lesson. When it was finally given the positive and negative controls it demands of everything else (`tests/test_no_sim_check.py`, 56 tests), it turned out to have both poor precision and poor recall: it fired on comments describing deliberate fault injection, while missing `class MockSQSQueue` and `mock_client` entirely because `\b` does not match before a capital or an underscore. Repairing it took repo-wide hits from 133 to 56 and, on the way, surfaced six genuine substituted integrations in L23 that had been sitting under the radar. Precision and recall of your own tripwire are worth measuring before you trust a green run.

**Agentic memory.** The memory track (L78 onward) covers shared cross-agent memory, cross-session persistence on DynamoDB, filtered long-term retrieval on AgentCore Memory, long-horizon dynamics (consolidation, forgetting, conflict), and durable multi-agent resume after a real crash. Stores sit behind hexagonal ports so they are swappable. The capstone measured the effect: 1.00 goal success with memory against 0.00 without, p = 0.0003 by permutation test.

**Trajectory-level evals.** Most of the agent failures I hit showed up in the trajectory, meaning which tools were called, in what order, and with what arguments, rather than in the final answer. The evals track grades tool selection, ordering, and argument correctness (L83) and multi-turn goal success against real state (L84), with Wilson confidence intervals and permutation significance on every claim (L85). These compose into `tools/eval_harness.py` and terminate in `tools/ship_gate.py`, which produces a single audit-reproducible GO/NO-GO verdict over real paid runs.

**Negative results.** Gemini 2.5 Flash was robust to a blatant prompt injection I expected to succeed. Adding more retrieval sources did not improve answer quality. Both are documented with the runs behind them.

## Cross-model validation

Model-sensitive findings were re-run on a second provider: Bedrock Claude Haiku 4.5 for the ADK patterns, Bedrock Nova Lite for the memory and evals tracks. Each finding is labelled framework-inherent (held on the second model) or model-specific (did not). Capability failures on the weaker model are recorded as such rather than counted against the framework.

## Layout

| Area | Levels | Where |
|------|--------|-------|
| Fundamentals: agents, tools, sessions | L1 to L5 | `01_basics/`, `02_intermediate/` |
| Multi-agent: swarm, graph, debate, meta-agents | L6 to L20 | `03_multi_agent/`, `07_advanced_multiagent/` |
| Production: observability, safety, recovery, AgentCore deploy | L21 to L27 | `08_production/`, `10_production/` |
| Platform and orchestration: ReWOO, reflexion, hybrid DAGs, HITL | L28 to L50 | `11_platform/`, `12_orchestration/` |
| Quality and evals | L51 to L56, L83 to L92 | `13_quality/` |
| Token economics and state persistence | L57 to L68 | `14_token_economics/`, `13_state_persistence/` |
| AgentCore platform: memory, registry, tools, identity, AG-UI | L66 to L76 | `14_` through `19_agentcore_*/` |
| ADK multi-agent patterns ported to Strands, verified on two models | L77 | `artifacts/adk_patterns/` |
| Agentic memory and evals, cross-model capstone | L78 to L93 | `06_memory/`, `13_quality/`, `tools/` |
| v1.48 ecosystem delta: upgrade sweep, checkpoint runtime, interventions, memory rematch, sandbox tiers, red-team, context management | L94 to L100, plus L97b | `12_orchestration/`, `13_quality/`, `06_memory/` |
| Unit tests for the quality gates themselves | n/a | `tests/` |

Every lesson has its own doc in `docs/levels/` (one file per level, `L01` to `L100`, plus `L97b`). `LEARNING_PLAN.md` is the master index; `LEARNING_PLAN_agentic_memory_evals.md` is the track overview for the memory and evals arc. Each level also has a lessons-learned write-up in `.claude/learnings/reflections/`, including what went wrong.

## Running it

```bash
uv sync                                    # Python 3.13+, uv
uv run python 01_basics/hello_agent.py     # simplest agent
uv run pytest                              # tests
uv run python tools/no_sim_check.py $(git ls-files '*.py')   # anti-simulation gate
```

Model access goes through an OpenAI-compatible LiteLLM proxy on `localhost:4000` (mine runs as a Podman container). `tools/get_model` resolves aliases to whatever the proxy serves. The AgentCore levels need AWS credentials with the policies in `10_production/l27_agentcore/iac_policy.json`.

If you are working in this repo with an AI coding agent, `CLAUDE.md` carries the runtime setup and the non-obvious rules. This README is the human overview.

## Resources

- [Strands Agents documentation](https://strandsagents.com/latest/)
- [Strands SDK on GitHub](https://github.com/strands-agents/sdk-python)
- [Strands samples](https://github.com/strands-agents/samples)

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# AWS Agent Learning Project

Progressive learning path for AWS Strands Agents SDK.

**Status**: 101 levels, L1–L100 plus L97b (Dec 2025 – Jul 2026). Tier 22 (L94–L100) complete:
v1.48 upgrade sweep, checkpoint runtime, unified interventions, memory rematch, sandbox tiers,
red-team, context management. Per-level docs: `docs/levels/` (one file per lesson). See also
`LEARNING_PLAN_agentic_memory_evals.md`, `LEARNING_PLAN_v148_impact.md`, `NEXT_STEPS_PLAN.md`,
and `.claude/learnings/reflections/`.

**Gate status (2026-08-26)**: `no_sim_check` reports **0 hits over 277 tracked `.py` files**,
and CI enforces it on every push (`.github/workflows/gates.yml`) alongside `check_no_aws_ids`
and `uv run pytest` (132 tests). The pre-commit hook runs both tripwires over staged files.
Keep it at zero: any file you touch must come out clean, and a justified exception takes a
trailing `# nosim:ok <reason>`, never a quiet reword of working code.

## Quick Start

```bash
# Ensure the LiteLLM proxy is running: it's a PODMAN container named `litellm-proxy` (podman, not docker)
podman start litellm-proxy && curl -s localhost:4000/health/liveliness   # expect HTTP 200

# Run any level
uv run python 01_basics/hello_agent.py

# Run tests
uv run pytest
```

## Project Structure

```
01_basics/          # L1-3: hello world, tools, custom tools
02_intermediate/    # L4-5: system prompts, sessions
03_multi_agent/     # L6-8: agents-as-tools, swarm, graph
04_production/      # L9-10: MCP integration, AgentCore basics
05_advanced/        # L11-13: reflection, structured outputs, RAG
06_memory/          # L14-17 + agentic memory (L78+): shared, cross-session, long-horizon, capstone
07_advanced_multiagent/  # L18-20: debate, planning, meta-agents
08_production/      # L21-23: observability, safety, error recovery
09_cutting_edge/    # L24-26: tool synthesis, self-improving, research capstone
10_production/      # L27: AWS AgentCore deployment
11_platform/        # L28-40: SDK advances, streaming, TypeScript, edge
11_2026_updates/    # L57-60: session mgmt, sliding window, service tiers, MCP elicitation
12_orchestration/   # L41-50 + L70: ReWOO, reflexion, hybrid, evals harness, native interrupts/HITL
13_quality/         # L51-56 + agentic evals (L83+): trajectory, goal-success, significance
13_state_persistence/   # L64-65, L82: SDK snapshots, checkpoint, durable multi-agent resume
14_token_economics/     # L61-63, L68: token counting, prompt caching, tool offload, invocation limits
14_agentcore_platform/  # L66, L69 + LTM-filtered retrieval: AgentCore memory, payments (x402)
15_agentcore_registry/  # L71: agent registry (publish/discover skill bundles)
16_agentcore_tools/     # L72-73: managed code interpreter, headless browser
17_agentcore_identity/  # L74: workload identity (vaulted secrets)
18_agentcore_config/    # L75: config bundles (versioned resource config)
19_agentcore_agui/      # L76: AG-UI native (serve_ag_ui)
artifacts/          # L77 ADK patterns + review-gate architecture (verified on Gemini + Bedrock)
docs/levels/        # One doc per lesson, L01-L100 + L97b (linked from LEARNING_PLAN.md tables)
tools/              # get_model (repo-specific model aliases) + install_hooks.sh
packages/agent-build-gates/  # the quality gates, extracted as an installable package
```

## Model Helper

```python
from tools import get_model
from strands import Agent

model = get_model("claude-sonnet-4")  # or haiku, opus, gemini-flash
agent = Agent(model=model, tools=[...])
```

## Available Models (aliases resolved by `tools/get_model`)

| Alias | Model | Use Case |
|-------|-------|----------|
| `claude-sonnet-4` | Claude Sonnet 4 | General, tool-use |
| `claude-opus-4` | Claude Opus 4 | Complex reasoning |
| `haiku` | Claude Haiku 4.5 | Fast iterations |
| `gemini-flash` | Gemini 2.5 Flash | Fast alternative |

Claude aliases route via the LiteLLM proxy at `localhost:4000`; `gemini*` goes direct to Google AI (needs `GEMINI_API_KEY`).

## Quality Gates (`packages/agent-build-gates/`)

The four gates live in a workspace package with their own version and 111 tests, installable
elsewhere (`pip install agent-build-gates`, zero dependencies). Invoke them by console script,
not by path. `tools/` now keeps only `models.py` (this repo's model aliases) and `install_hooks.sh`.

- `no-sim-check`: tripwire for substituted integrations. Flags substitute-object vocabulary
  (mock/stub/fake/dummy/hardcoded), fake-success returns, "in production this would" deferrals, and
  `return True` straight out of an `except`. Run on new lessons: `uv run no-sim-check <path>`;
  repo-wide use `$(git ls-files '*.py')`, because pointing it at `.` also sweeps `.venv`.
  Two scoping rules, both learned from classifying every hit in the repo and both pinned by tests:
  boundaries break on underscores and CamelCase humps, so
  `MockSQSQueue` / `mock_client` / `_simulate_human_response` are caught; and the two vocabulary
  rules do not fire on comments or docstrings, because prose cannot fake an integration. Escape a
  justified line with a trailing `# nosim:ok <reason>`.
- `eval_harness`: composable evals: datasets + evaluators + multi-run + Wilson/bootstrap CIs +
  permutation significance + token/latency cost gate + regression baseline. `run_suite` takes an
  injectable `run_fn`, so it never assumes a framework.
- `ship-gate`: one auditable GO/NO-GO verdict over real runs (the "paid, audit-reproducible gate").
  Needs the `[strands]` extra; `run_fn` is injectable so the verdict logic is testable unpaid.
- `sh tools/check_doc_sync.sh`: two research reports under `docs/work/research/reports/` are
  adapted from raw research in the sibling `aws_data_engineering/docs` directory, which is not
  under version control. They are not byte-identical by design. This reports when a source has
  changed and its report has not; reconcile, then `--update` to re-record. Run it before trusting
  either report, and after editing one. It exits 0 when the sibling directory is absent, so CI is
  unaffected. Override the location with `DATA_ENG_DOCS`.
- `check-no-aws-ids`: **BINDING RULE: never put AWS account info (12-digit account ids, `AWSAdministratorAccess-*` / SSO profile strings, account-bearing ARNs) in ANY `.md` or `.py` file.** This tripwire blocks it; install the pre-commit hook once per clone with `sh tools/install_hooks.sh`. Account ids belong only in local, gitignored config (`~/.aws`, `.claude/settings.local.json`), never in tracked files. A line that must legitimately carry an account-shaped string (this gate's own tests, docs describing the patterns) takes `noaws:ok` anywhere on it, which works as `# noaws:ok reason` in Python and `<!-- noaws:ok reason -->` in Markdown, and covers only that line.

**Anti-simulation is non-negotiable** (enforced by `agent_build_gates.no_sim_check`): every lesson is
structurally un-fakeable (runtime sentinels, real services, real crashes, positive/negative controls)
and must pass `no_sim_check`. The repo is at zero and CI keeps it there, so **a new hit is a
regression, not a backlog item.** When classifying one, open the flagged function rather than
judging from the gate's 100-character summary: the discriminator is whether a real call was
available and skipped. A helper that genuinely raises is fault injection and legitimate; code
that fabricates a success is not.

**`ship_gate.py` is a manual release step**, not part of CI, because it spends money. Run it
against a candidate before shipping: `podman start litellm-proxy && uv run ship-gate`.

## Critical Non-Obvious Rules

### Model Provider
Use `OpenAIModel` with `base_url` for LiteLLM, **not** `LiteLLMModel`:
```python
from strands.models.openai import OpenAIModel
model = OpenAIModel(model_id="claude-sonnet-4", client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"})
```

### LiteLLM proxy runs on PODMAN: diagnose before declaring it "down"
The proxy is a **long-lived podman container named `litellm-proxy`** bound to `127.0.0.1:4000`, with its config mounted from `~/Code/litellm-proxy/litellm_config.yaml` (that repo has its own CLAUDE.md). Manage it with **podman, not docker**: don't `docker compose` from that dir.
```bash
podman ps -a | grep litellm    # check state: do NOT truncate `podman ps` output; the container sorts low
podman start litellm-proxy      # restart if "Exited"; exit 137 = OOM-killed (machine is only ~2GB)
curl -s localhost:4000/health/liveliness   # HTTP 200 = ready
```
- **Gemini routes through the proxy too** (this is the OpenAIModel→compat→Gemini path):
  `OpenAIModel(model_id="gemini-2.5-flash", client_args={"base_url":"http://localhost:4000","api_key":"sk-local"})`.
  (`tools/get_model` instead sends `gemini*` DIRECT to Google AI and needs `GEMINI_API_KEY`/`LESSON_DOTENV`.)
- **Claude models may 400 "credit balance too low"** → fall back to `gemini-2.5-flash`.
- A single failed curl or a truncated `podman ps` is NOT evidence the proxy is gone. Check container state and `podman start` first.

### Streaming
Strands streams by default. For clean output: `Agent(..., callback_handler=None)` then `print(result)`.

### MCP Integration
Always use real MCP calls, never simulate/comment out. Use `MCPClient(lambda: stdio_client(params))` with `prefix` param for multiple servers.

### New AWS Service: Probe First
Before writing any implementation against a new AWS service:
1. `_sandbox/probe_<level>_shapes.py`: enumerate operation input/output shapes via `service_model`
2. `_sandbox/probe_<level>_state.py`: query live state of existing resources
3. Check IAM role policies on any role that will call the new service
Then code. Guessing API syntax costs more time than probing. (Lesson: L33, 8 failures.)

### AgentCore Deployment
Use `BedrockAgentCoreApp` from `bedrock_agentcore`, do **not** manually create FastAPI apps with `/invocations`. Requires `POST /invocations` + `GET /ping` on port 8080.

### Streaming Swarm
Use positional args: `Swarm([a1, a2], ...)`. Set `repetitive_handoff_detection_window` to prevent ping-pong loops.

### Thread Safety
Create a fresh `Agent` per thread in parallel execution: agents are not thread-safe.

## Knowledge Persistence

```
.claude/learnings/
├── observations.jsonl      # Append-only raw observations
└── reflections/            # Per-level summaries (L1-93)
```

Use `/reflect` command after completing a level to ensure JSONL observation capture (manual reflection misses this).

## Resources

- [Strands Docs](https://strandsagents.com/latest/) | [GitHub](https://github.com/strands-agents/sdk-python)
- `LEARNING_PLAN.md` (master index, links per level) + `docs/levels/` (one doc per lesson, L01–L100 + L97b) +
  `LEARNING_PLAN_agentic_memory_evals.md` (memory/evals track overview)

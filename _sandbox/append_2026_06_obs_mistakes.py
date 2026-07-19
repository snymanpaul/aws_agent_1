"""Append the MISTAKE / QUESTION / extra INSIGHT observations from the 2026-06
session (the failed approaches are the highest-value empirical learning).
Each is grounded in an actually-executed run this session.
    uv run python _sandbox/append_2026_06_obs_mistakes.py
"""
import json
import os
from datetime import datetime, timedelta, timezone

LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   ".claude", "learnings", "observations.jsonl")
base = datetime.now(timezone.utc)

OBS = [
    dict(level=64, cat="mistake", topic="misdiagnosed-import-hang-chain",
         obs="On a strands import that hung at 0% CPU, I burned ~hours hypothesis-chaining: iCloud-eviction (wrong — `find -name '*.icloud'`=0), OpenTelemetry (wrong — OTEL_SDK_DISABLED=true no change), orphaned procs (wrong), corrupt __pycache__ (wrong), botocore. The decisive tools were macOS `sample <pid>` (stack stuck in _io_FileIO_readall_impl->read) + `lsof -p <pid>` (fd 3r = the freshly-written .pyc). FIX FIRST-MOVE: on a 0%-CPU process hang, run `sample`+`lsof` on the live PID before any hypothesis.",
         ctx="L64 verification kept timing out; user had to run it in a fresh window before I escalated to live-process inspection.",
         entities=["debugging", "sample", "lsof", "import-hang", "hypothesis-chaining"]),
    dict(level=7, cat="mistake", topic="multiagentplugin-missing-super-init",
         obs="MonitoringPlugin(MultiAgentPlugin) with a custom __init__ crashed at Swarm construction: AttributeError 'MonitoringPlugin' object has no attribute '_hooks' (multiagent_registry._register_hooks reads plugin.hooks->self._hooks). Cause: my __init__ didn't call super().__init__(), which is where the base auto-discovers @hook methods into self._hooks. The SDK docstring example omits __init__ entirely, so the requirement wasn't obvious. FIX: super().__init__() first in any plugin subclass __init__.",
         ctx="L7 swarm_example.py first run failed; one-line fix then 8 node events fired.",
         entities=["MultiAgentPlugin", "super-init", "_hooks", "subclassing"]),
    dict(level=34, cat="mistake", topic="assumed-datasetclient-usable-on-pinned-botocore",
         obs="Assumed bedrock-agentcore DatasetClient was usable; create_dataset is ABSENT from botocore 1.43.2's bedrock-agentcore-control model (hasattr=False; only Evaluator+OnlineEvaluationConfig ops). Present at 1.43.19. SDK bundles no model. Second trap: `uv run` re-syncs the env to the lockfile, REVERTING ad-hoc `uv pip install` — had to test the upgrade via `.venv/bin/python` directly. FIX: bump boto3/botocore>=1.43.19.",
         ctx="L34 probe: hasattr(cp_client,'create_dataset') False at 1.43.2, True at 1.43.19.",
         entities=["botocore", "DatasetClient", "uv-run-resync", "service-model"]),
    dict(level=34, cat="mistake", topic="assumed-datasets-feed-evaluate",
         obs="Plan premise 'DatasetClient -> feed the on-demand evaluate' is wrong. Probing the bedrock-agentcore-control model: NO operation (besides Dataset CRUD) references a datasetId; CreateOnlineEvaluationConfig.dataSourceConfig uses cloudWatchLogs. Datasets are standalone curated eval-example resources (golden sets), not evaluate inputs. Lesson: verify how a new resource is CONSUMED, don't assume the obvious wiring.",
         ctx="L34 probe_l34_example_shapes.py — scanned every op input for 'dataset'.",
         entities=["dataset", "evaluate", "api-wiring", "assumption"]),
    dict(level=34, cat="pattern", topic="api-error-as-schema-oracle",
         obs="Discovered the undocumented PREDEFINED_V1 example schema by iterative create_dataset calls, reading each ValidationException: datasetName regex [a-zA-Z][a-zA-Z0-9_]{0,47} -> 'scenario_id' required -> 'turns' required -> turns[0].'input' required -> turns[0].'expected_output' -> ACTIVE. Live-API validation errors are a fast, reliable schema-discovery oracle when the shape is undocumented (each call narrows it).",
         ctx="L34 — 5 create_dataset attempts converged on {scenario_id, turns:[{input, expected_output}]}.",
         entities=["schema-discovery", "ValidationException", "CreateDataset", "empirical"]),
    dict(level=66, cat="mistake", topic="async-mode-wrong-call-shape",
         obs="Plan's `AgentCoreMemorySessionManager(async_mode=True)` is wrong: async_mode is a field on AgentCoreMemoryConfig (BaseModel, default=False), passed as the manager's first positional arg (agentcore_memory_config=). Verified: inspect.signature shows no async_mode on the manager; config.py:100 defines it. Async mode requires invoking via stream_async/invoke_async.",
         ctx="Step-0 import-smoke flagged async_mode param=False on the manager; grep of config.py confirmed the field.",
         entities=["AgentCoreMemorySessionManager", "AgentCoreMemoryConfig", "async_mode"]),
    dict(level=15, cat="insight", topic="proactive-compression-needs-explicit-window",
         obs="proactive_compression fires when projected_input_tokens / model.context_window_limit >= threshold. The hook reads model.context_window_limit; OpenAI/LiteLLM and Gemini do NOT auto-populate it (falls back to a large DEFAULT_CONTEXT_WINDOW_LIMIT + warns), so the threshold never trips in a demo. MUST set context_window_limit explicitly on the model. Verified: limit=3000 + ~2400-token history -> hook fired, history 20->13 before the call.",
         ctx="L15 Iter 9 — added context_window_limit passthrough to get_model.",
         entities=["proactive_compression", "context_window_limit", "BeforeModelCallEvent"]),
    dict(level=0, cat="mistake", topic="litellm-postgres-rabbithole",
         obs="Spent effort diagnosing litellm's Postgres (zeroed PG_VERSION) + OOM-loop (RestartCount=9, 2GB VM) before realizing the proxy does not NEED Postgres at all — it is only for optional spend/keys/UI. Running litellm DB-less (no DATABASE_URL) sidesteps the whole problem. Lesson: question whether a bundled dependency is even required before debugging it.",
         ctx="User prompt 'why does a small proxy need 1GB postgres?' triggered the reframe.",
         entities=["litellm", "postgres", "yagni", "podman"]),
    dict(level=0, cat="mistake", topic="gemini-2.0-flash-retired-at-runtime",
         obs="get_model's 'gemini-flash' alias pointed at gemini-2.0-flash, which Google RETIRED — failed only at call time (404 'no longer available'), not at construction. User flagged it. FIX: alias -> gemini-2.5-flash (a thinking model; ~19 reasoning tokens overhead on small replies, relevant to L64 output_token caps).",
         ctx="First L64 run on Gemini hit the 404 via the litellm log.",
         entities=["gemini-2.0-flash", "gemini-2.5-flash", "model-retirement"]),
    dict(level=66, cat="question", topic="ltm-strategy-on-existing-memory",
         obs="Does the existing ACTIVE memory l27agentcore_Memory-9RYaOkDitt have an LTM strategy + extracted memories carrying metadata? Needed to decide whether L66 can demonstrate MemoryMetadataFilter doing REAL filtering, or only the API call + the <=5-filter ValueError constraint (LTM extraction latency makes live end-to-end filtering slow/flaky to verify).",
         ctx="L66 not yet built; reusing the L27 memory to avoid slow provisioning.",
         entities=["AgentCore-Memory", "LTM", "MemoryMetadataFilter", "verification"]),
    dict(level=27, cat="question", topic="header-forwarding-needs-redeploy",
         obs="Does verifying runtime header forwarding (context.request_headers + is_forwardable_header) and the class-based @app.entrypoint require REDEPLOYING the L27 AgentCore runtime, or can it be exercised against the already-deployed l27agentcore_Agent-8SQjr5BSN3 + a local BedrockAgentCoreApp test? Determines P2.7 cost.",
         ctx="P2.7 not yet built.",
         entities=["AgentCore-runtime", "header-forwarding", "redeploy", "entrypoint"]),
]

with open(LOG, "a", encoding="utf-8") as f:
    for i, o in enumerate(OBS):
        rec = {"ts": (base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "repo": "aws_agent_1", **o}
        f.write(json.dumps(rec) + "\n")

by_cat = {}
for o in OBS:
    by_cat[o["cat"]] = by_cat.get(o["cat"], 0) + 1
print(f"appended {len(OBS)} observations: {by_cat}")

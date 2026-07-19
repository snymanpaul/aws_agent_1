"""Append 2026-06 session observations to .claude/learnings/observations.jsonl.

Each observation is grounded in an actually-executed run/probe this session
(empirical-only rule). Run once:
    uv run python _sandbox/append_2026_06_obs.py
"""
import json
import os
from datetime import datetime, timedelta, timezone

LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   ".claude", "learnings", "observations.jsonl")

base = datetime.now(timezone.utc)

OBS = [
    dict(level=64, cat="insight", topic="pyc-read-stall-hang",
         obs="strands lessons hung at 0% CPU forever in a read() syscall during import. macOS `sample <pid>` showed the stack stuck in _io_FileIO_readall_impl->read; `lsof -p` named fd 3r = tools/__pycache__/__init__.cpython-313.pyc. Raw `cat` of every module file was instant (0.01s), so it was NOT file content — it was the FRESHLY-WRITTEN .pyc bytecode under iCloud-synced ~/Documents stalling on read (iCloud/EDR intercept of new files). Fix: PYTHONDONTWRITEBYTECODE=1 -> import tools OK in 1.04s.",
         ctx="Cost ~hours misdiagnosing as iCloud-eviction(.icloud placeholders=0), OTel(OTEL_SDK_DISABLED no help), stray procs, corrupt pycache. Lesson: on a 0%-CPU import hang, go straight to `sample <pid>` + `lsof -p <pid>`.",
         entities=["pyc", "PYTHONDONTWRITEBYTECODE", "icloud", "import-hang", "sample", "lsof"]),
    dict(level=64, cat="pattern", topic="invocation-limits-verified",
         obs="strands.types.Limits(turns/output_tokens/total_tokens) verified end-to-end on Gemini 2.5 Flash: hitting a cap RETURNS a result (no exception) with result.stop_reason in {limit_turns, limit_total_tokens, limit_output_tokens}. Per-invocation reset confirmed (same agent, two runs, both hit turns=2). Priority on simultaneous trip confirmed: Limits(turns=1, output_tokens=1) -> stop_reason 'limit_turns' (turns > total > output). Limits(turns=0) -> TypeError. Passed via agent(prompt, limits=...) on __call__/invoke_async/stream_async.",
         ctx="L64 14_token_economics/invocation_limits.py run 2026-06-02 (4 iterations, exit 0).",
         entities=["Limits", "stop_reason", "agent-loop", "strands-1.42"]),
    dict(level=66, cat="insight", topic="async-mode-is-config-field-not-ctor-kwarg",
         obs="AgentCoreMemorySessionManager has NO async_mode constructor kwarg (probe: inspect.signature shows async_mode param=False). Async is enabled via the config object: self.config.async_mode (session_manager.py:939), i.e. AgentCoreMemoryConfig(..., async_mode=True). The plan's `AgentCoreMemorySessionManager(async_mode=True)` is wrong. Async mode requires invoking via stream_async/invoke_async (offloads sync boto3 via asyncio.to_thread).",
         ctx="Step-0 import-smoke probe + grep of installed bedrock_agentcore 1.12.0 session_manager.py. Correction needed before building L66.",
         entities=["AgentCoreMemorySessionManager", "async_mode", "AgentCoreMemoryConfig", "stream_async"]),
    dict(level=34, cat="insight", topic="dataset-api-needs-botocore-1.43.19",
         obs="bedrock-agentcore DatasetClient.create_dataset fails on the locked botocore 1.43.2: hasattr(cp_client,'create_dataset')=False; CreateDataset absent from the service model (only Evaluator + OnlineEvaluationConfig ops present). At botocore 1.43.19 hasattr=True and the full dataset op set appears (CreateDataset, AddDatasetExamples, CreateDatasetVersion, Get/List/Delete...). bedrock-agentcore bundles NO botocore json model (relies on public botocore). Fix: bump boto3/botocore pins >=1.43.19.",
         ctx="Probed via .venv/bin/python (uv run reverts ad-hoc installs to the lock). L34 DatasetClient extension was blocked until the bump.",
         entities=["DatasetClient", "botocore", "create_dataset", "bedrock-agentcore-control"]),
    dict(level=34, cat="insight", topic="datasets-not-wired-to-evaluate",
         obs="No bedrock-agentcore-control operation (besides Dataset CRUD) references a datasetId. CreateOnlineEvaluationConfig.dataSourceConfig uses cloudWatchLogs, NOT a dataset. CreateDataset.source is inlineExamples|s3Source, schemaType in {AGENTCORE_EVALUATION_PREDEFINED_V1, AGENTCORE_EVALUATION_SIMULATED_V1}. So datasets are STANDALONE curated eval-example resources (golden datasets), NOT fed into runtime.evaluate via an id. The plan's premise ('DatasetClient -> feed the on-demand evaluate') is incorrect; the lesson should demonstrate the dataset lifecycle (create/examples/version/delete) instead.",
         ctx="Probe _sandbox/probe_l34_example_shapes.py against bedrock-agentcore-control service model (botocore 1.43.19), us-east-1.",
         entities=["dataset", "evaluate", "OnlineEvaluationConfig", "schemaType", "inlineExamples"]),
    dict(level=7, cat="insight", topic="multiagentplugin-must-call-super-init",
         obs="A MultiAgentPlugin subclass that defines its own __init__ MUST call super().__init__(), else self._hooks is never populated and the orchestrator raises AttributeError '_hooks' at multiagent_registry._register_hooks. After the fix, MonitoringPlugin (@hook on Before/AfterNodeCallEvent, event.node_id) fired 8 node-lifecycle events on BOTH a Swarm (plugins=[...]) and a Graph (GraphBuilder.set_plugins([...])). Orchestrator-level (node lifecycle) vs L30 AgentSkills agent-level Plugin (BeforeInvocationEvent + @tool).",
         ctx="L7 swarm_example.py + L8 graph_workflow.py runs on Gemini 2.5 Flash 2026-06-02, both Status.COMPLETED.",
         entities=["MultiAgentPlugin", "super-init", "_hooks", "BeforeNodeCallEvent", "Swarm", "GraphBuilder"]),
    dict(level=22, cat="pattern", topic="tools-070-security-hardening",
         obs="strands-agents-tools 0.7.0 tool defenses (verified 9/9 offline + in L22): calculator.parse_expression/_validate_expression_ast walks the AST against an allowlist and raises ValueError 'unsupported syntax Attribute' on (1).__class__.__bases__[0].__subclasses__() BEFORE eval, while 2+3*4 still evaluates to 14; use_aws.redact_sensitive_values replaces 16 SENSITIVE_RESPONSE_KEYS values with **REDACTED** (incl. nested) and 17 SENSITIVE_OPERATIONS are consent-gated even when non-mutating; cron._sanitize_cron_line collapses CR/LF so one crontab line can't smuggle a second entry.",
         ctx="_sandbox/probe_l22_tool_security.py + L22 Iteration 13 run 2026-06-02.",
         entities=["calculator", "use_aws", "cron", "AST-sandbox", "redaction", "tools-0.7.0"]),
    dict(level=0, cat="pattern", topic="litellm-dbless-for-small-vm",
         obs="LiteLLM bundles Postgres only for OPTIONAL features (spend logs, virtual keys, admin UI). Lessons authenticate with sk-local + read models from config.yaml, needing none of it. The compose's Postgres OOM-looped (RestartCount=9, OOMKilled=true) in the 2GB podman VM (5 other containers held ~1GB). Running litellm standalone via `podman run` WITHOUT DATABASE_URL -> DB-less proxy, healthy in seconds, routes Gemini. Old corrupt PG data preserved (renamed) at litellm-proxy/data/postgres.corrupt.bak.20260602.",
         ctx="Infra fix 2026-06-02; verified GET :4000/health/liveliness + a real gemini-2.5-flash completion through the proxy.",
         entities=["litellm", "podman", "postgres", "OOM", "DB-less"]),
    dict(level=0, cat="pattern", topic="gemini-direct-course-switch",
         obs="Anthropic/Claude budget exhausted 2026-06-02 -> whole course switched to Gemini 2.5 Flash. gemini-2.0-flash is RETIRED (Google returns 404 'no longer available'); use gemini-2.5-flash. tools/get_model now routes any 'gemini*' model DIRECT to Google AI (strands GeminiModel, no LiteLLM proxy), reads the key via load_dotenv + a chained LESSON_DOTENV path, and supports a LESSON_MODEL global override + a context_window_limit passthrough.",
         ctx="get_model rewrite + verified GeminiModel reply 2026-06-02. Key lives in the LESSON_DOTENV dotenv file.",
         entities=["gemini-2.5-flash", "GeminiModel", "get_model", "LESSON_DOTENV", "LESSON_MODEL"]),
]

with open(LOG, "a", encoding="utf-8") as f:
    for i, o in enumerate(OBS):
        rec = {
            "ts": (base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "repo": "aws_agent_1",
            **o,
        }
        f.write(json.dumps(rec) + "\n")

print(f"appended {len(OBS)} observations to {LOG}")

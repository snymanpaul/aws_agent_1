"""Append L27 v1.42 runtime-feature observations — captured in the moment."""
import json
import os
from datetime import datetime, timedelta, timezone

LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   ".claude", "learnings", "observations.jsonl")
base = datetime.now(timezone.utc)

OBS = [
    dict(level=27, cat="insight", topic="p27-runtime-features-locally-testable",
         obs="Open question resolved: header forwarding + class-based entrypoint are SDK-level behaviors, verifiable LOCALLY with no AgentCore redeploy. is_forwardable_header is a pure function; app.entrypoint registration and BedrockAgentCoreContext are exercisable in-process. Saved a runtime redeploy.",
         ctx="L27 04_production/agentcore_deploy.py v1.42 section run 2026-06-02, exit 0, no AWS/model.",
         entities=["BedrockAgentCoreApp", "local-test", "is_forwardable_header"]),
    dict(level=27, cat="pattern", topic="forwardable-header-allowlist",
         obs="Empirical is_forwardable_header results (bedrock-agentcore 1.12): FWD = X-Api-Key, Authorization, X-Amzn-Bedrock-AgentCore-Runtime-Custom-*; DROP = Content-Type (restricted), Host (restricted), x-amz-* (SigV4), x-amzn-trace-id (reserved x-amzn- without the custom prefix). So custom auth/tenant headers flow to the agent; signing/infra headers don't.",
         ctx="L27 v1.42 section — printed table of FWD/drop per header.",
         entities=["is_forwardable_header", "request_headers", "header-allowlist"]),
    dict(level=27, cat="pattern", topic="class-based-bound-method-entrypoint",
         obs="app.entrypoint(instance.method) registers a BOUND method as handlers['main'] (verified handlers['main'].__self__ is the instance), so a stateful class backs the agent (#474). Invoking it locally with a context carrying request_headers ({'X-Api-Key': ...}) returned saw_api_key=True (#483) — the forwarded header reaches the entrypoint via context.request_headers.",
         ctx="L27 v1.42 section — GreetingAgent bound-method entrypoint invoked locally with a SimpleNamespace context.",
         entities=["app.entrypoint", "bound-method", "context.request_headers"]),
]

with open(LOG, "a", encoding="utf-8") as f:
    for i, o in enumerate(OBS):
        rec = {"ts": (base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "repo": "aws_agent_1", **o}
        f.write(json.dumps(rec) + "\n")
print(f"appended {len(OBS)} L27 observations")

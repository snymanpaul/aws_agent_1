"""Append L66 (async memory + LTM filter) observations — captured in the moment."""
import json
import os
from datetime import datetime, timedelta, timezone

LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   ".claude", "learnings", "observations.jsonl")
base = datetime.now(timezone.utc)

OBS = [
    dict(level=66, cat="pattern", topic="async-mode-verified",
         obs="AgentCoreMemoryConfig(memory_id, actor_id, session_id, async_mode=True) -> AgentCoreMemorySessionManager(config, boto_session=...). Invoked via agent.invoke_async -> completes, persists the exchange async (offloads boto3 via asyncio.to_thread). The SDK logs that async_mode REQUIRES the async path; sync __call__ would RuntimeError from Strands' hook registry. Verified on the existing STM memory l27agentcore_Memory-9RYaOkDitt.",
         ctx="L66 Iteration 1 run 2026-06-02, bedrock-agentcore 1.12 + Gemini 2.5 Flash.",
         entities=["AgentCoreMemorySessionManager", "async_mode", "invoke_async", "asyncio.to_thread"]),
    dict(level=66, cat="mistake", topic="memorysessionmanager-creds-not-inherited",
         obs="MemorySessionManager(memory_id, region_name) built its OWN client that did NOT inherit the active SSO profile (RetrieveMemoryRecords -> UnrecognizedClientException 'security token invalid'), even with AWS_PROFILE set in env. Also tried boto_client= (TypeError: unexpected kwarg). FIX: pass boto3_session=<profile session> (the kwarg is boto3_session, not boto_client). The strands AgentCoreMemorySessionManager worked because it got boto_session=_session explicitly.",
         ctx="L66 Iteration 2 first run auth error; fixed by boto3_session=_session.",
         entities=["MemorySessionManager", "boto3_session", "SSO", "UnrecognizedClientException"]),
    dict(level=66, cat="insight", topic="ltm-filter-key-must-be-indexed",
         obs="search_long_term_memories with a well-formed MemoryMetadataFilter ({left:{metadataKey}, operator:'EQUALS_TO', right:{metadataValue:{stringValue}}}) returned ValidationException 'Filter key topic is not a valid...' on a memory whose LTM strategy does not index that key. So the call + filter shape are correct, but the filter KEY must be an INDEXED metadata key — which only exists after an LTM strategy extracts records carrying that metadata. Real metadata filtering is extraction-gated. Separately verified: >5 filters -> ValueError (service max 5).",
         ctx="L66 Iteration 2 — STM-only memory; the service validated the request and rejected the unindexed key.",
         entities=["MemoryMetadataFilter", "search_long_term_memories", "indexed-metadata", "LTM-strategy"]),
]

with open(LOG, "a", encoding="utf-8") as f:
    for i, o in enumerate(OBS):
        rec = {"ts": (base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "repo": "aws_agent_1", **o}
        f.write(json.dumps(rec) + "\n")
print(f"appended {len(OBS)} L66 observations")

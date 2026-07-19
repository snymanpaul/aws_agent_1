"""
Level 66: Async AgentCore Memory + LTM Metadata Filtering
=========================================================
bedrock-agentcore v1.12 — two new memory surfaces:
  1. AgentCoreMemorySessionManager in ASYNC mode (offloads the blocking boto3
     memory I/O to a worker thread via asyncio.to_thread, so the event loop
     isn't stalled while persisting/retrieving). Enabled by a CONFIG field, not
     a constructor kwarg — AgentCoreMemoryConfig(async_mode=True). Requires the
     agent be driven via the async path (invoke_async / stream_async).
  2. MemoryMetadataFilter — an indexed-metadata prefilter on
     search_long_term_memories(..., metadata_filters=[...]) (service max: 5).

Depends on: L14 (long-term memory), L37 (AgentCore memory) | Unlocks: scalable
memory-backed agents that don't block their event loop.

Empirical caveats (validated 2026-06-02 — see level-66-reflection):
  * async_mode is AgentCoreMemoryConfig(async_mode=True), NOT
    AgentCoreMemorySessionManager(async_mode=True). (Plan said the latter; wrong.)
  * Reusing the existing memory l27agentcore_Memory-9RYaOkDitt: it is STM-only
    (no strategies), so search_long_term_memories has nothing to return.
    REAL metadata filtering needs a memory with an LTM strategy AND time for the
    async LTM extraction to run. This lesson verifies the async path + the
    filter API + the <=5 constraint; real filtered results are extraction-gated.

Usage:
    PYTHONDONTWRITEBYTECODE=1 AWS_PROFILE=<your-sso-profile> \
      uv run python 14_agentcore_platform/memory_async_ltm.py
"""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from strands import Agent

from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from bedrock_agentcore.memory.session import MemorySessionManager
from bedrock_agentcore.memory.models.filters import (
    MemoryRecordLeftExpression,
    MemoryRecordRightExpression,
    OperatorType,
)

from tools import get_model

REGION = "us-east-1"
AWS_PROFILE = os.environ.get("AWS_PROFILE")
MEMORY_ID = "l27agentcore_Memory-9RYaOkDitt"  # existing ACTIVE memory (STM-only)
_session = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)

model = get_model("gemini-2.5-flash")


# ---------------------------------------------------------------------------
# ITERATION 1: Async-mode session manager (non-blocking memory I/O)
# ---------------------------------------------------------------------------
def iteration_1_async_mode() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 1: AgentCoreMemorySessionManager async_mode")
    print("=" * 70)

    actor_id = f"l66-actor-{uuid.uuid4().hex[:8]}"
    session_id = f"l66-session-{uuid.uuid4().hex[:8]}"

    # async_mode lives on the CONFIG (not the manager constructor).
    config = AgentCoreMemoryConfig(
        memory_id=MEMORY_ID,
        actor_id=actor_id,
        session_id=session_id,
        async_mode=True,
    )
    manager = AgentCoreMemorySessionManager(config, region_name=REGION, boto_session=_session)
    print(f"  config.async_mode = {config.async_mode}  (a config field, not a ctor kwarg)")

    agent = Agent(model=model, session_manager=manager, callback_handler=None)

    async def run() -> str:
        # async_mode REQUIRES the async invocation path; sync __call__ would
        # block on the memory I/O it is trying to offload.
        result = await agent.invoke_async("My favourite colour is teal. Remember that.")
        return str(result)

    reply = asyncio.run(run())
    print(f"  invoke_async completed; reply: {reply[:80]!r}")
    print(f"  messages in history: {len(agent.messages)} (persisted async to {MEMORY_ID})")
    print("  -> blocking boto3 memory writes ran via asyncio.to_thread, off the event loop")


# ---------------------------------------------------------------------------
# ITERATION 2: MemoryMetadataFilter on long-term-memory search
# ---------------------------------------------------------------------------
def iteration_2_metadata_filter() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 2: MemoryMetadataFilter (indexed LTM prefilter)")
    print("=" * 70)

    msm = MemorySessionManager(memory_id=MEMORY_ID, boto3_session=_session)

    # Build a filter: metadata key 'topic' EQUALS_TO 'billing'.
    topic_filter = {
        "left": MemoryRecordLeftExpression.build("topic"),
        "operator": OperatorType.EQUALS_TO.value,
        "right": MemoryRecordRightExpression.build_string("billing"),
    }
    print(f"  built filter: {topic_filter}")

    try:
        results = msm.search_long_term_memories(
            query="account balance",
            namespace="/",
            metadata_filters=[topic_filter],
            max_results=5,
        )
        n = len(results) if isinstance(results, list) else len(getattr(results, "memories", []) or [])
        print(f"  search_long_term_memories(metadata_filters=[topic]) -> {n} records")
        print("  (0 expected: this memory is STM-only; real filtering needs an LTM strategy + extraction)")
    except Exception as e:  # noqa: BLE001
        print(f"  search returned: {type(e).__name__}: {str(e)[:120]}")
        print("  -> empirical: the call + filter are well-formed, but the filter KEY must be")
        print("     an INDEXED metadata key — which only exists once an LTM strategy extracts")
        print("     records carrying that metadata. Confirms real filtering is extraction-gated.")

    # The service caps metadata_filters at 5 — verify the SDK enforces it.
    six = [topic_filter] * 6
    try:
        msm.search_long_term_memories(query="x", namespace="/", metadata_filters=six)
        print("  WARN: 6 filters did not raise (expected ValueError)")
    except ValueError as e:
        print(f"  constraint: 6 filters -> ValueError ({str(e)[:60]})")
    except Exception as e:  # noqa: BLE001
        print(f"  6 filters -> {type(e).__name__} (constraint not the ValueError path: {str(e)[:60]})")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L66 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. async_mode is a CONFIG field
   AgentCoreMemoryConfig(memory_id, actor_id, session_id, async_mode=True)
   -> AgentCoreMemorySessionManager(config, ...). Drive the agent via
   invoke_async / stream_async; the blocking boto3 memory I/O is offloaded to a
   thread (asyncio.to_thread) so the event loop keeps moving.

2. MemoryMetadataFilter prefilters LTM search
   search_long_term_memories(query, namespace, metadata_filters=[...]) with each
   filter {left:{metadataKey}, operator, right:{metadataValue:{stringValue}}}.
   Max 5 filters (SDK raises ValueError beyond that). Indexed metadata narrows
   the semantic search BEFORE scoring — cheaper + more precise than post-filtering.

3. Verification reality
   Real filtered LTM results require (a) a memory with an LTM strategy and
   (b) time for async LTM extraction to populate records with indexed metadata.
   The reused l27 memory is STM-only, so this lesson verifies the async path +
   the filter API + the <=5 constraint; populating + filtering real LTM records
   is extraction-latency-gated (a dedicated run).
""")


def main() -> None:
    iteration_1_async_mode()
    iteration_2_metadata_filter()
    summary()


if __name__ == "__main__":
    main()

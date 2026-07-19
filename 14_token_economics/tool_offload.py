"""
Level 63: Tool Result Offload — Stop Big Outputs From Eating the Context Window
==============================================================================
Strands SDK v1.38 — `strands.vended_plugins.context_offloader`.

Goal: when a tool returns a large payload (web scrape, file read, search results),
spill it to a storage backend instead of dumping it into the conversation. The
agent gets a short preview + a reference; if it actually needs the full content,
an auto-injected retrieval tool fetches it on demand.

Problem this solves:
    Naïve agent loop with a tool that returns 50KB of text:
      turn 1: tool_result = 12,500 tokens of scraped HTML
      turn 2: history now carries those 12,500 tokens forever
      turn 3: another tool_result of 12,500 tokens -> 25,000 tokens
      turn 4: context window saturated; cost balloons; latency rises
    The model rarely needs the full content — it usually summarises, extracts
    a field, or makes a yes/no decision. Carrying the raw bytes in history is
    pure waste.

Depends on: L9 (MCP), L31 (Workflow), L57 (Sessions)
Unlocks:    L62 (CachePoint TTL), L67 (AG-UI on AgentCore — offload bonds well
            with managed runtime memory budgets)

Iterations:
  1. Storage backends in isolation     — round-trip the three storage classes,
                                         no agent involved. Confirms the API.
  2. Offloader plugin construction     — wire ContextOffloader into Agent via
                                         the `plugins=[...]` parameter; show
                                         what gets attached.
  3. End-to-end with a fake big tool   — agent + tool that returns ~50KB;
                                         observe history with vs without the
                                         offloader plugin. Requires LiteLLM
                                         proxy running (per CLAUDE.md).

Critical API facts (validated by probe, not docs):
    * ContextOffloader(storage, max_result_tokens=2500, preview_tokens=1000,
                       *, include_retrieval_tool=True)
        - max_result_tokens: tool results estimated above this get offloaded.
        - preview_tokens: how many tokens of preview text are kept inline.
        - include_retrieval_tool: if True, the agent gets a tool to fetch the
          full content by reference. If False, only the preview is visible.
    * Storage protocol: store(key, content: bytes, content_type='text/plain') -> str
                        retrieve(reference: str) -> tuple[bytes, str]
    * Backends: InMemoryStorage(), FileStorage(artifact_dir='./artifacts'),
                S3Storage(bucket, prefix='', boto_session=None, ...).
    * Wiring: Agent(model=..., tools=..., plugins=[ContextOffloader(...)]).
      The offloader subclasses Plugin; it auto-registers an AfterToolCallEvent
      hook + the retrieval tool.

Usage:
    uv run python 14_token_economics/tool_offload.py
"""

import os
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands.vended_plugins.context_offloader.plugin import ContextOffloader
from strands.vended_plugins.context_offloader.storage import (
    InMemoryStorage,
    FileStorage,
    # S3Storage  # production; needs AWS creds — not used in this lesson
)
from tools import get_model

model = get_model("haiku")


# ---------------------------------------------------------------------------
# ITERATION 1: Storage backends in isolation
# ---------------------------------------------------------------------------
# Goal: verify the Storage protocol works without involving an agent. This
# isolates the "where do bytes go and how do we get them back" question from
# the "when does the offloader kick in" question.
def iteration_1_storage_round_trip() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 1: Storage backend round-trip")
    print("=" * 70)

    payload = ("X" * 50_000).encode()  # ~12.5K tokens at chars/4

    # InMemoryStorage — fastest, lost on process exit.
    mem = InMemoryStorage()
    ref_mem = mem.store(key="probe-1", content=payload, content_type="text/plain")
    out_bytes, out_type = mem.retrieve(ref_mem)
    print(f"  InMemoryStorage : ref={ref_mem!r:30s} bytes={len(out_bytes)} type={out_type!r}")
    assert out_bytes == payload, "InMemoryStorage round-trip mismatch"

    # FileStorage — survives process restart; metadata sidecar carries content type.
    artifact_dir = Path("./artifacts/l63_demo")
    fs = FileStorage(artifact_dir=str(artifact_dir))
    ref_fs = fs.store(key="probe-2", content=payload, content_type="text/plain")
    out_bytes, out_type = fs.retrieve(ref_fs)
    print(f"  FileStorage     : ref={ref_fs!r:30s} bytes={len(out_bytes)} type={out_type!r}")
    print(f"                    artifact_dir contents: {sorted(p.name for p in artifact_dir.iterdir())[:4]}")
    assert out_bytes == payload, "FileStorage round-trip mismatch"

    # S3Storage skipped here — same protocol, just substitutes the bucket.
    # Use it when artifacts must be shared across machines or kept beyond a
    # single agent run.
    print("  (S3Storage uses identical protocol — drop in for cross-host runs.)")


# ---------------------------------------------------------------------------
# ITERATION 2: Offloader plugin construction & inspection
# ---------------------------------------------------------------------------
# Goal: show how the plugin attaches to the agent and what it brings — a hook
# (AfterToolCallEvent) and an auto-injected retrieval tool. No LLM call yet.
def iteration_2_plugin_wiring() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 2: Plugin wiring — what the offloader attaches")
    print("=" * 70)

    @tool
    def small_tool(query: str) -> str:
        """Returns a short string."""
        return f"You asked: {query}"

    offloader = ContextOffloader(
        storage=InMemoryStorage(),
        max_result_tokens=2500,
        preview_tokens=1000,
        include_retrieval_tool=True,
    )

    agent = Agent(
        model=model,
        tools=[small_tool],
        plugins=[offloader],
        callback_handler=None,
    )

    print(f"  agent tool names: {[t for t in agent.tool_names]}")
    print(f"    -> notice the auto-injected retrieval tool added by the plugin")
    print(f"  plugin name     : {offloader.name}")
    print(f"  plugin hooks    : {[h.__class__.__name__ for h in offloader.hooks]}")
    print(f"  plugin tools    : {[t.tool_name for t in offloader.tools]}")
    print(f"  thresholds      : max_result_tokens={2500}, preview_tokens={1000}")
    print(f"                    (results above max_result are offloaded; preview kept inline)")


# ---------------------------------------------------------------------------
# ITERATION 3: End-to-end — the offloader gives the AGENT a choice
# ---------------------------------------------------------------------------
# Empirical insight (verified by running this lesson 2026-05-03):
#   The offloader does NOT magically save tokens. What it does is replace the
#   inline tool_result with a short preview + a reference. The agent then
#   *decides* whether to retrieve the full content via an auto-injected tool.
#
#   - If the task is preview-sufficient (summary, single field, yes/no), the
#     agent answers from the preview and the full content stays out of history.
#     => big savings.
#   - If the task NEEDS the full content (count words, search for a quote),
#     the agent calls the retrieval tool. The full content comes back inline.
#     => no savings on this turn, but the choice was deliberate.
#
# This iteration runs both cases against the same big-doc tool to make the
# distinction concrete.
#
# Requires LiteLLM proxy at localhost:4000 (see CLAUDE.md).
def iteration_3_end_to_end() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 3: End-to-end — preview-sufficient vs full-content tasks")
    print("=" * 70)

    @tool
    def fetch_huge_doc(topic: str) -> str:
        """Pretend to fetch a long document about a topic."""
        # Real-world analogue: web scrape, file read, search result list.
        # Use varied, non-repetitive prose so content filters don't reject it.
        chunks = [f"# Report on {topic}\n\n## Executive Summary\n\n"]
        for i in range(60):
            chunks.append(
                f"Section {i+1}. The history of {topic} extends across multiple decades "
                f"and disciplines. Researchers in iteration {i} have documented "
                f"approximately {i * 7 + 13} distinct sub-fields, each with its own "
                f"vocabulary and methodologies. Cross-disciplinary collaboration has "
                f"yielded {i * 11 + 47} peer-reviewed publications in the period under "
                f"review. Notable contributors during phase {i} include institutions in "
                f"North America, Europe, and Asia, with distinct emphases on theoretical "
                f"modelling, empirical validation, and applied engineering. "
                f"The implications for industry adoption remain an active question.\n\n"
            )
        return "".join(chunks)

    @tool
    def count_words(text: str) -> int:
        """Count words — a tool that NEEDS the full text."""
        return len(text.split())

    def history_size(agent: Agent) -> tuple[int, int]:
        chars = sum(
            len(c.get("text", "") or str(c))
            for m in agent.messages
            for c in (m.get("content", []) if isinstance(m.get("content"), list) else [])
        )
        return len(agent.messages), chars

    def run_and_report(label: str, agent: Agent, prompt: str) -> None:
        print(f"\n  --- {label} ---")
        try:
            agent(prompt)
        except Exception as e:
            print(f"    agent run failed: {type(e).__name__}: {str(e)[:200]}")
            return
        n_msgs, chars = history_size(agent)
        print(f"    prompt        : {prompt!r}")
        print(f"    history msgs  : {n_msgs}")
        print(f"    inline chars  : ~{chars} (~{chars // 4} tokens)")

    # ---- Case 3A: preview-sufficient task ----
    # Asking "what is this about?" — the agent can answer from the preview
    # without retrieving the full content. Offloader pays off.
    print("\n  CASE 3A: preview-sufficient task ('what's the gist?')")

    agent_a_no = Agent(
        model=model, tools=[fetch_huge_doc, count_words], callback_handler=None,
    )
    run_and_report(
        "Variant A.no_offloader",
        agent_a_no,
        "Fetch a report on quantum computing. In one sentence, what's the topic?",
    )

    agent_a_off = Agent(
        model=model, tools=[fetch_huge_doc, count_words],
        plugins=[ContextOffloader(
            storage=InMemoryStorage(),
            max_result_tokens=500, preview_tokens=200,
        )],
        callback_handler=None,
    )
    run_and_report(
        "Variant A.with_offloader",
        agent_a_off,
        "Fetch a report on quantum computing. In one sentence, what's the topic?",
    )

    # ---- Case 3B: full-content task ----
    # Asking "count the words" — the agent MUST retrieve. Offloader doesn't
    # help token-wise, but the choice was deliberate (and the bytes were
    # held in storage rather than carried through every prior turn).
    print("\n  CASE 3B: full-content task ('count words')")

    agent_b_no = Agent(
        model=model, tools=[fetch_huge_doc, count_words], callback_handler=None,
    )
    run_and_report(
        "Variant B.no_offloader",
        agent_b_no,
        "Fetch a report on quantum computing. How many words is it?",
    )

    agent_b_off = Agent(
        model=model, tools=[fetch_huge_doc, count_words],
        plugins=[ContextOffloader(
            storage=InMemoryStorage(),
            max_result_tokens=500, preview_tokens=200,
        )],
        callback_handler=None,
    )
    run_and_report(
        "Variant B.with_offloader",
        agent_b_off,
        "Fetch a report on quantum computing. How many words is it?",
    )

    print("""
  Expected pattern:
    Case A (preview-sufficient): with_offloader history is MUCH smaller.
    Case B (full-content):       both variants similar — the agent retrieved
                                 the full content because the task required it.
""")


# ---------------------------------------------------------------------------
# Summary — the takeaways
# ---------------------------------------------------------------------------
def summary() -> None:
    print("\n" + "=" * 70)
    print("L63 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. The problem
   Tool results above ~2500 tokens (default) blow up history every turn.
   Most reasoning needs a summary, not the raw bytes.

2. The shape of the fix
   Agent(model=..., tools=..., plugins=[ContextOffloader(storage=...)])
   The plugin attaches an AfterToolCallEvent hook + a retrieval tool.
   Big tool_result -> stored externally; preview + reference kept inline.

   CRUCIAL nuance (verified empirically): the offloader does not magically
   save tokens. It replaces the inline result with preview + reference and
   gives the AGENT a choice. If the task is preview-sufficient, the agent
   answers from the preview and the full content never re-enters history
   (real savings). If the task needs the full content, the agent calls the
   auto-injected retrieval tool and the full bytes come back inline (no
   savings on that turn, but the choice was deliberate and the storage
   keeps the bytes out of every PRIOR turn).

3. Storage choice
   - InMemoryStorage : single-process, fastest, lost at exit. Tests/demos.
   - FileStorage     : per-host disk, survives restart. Single-machine prod.
   - S3Storage       : multi-host, durable. Real production; small AWS dep.

4. Threshold tuning
   max_result_tokens : the trigger. Lower = more aggressive offloading.
   preview_tokens    : how much of the result the model still sees inline.
   include_retrieval_tool : True if the model should be able to fetch the
                            full content; False if a preview is enough.

5. When to reach for it
   - Web scraping / browser tools (L29 bidi + L66 AgentCore browser)
   - File reads with unknown size
   - Search APIs returning long candidate lists (Exa deep search, MCP)
   - Any tool whose payload size is data-dependent

6. Pairs cleanly with
   - L61 count_tokens : pre-call estimate decides if you SHOULD offload before
     even running the tool.
   - L62 CachePoint TTL : different lever (cache prompt prefix); offload covers
     the variable-size middle. Use both for full token economics.
""")


def main() -> None:
    iteration_1_storage_round_trip()
    iteration_2_plugin_wiring()
    iteration_3_end_to_end()
    summary()


if __name__ == "__main__":
    main()

"""
Level 44: AG-UI — Agent-to-Frontend Protocol

AG-UI is the open event protocol for streaming agent state to a UI without
custom WebSocket wiring. Every Strands action (text token, tool call,
tool result) emits a typed SSE event that any AG-UI-compatible frontend
(CopilotKit, custom React) can consume.

What this level covers:
  1. Event anatomy     — what's inside each of the 10+ AG-UI event types
  2. State management  — shared state flows frontend ↔ agent via:
       state_context_builder  → frontend state injected into system prompt
       state_from_args        → optimistic update when tool is CALLED
       state_from_result      → actual update when tool RETURNS
  3. Multi-turn thread — state persists across messages in same thread
  4. ToolBehavior      — per-tool SSE configuration

Domain: Research Agent
  Tools: search_papers, fetch_abstract, get_citation_count
  State: {"query": str, "sources": list[str], "status": str}
  The frontend state shows live "Searching for: X" before results arrive,
  then "Found 3 sources" once tools return.

vs A2A (L32):
  A2A   = agent talking to another agent (agent↔agent)
  AG-UI = agent talking to a frontend (agent↔UI)
  Both use the same event-streaming concept but different payloads.
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
from typing import Any

from fastapi.testclient import TestClient
from ag_ui_strands import (
    StrandsAgent, StrandsAgentConfig,
    ToolBehavior, ToolCallContext, ToolResultContext,
    PredictStateMapping, create_strands_app,
)
from ag_ui.core import RunAgentInput, UserMessage
from strands import Agent, tool
from tools import get_model

model      = get_model("claude-sonnet-4")
fast_model = get_model("haiku")


# ── Domain tools (simulated research API) ────────────────────────────────────

@tool
def search_papers(query: str, max_results: int = 3) -> str:
    """Search academic papers for a given query. Returns paper titles and IDs."""
    papers = {
        "transformer":   ["Attention Is All You Need [p001]", "BERT [p002]", "GPT-3 [p003]"],
        "agent":         ["ReAct: Synergizing Reasoning [p004]", "Toolformer [p005]", "AutoGPT [p006]"],
        "rag":           ["RAG for Knowledge-Intensive NLP [p007]", "REALM [p008]", "FAISS [p009]"],
        "reflexion":     ["Reflexion: Language Agents [p010]", "Self-Refine [p011]", "Critic [p012]"],
    }
    key = next((k for k in papers if k in query.lower()), None)
    if key:
        results = papers[key][:max_results]
        return f"Found {len(results)} papers: " + "; ".join(results)
    return f"No papers found for '{query}'"

@tool
def fetch_abstract(paper_id: str) -> str:
    """Fetch the abstract of a paper by ID."""
    abstracts = {
        "p001": "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms...",
        "p004": "We combine reasoning traces and task-specific actions, allowing for greater synergy between the two...",
        "p007": "We combine parametric and non-parametric memory for language generation, enabling knowledge-intensive NLP...",
        "p010": "We introduce Reflexion, a framework to reinforce language agents via linguistic feedback...",
    }
    pid = paper_id.strip().lower().replace("[", "").replace("]", "")
    return abstracts.get(pid, f"Abstract not found for {paper_id}")

@tool
def get_citation_count(paper_id: str) -> str:
    """Get the citation count for a paper."""
    citations = {"p001": 90000, "p002": 50000, "p004": 3200, "p007": 4100, "p010": 1800}
    pid = paper_id.strip().lower().replace("[", "").replace("]", "")
    count = citations.get(pid, 0)
    return f"Paper {paper_id} has {count:,} citations"


# ── State management callbacks ────────────────────────────────────────────────

def state_context_builder(run_input: RunAgentInput, user_message: str) -> str:
    """
    Inject frontend state into the user message.
    The SDK passes (input_data, original_user_message_str) and expects back
    the COMPLETE modified user message — return value REPLACES user_message.
    Must include the original task or the agent only sees the context.
    """
    state = run_input.state or {}
    sources = state.get("sources", [])
    user_pref = state.get("user_preference", "concise")

    context_lines = [f"[Context] Response style: {user_pref}"]
    if sources:
        context_lines.append(f"[Context] Already found: {', '.join(sources)}")

    context = "\n".join(context_lines)
    return f"{user_message}\n\n{context}"

def search_papers_from_args(ctx: ToolCallContext) -> dict | None:
    """
    Optimistic state update — fires when search_papers is CALLED (before result).
    Frontend immediately shows "Searching for: X..." before the tool returns.
    ctx.tool_input is the dict of tool arguments.
    """
    args = ctx.tool_input or {}
    query = args.get("query", "")
    if query:
        return {"status": f"Searching for: {query}...", "query": query}
    return None

def search_papers_from_result(ctx: ToolResultContext) -> dict | None:
    """
    Actual state update — fires when search_papers RETURNS.
    Extracts paper IDs from the result and adds them to the sources list.
    ctx.result_data is the tool return value; state is in ctx.input_data.state.
    """
    import re
    result_str = str(ctx.result_data) if ctx.result_data else ""
    paper_ids = re.findall(r'\[p\d+\]', result_str)
    if paper_ids:
        existing = (ctx.input_data.state or {}).get("sources", [])
        updated = list(dict.fromkeys(existing + paper_ids))  # dedup, preserve order
        count = len(updated)
        return {
            "sources":  updated,
            "status":   f"Found {count} source{'s' if count != 1 else ''}",
        }
    return {"status": "Search complete (no papers matched)"}


# ── Build the app ─────────────────────────────────────────────────────────────

def build_app():
    strands_agent = Agent(
        model=model,
        tools=[search_papers, fetch_abstract, get_citation_count],
        system_prompt=(
            "You are a research assistant. "
            "Search for papers, fetch abstracts, and report citation counts. "
            "Be concise and cite paper IDs in your responses."
        ),
        callback_handler=None,
    )

    config = StrandsAgentConfig(
        state_context_builder=state_context_builder,
        tool_behaviors={
            "search_papers": ToolBehavior(
                state_from_args   = search_papers_from_args,
                state_from_result = search_papers_from_result,
            ),
        },
    )

    agui_agent = StrandsAgent(
        agent=strands_agent,
        name="research_agent",
        description="Searches academic papers and fetches abstracts",
        config=config,
    )

    return create_strands_app(agui_agent, path="/invocations", ping_path="/ping")


# ── Event stream consumer ─────────────────────────────────────────────────────

def consume_stream(client: TestClient, payload: dict) -> list[dict]:
    """Send a request and collect all SSE events."""
    events = []
    with client.stream(
        "POST", "/invocations",
        json=payload,
        headers={"Accept": "text/event-stream"},
        timeout=60,
    ) as response:
        for line in response.iter_lines():
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                try:
                    events.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass
    return events

def print_events(events: list[dict], turn: int):
    print(f"\n{'─' * 60}")
    print(f"  TURN {turn} — {len(events)} events")
    print(f"{'─' * 60}")

    text_buf = []
    state_after = {}

    for ev in events:
        etype = ev.get("type", "unknown")

        if etype == "RUN_STARTED":
            print(f"  ┌ RUN_STARTED  run_id={ev.get('run_id','?')[:12]}")

        elif etype == "STATE_SNAPSHOT":
            state_after = ev.get("snapshot", {})
            print(f"  │ STATE_SNAPSHOT  state={state_after}")

        elif etype == "TOOL_CALL_START":
            print(f"  │ TOOL_CALL_START  → {ev.get('toolCallName')}()")

        elif etype == "TOOL_CALL_ARGS":
            delta = ev.get("delta", "")
            print(f"  │   args_delta: {delta!r}")

        elif etype == "TOOL_CALL_END":
            print(f"  │ TOOL_CALL_END")

        elif etype == "TOOL_CALL_RESULT":
            result_str = str(ev.get("content", ""))[:80]
            print(f"  │ TOOL_CALL_RESULT  {result_str!r}")

        elif etype == "TEXT_MESSAGE_CONTENT":
            text_buf.append(ev.get("delta", ""))

        elif etype == "TEXT_MESSAGE_END":
            full = "".join(text_buf)
            text_buf = []
            print(f"  │ TEXT  {full[:120]!r}{'...' if len(full) > 120 else ''}")

        elif etype == "MESSAGES_SNAPSHOT":
            msgs = ev.get("messages", [])
            print(f"  │ MESSAGES_SNAPSHOT  ({len(msgs)} messages in thread)")

        elif etype == "RUN_FINISHED":
            print(f"  └ RUN_FINISHED")

    return state_after


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("L44: AG-UI — Agent-to-Frontend Protocol")
    print("=" * 60)
    print("\nAgent: Research Assistant (search_papers, fetch_abstract, get_citation_count)")
    print("State: {query, sources, status} — updated optimistically on tool call")
    print("Config: state_context_builder + ToolBehavior(state_from_args, state_from_result)")

    app = build_app()

    with TestClient(app) as client:
        # ── Health check ──────────────────────────────────────────────────
        r = client.get("/ping")
        print(f"\n  GET /ping → {r.status_code} {r.json()}")

        THREAD_ID = "research-session-42"

        # ── Turn 1: first message ─────────────────────────────────────────
        print("\n" + "=" * 60)
        print("TURN 1 — Initial research query")
        print("=" * 60)

        payload1 = {
            "thread_id": THREAD_ID,
            "run_id":    "run-001",
            "messages":  [
                {"role": "user", "id": "m1",
                 "content": "Find papers on Reflexion agents and get the citation count for the top result."}
            ],
            "tools":     [],
            "state":     {"user_preference": "concise", "sources": [], "status": "idle"},
            "context":   [],
            "forwarded_props": {},
        }

        events1 = consume_stream(client, payload1)
        state1 = print_events(events1, turn=1)

        # ── Turn 2: follow-up using accumulated state ─────────────────────
        print("\n" + "=" * 60)
        print("TURN 2 — Follow-up (state carries sources from Turn 1)")
        print("=" * 60)
        print(f"  State carried forward: {state1}")

        # Reconstruct message history from Turn 1 events
        t1_msgs = next(
            (ev.get("messages", []) for ev in reversed(events1)
             if ev.get("type") == "MESSAGES_SNAPSHOT"),
            []
        )
        t1_msgs.append({
            "role": "user", "id": "m2",
            "content": "Now fetch the abstract for the Reflexion paper you found."
        })

        payload2 = {
            "thread_id": THREAD_ID,
            "run_id":    "run-002",
            "messages":  t1_msgs,
            "tools":     [],
            "state":     state1 or {"sources": [], "status": "idle", "user_preference": "concise"},
            "context":   [],
            "forwarded_props": {},
        }

        events2 = consume_stream(client, payload2)
        state2 = print_events(events2, turn=2)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("KEY CONCEPTS DEMONSTRATED")
    print("=" * 60)
    print("""
  AG-UI event stream (in order):
    RUN_STARTED        → conversation begins
    STATE_SNAPSHOT     → current shared state sent to consumer
    TOOL_CALL_START    → agent called a tool
    TOOL_CALL_ARGS     → tool arguments streaming (delta)
    TOOL_CALL_END      → arguments complete
    TOOL_CALL_RESULT   → tool return value
    TEXT_MESSAGE_*     → agent response streaming (start/content/end)
    MESSAGES_SNAPSHOT  → full conversation history snapshot
    RUN_FINISHED       → run complete

  State management (3 hooks):
    state_context_builder(input, user_msg) → str
      → Return value REPLACES the user message. Must include original task +
         injected context. SDK passes original message as second arg.

    ToolBehavior.state_from_args(ctx) → dict | None
      → Optimistic update fires when tool is CALLED (before execution).
         Frontend immediately shows "Searching for: X..." — no waiting.

    ToolBehavior.state_from_result(ctx) → dict | None
      → Actual update fires when tool RETURNS.
         Sources list grows; status changes to "Found N sources".

  Multi-turn thread:
    Same thread_id = same conversation. State carried forward in payload.
    Agent sees previous tool calls + results via MESSAGES_SNAPSHOT history.

  Portability:
    Same /invocations + SSE contract works with CopilotKit, custom React,
    or any AG-UI consumer. Swap Strands for LangGraph without touching frontend.
    """)

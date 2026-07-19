"""
Level 32: A2A Protocol — Remote Agents as Network Services
==========================================================
Expose Strands agents as HTTP services via the Agent-to-Agent (A2A)
open standard; consume them as local objects.

Goal: a remote A2A agent looks identical to a local Agent from the
caller's perspective. Mix local and remote agents transparently in
Graphs and tool-driven orchestration.

Depends on: L31 (Workflow), L8 (Graph)
Spec: https://google-a2a.github.io/A2A/latest/

Iterations:
  1. Hello A2A          — single server + A2AAgent direct call
  2. Tool client        — A2AClientToolProvider: LLM-driven routing
  3. Graph node         — A2AAgent as drop-in GraphBuilder node
  4. Diamond graph      — two A2AAgent branches, local merge (fan-out/in)
  5. Compliant streaming— enable_a2a_compliant_streaming=True verified
  6. Dynamic discovery  — a2a_discover_agent at runtime, not pre-seeded
  7. A2A + Workflow     — @tool wrapper bridges remote agents into L31 DAGs

Architecture:
    SERVER SIDE
    ┌──────────────────────────────────────────────┐
    │  Agent(name=..., description=..., tools=[...])│
    │             ↓                                 │
    │  A2AServer(agent=..., port=N)                 │
    │             ↓                                 │
    │  uvicorn → HTTP /a2a + /.well-known/agent.json│
    └──────────────────────────────────────────────┘

    CLIENT (direct)
    ┌──────────────────────────────────────────────┐
    │  A2AAgent(endpoint="http://host:N")           │
    │  remote("task")  ← identical to Agent("task") │
    └──────────────────────────────────────────────┘

    CLIENT (tool-based)
    ┌──────────────────────────────────────────────┐
    │  A2AClientToolProvider(known_agent_urls=[...])│
    │  tools: discover | list | send_message        │
    │  Agent(tools=provider.tools) ← LLM orchestrates│
    └──────────────────────────────────────────────┘

Usage:
    uv run python 11_platform/a2a_protocol.py
"""

import asyncio
import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from strands import Agent, tool
from strands.agent.a2a_agent import A2AAgent
from strands.multiagent import GraphBuilder
from strands.multiagent.a2a import A2AServer
from strands_tools import calculator, workflow
from strands_tools.a2a_client import A2AClientToolProvider
from tools import get_model

model = get_model("haiku")


# ---------------------------------------------------------------------------
# Helper — start A2AServer in a background daemon thread
# ---------------------------------------------------------------------------

def start_server_bg(agent: Agent, port: int, **server_kwargs) -> uvicorn.Server:
    """Wrap agent in A2AServer, run in background thread; return when ready."""
    a2a = A2AServer(agent=agent, host="127.0.0.1", port=port, **server_kwargs)
    app = a2a.to_starlette_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    t = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    t.start()

    # Block until uvicorn signals the port is bound
    while not server.started:
        time.sleep(0.05)

    return server


# ---------------------------------------------------------------------------
# ITERATION 1: Hello A2A — server + direct A2AAgent client
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 1: Hello A2A — math specialist over the network")
print("=" * 70)
print("""
SERVER: math_specialist Agent + A2AServer → HTTP :9100
CLIENT: A2AAgent(endpoint="http://127.0.0.1:9100")

Key insight: remote("task") is syntactically identical to Agent("task").
The caller has no idea it is talking across HTTP.
""")

math_agent = Agent(
    name="math_specialist",
    description="A maths specialist that performs arithmetic calculations.",
    model=model,
    tools=[calculator],
    callback_handler=None,
)

print("Starting math_specialist on :9100 ...")
start_server_bg(math_agent, port=9100)
print("Server ready.\n")

math_remote = A2AAgent(endpoint="http://127.0.0.1:9100")

print("--- agent card (discovery endpoint) ---")
card = asyncio.run(math_remote.get_agent_card())
print(f"  name:         {card.name}")
print(f"  description:  {card.description}")
print(f"  streaming:    {card.capabilities.streaming}")

print("\n--- remote call ---")
result = math_remote("Use the calculator to compute 42 * 7 + 100. Report the number only.")
print(f"  remote result : {result}")

print("\n--- identical local call (for comparison) ---")
local_math = Agent(model=model, tools=[calculator], callback_handler=None)
local_result = local_math("Use the calculator to compute 42 * 7 + 100. Report the number only.")
print(f"  local  result : {local_result}")


# ---------------------------------------------------------------------------
# ITERATION 2: A2AClientToolProvider — LLM-orchestrated discovery
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 2: A2AClientToolProvider — LLM decides who to call")
print("=" * 70)
print("""
Instead of hardcoding A2AAgent calls, expose A2A as LLM-visible TOOLS:

  a2a_discover_agent(url)       — add a new remote agent
  a2a_list_discovered_agents()  — list all known agents
  a2a_send_message(text, url)   — ask a specific agent

An orchestrator LLM can autonomously discover and route tasks without
knowing endpoints in advance — it just calls the tools.
""")

geo_agent = Agent(
    name="geography_specialist",
    description="An expert in world geography, capitals, and countries.",
    model=model,
    callback_handler=None,
)

print("Starting geography_specialist on :9101 ...")
start_server_bg(geo_agent, port=9101)
print("Server ready.\n")

provider = A2AClientToolProvider(known_agent_urls=["http://127.0.0.1:9101"])

orchestrator = Agent(
    model=model,
    tools=provider.tools,
    callback_handler=None,
    system_prompt=(
        "You are an orchestrator. Use A2A tools to communicate with remote agents. "
        "Always list available agents first, then delegate tasks to the right agent."
    ),
)

print("--- orchestrator uses A2A tools (list → send_message) ---")
orch_result = orchestrator(
    "List all discovered A2A agents, then ask the geography specialist: "
    "'What are the capitals of France, Japan, and Brazil? "
    "Answer as a bullet list.'"
)
print(f"Result:\n{orch_result}")


# ---------------------------------------------------------------------------
# ITERATION 3: Graph — A2AAgent as a transparent node
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 3: Graph — A2AAgent node is indistinguishable from local node")
print("=" * 70)
print("""
Graph:
    [math_node]      ← A2AAgent — remote, port 9100
          ↓
    [explain_node]   ← Agent    — local

GraphBuilder.add_node() accepts any AgentBase subclass.
A2AAgent extends AgentBase, so no special handling is needed.
The graph result flows through remote and local nodes identically.
""")

# math_remote is still alive from iteration 1 — reuse it
explainer = Agent(
    name="local_explainer",
    model=model,
    callback_handler=None,
    system_prompt=(
        "You receive a number computed in the previous step. "
        "Write a single warm sentence explaining what that number represents "
        "(e.g. '394 is the product of 42 and 7 plus an extra 100.')."
    ),
)

builder = GraphBuilder()
builder.add_node(math_remote, "math_node")      # ← A2AAgent (remote)
builder.add_node(explainer,   "explain_node")   # ← Agent    (local)
builder.add_edge("math_node", "explain_node")
builder.set_entry_point("math_node")
builder.set_max_node_executions(5)
builder.set_execution_timeout(120)
builder.set_node_timeout(60)

graph = builder.build()

print("--- running graph: math (remote) → explain (local) ---")
graph_result = graph("Use the calculator to compute 6 * 7. Return the number only.")
print(f"Graph result: {graph_result}")


# ---------------------------------------------------------------------------
# ITERATION 4: Diamond graph — parallel A2AAgent branches, local merge
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 4: Diamond graph — two A2AAgent branches fan-out / fan-in")
print("=" * 70)
print("""
Graph topology (classic diamond):

    [planner:local]
    /              \\
[math:9100]    [geo:9101]   ← both A2AAgent nodes; ready simultaneously
    \\              /
  [synthesizer:local]

planner → math AND geo (independent → parallel if GraphBuilder schedules it)
math + geo → synthesizer (fan-in: receives outputs of both branches)

Reuses the two servers already running from iterations 1 + 2.
""")

planner = Agent(
    name="local_planner",
    model=model,
    callback_handler=None,
    system_prompt=(
        "You split a compound question into two parts: "
        "one arithmetic question and one geography question. "
        "Output both questions clearly labelled."
    ),
)

synthesizer = Agent(
    name="local_synthesizer",
    model=model,
    callback_handler=None,
    system_prompt=(
        "You receive answers from a maths specialist and a geography specialist. "
        "Weave them into a single coherent two-sentence summary."
    ),
)

# math_remote and geo_agent (port 9101) still live from earlier iterations.
# Build a fresh A2AAgent handle for geo so naming is clear.
geo_remote = A2AAgent(endpoint="http://127.0.0.1:9101")

diamond = GraphBuilder()
diamond.add_node(planner,     "plan")
diamond.add_node(math_remote, "math")   # A2AAgent
diamond.add_node(geo_remote,  "geo")    # A2AAgent
diamond.add_node(synthesizer, "synth")
diamond.add_edge("plan", "math")
diamond.add_edge("plan", "geo")
diamond.add_edge("math", "synth")
diamond.add_edge("geo",  "synth")
diamond.set_entry_point("plan")
diamond.set_max_node_executions(8)
diamond.set_execution_timeout(180)
diamond.set_node_timeout(60)

g4 = diamond.build()

print("--- running diamond: planner → math+geo (parallel?) → synthesizer ---")
g4_result = g4(
    "What is 13 multiplied by 8? Also, what is the capital of Australia? "
    "Answer both questions."
)
# Extract just the final synthesizer answer
synth_text = g4_result.results.get("synth")
if synth_text:
    text = synth_text.result.message["content"][0]["text"]
    print(f"Synthesizer says: {text.strip()}")
else:
    print(f"Graph result status: {g4_result.status}")


# ---------------------------------------------------------------------------
# ITERATION 5: Compliant streaming — enable_a2a_compliant_streaming=True
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 5: Compliant streaming — spec-compliant SSE wire format")
print("=" * 70)
print("""
The SDK warns on every request that legacy mode doesn't conform to the A2A spec.
enable_a2a_compliant_streaming=True switches to artifact-update events
with a last_chunk flag — the format the spec requires.

Question answered here: does A2AAgent (client) handle both wire formats?

SERVER: new math server on :9102, compliant mode ON
CLIENT: same A2AAgent — call syntax unchanged
""")

math_compliant_agent = Agent(
    name="math_compliant",
    description="A maths specialist serving spec-compliant A2A streaming.",
    model=model,
    tools=[calculator],
    callback_handler=None,
)

print("Starting math_compliant on :9102 (enable_a2a_compliant_streaming=True) ...")
start_server_bg(
    math_compliant_agent,
    port=9102,
    enable_a2a_compliant_streaming=True,   # ← the only change vs iter 1
)
print("Server ready.\n")

compliant_remote = A2AAgent(endpoint="http://127.0.0.1:9102")

print("--- agent card ---")
card5 = asyncio.run(compliant_remote.get_agent_card())
print(f"  name:      {card5.name}")
print(f"  streaming: {card5.capabilities.streaming}")

print("\n--- call against compliant server (same syntax as iter 1) ---")
result5 = compliant_remote("Use the calculator to compute 13 * 8. Report the number only.")
print(f"  result: {result5}")
print("  (no UserWarning → A2AAgent handles compliant wire format transparently)")


# ---------------------------------------------------------------------------
# ITERATION 6: Dynamic discovery — a2a_discover_agent at runtime
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 6: Dynamic discovery — add a remote agent at runtime")
print("=" * 70)
print("""
In iterations 2-3 the provider was seeded with known URLs at construction.
Real systems often learn about agents dynamically (service registry, handoff).

Flow:
  1. Provider pre-seeded with ONLY math :9100
  2. History specialist starts on :9103 (unknown to provider at init)
  3. Orchestrator calls a2a_discover_agent("http://127.0.0.1:9103") at runtime
  4. Orchestrator lists agents — now sees both math + history
  5. Routes tasks to each specialist
""")

history_agent = Agent(
    name="history_specialist",
    description="An expert in world history, dates, and historical events.",
    model=model,
    callback_handler=None,
)

print("Starting history_specialist on :9103 (NOT pre-seeded in provider) ...")
start_server_bg(history_agent, port=9103)
print("Server ready.\n")

# Provider knows only math at construction — history is unknown
provider6 = A2AClientToolProvider(known_agent_urls=["http://127.0.0.1:9100"])

orchestrator6 = Agent(
    model=model,
    tools=provider6.tools,
    callback_handler=None,
    system_prompt=(
        "You are an orchestrator. You can discover new A2A agents at runtime "
        "using the discover tool, then route tasks to the right specialists."
    ),
)

print("--- orchestrator discovers history specialist, then queries both ---")
result6 = orchestrator6(
    "Step 1: discover http://127.0.0.1:9103. "
    "Step 2: list all discovered agents. "
    "Step 3: ask the math specialist to compute 7 * 11. "
    "Step 4: ask the history specialist in what year World War 2 ended. "
    "Summarise all answers."
)
print(f"Result:\n{result6}")


# ---------------------------------------------------------------------------
# ITERATION 7: A2A + Workflow hybrid — remote agents inside a DAG
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 7: A2A + Workflow hybrid — remote agents as workflow tools")
print("=" * 70)
print("""
L31 Workflow tasks run as sub-agents with specified tools.
Wrap an A2AAgent call in a @tool function so workflow tasks can delegate
computation to remote agents — merging L31 DAG orchestration with L32
network transparency.

Workflow DAG:
  [remote_calc_a]  ← task uses @tool ask_math → calls :9100
  [remote_calc_b]  ← task uses @tool ask_math → calls :9100
        \\        /
      [local_sum]  ← local task adds the two remote results
""")


@tool
def ask_math_specialist(question: str) -> str:
    """Ask the remote math specialist agent to answer an arithmetic question.

    Args:
        question: The arithmetic question to ask.

    Returns:
        The specialist's answer as a string.
    """
    result = math_remote(question)
    return str(result)


# Parent agent needs workflow + ask_math_specialist + calculator
# (calculator in tasks so they don't inherit workflow, preventing recursion)
hybrid_agent = Agent(
    model=model,
    tools=[workflow, ask_math_specialist, calculator],
    callback_handler=None,
)

WF_ID = "l32_hybrid"

print("--- create hybrid workflow ---")
show_wf = lambda r: print(
    next((i["text"] for i in r.get("content", []) if "text" in i), ""), end=""
)
show_wf(hybrid_agent.tool.workflow(
    action="create",
    workflow_id=WF_ID,
    tasks=[
        {
            "task_id": "remote_a",
            "description": (
                "Use ask_math_specialist to compute: what is 15 * 17? "
                "Return the number only."
            ),
            "tools": ["ask_math_specialist"],
            "priority": 5,
        },
        {
            "task_id": "remote_b",
            "description": (
                "Use ask_math_specialist to compute: what is 23 * 11? "
                "Return the number only."
            ),
            "tools": ["ask_math_specialist"],
            "priority": 5,
        },
        {
            "task_id": "local_sum",
            "description": (
                "Use the calculator to add the two numbers from remote_a and remote_b. "
                "State: 'X + Y = Z'."
            ),
            "tools": ["calculator"],
            "dependencies": ["remote_a", "remote_b"],
            "priority": 3,
        },
    ],
))

print("\n--- start workflow (remote tasks call :9100 via ask_math_specialist) ---")
show_wf(hybrid_agent.tool.workflow(action="start", workflow_id=WF_ID))

print("\n--- status ---")
show_wf(hybrid_agent.tool.workflow(action="status", workflow_id=WF_ID))

print("\n--- delete ---")
show_wf(hybrid_agent.tool.workflow(action="delete", workflow_id=WF_ID))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("L32 COMPLETE — Key Takeaways")
print("=" * 70)
print("""
1. A2AServer — wrap any Agent for network access
   • from strands.multiagent.a2a import A2AServer
   • A2AServer(agent=..., host="127.0.0.1", port=N)
   • serve() → blocking uvicorn; to_starlette_app() for background threads
   • Endpoints: GET /.well-known/agent.json (AgentCard discovery)
                POST /a2a                   (task execution)
   • Agent MUST have name= and description= (used in AgentCard)

2. A2AAgent — remote as local
   • from strands.agent.a2a_agent import A2AAgent
   • A2AAgent(endpoint="http://host:port")
   • remote("task")         → AgentResult  ← same syntax as Agent("task")
   • asyncio.run(remote.get_agent_card()) → AgentCard  ← capability discovery
   • Extends AgentBase → drop-in anywhere a local Agent is accepted

3. A2AClientToolProvider — LLM-driven routing
   • from strands_tools.a2a_client import A2AClientToolProvider
   • A2AClientToolProvider(known_agent_urls=[...])
   • provider.tools → [a2a_discover_agent, a2a_list_discovered_agents,
                        a2a_send_message]
   • Agent(tools=provider.tools): LLM decides who to call and when

4. Diamond graph — fan-out to two A2AAgent nodes, local fan-in
   • add_edge("plan", "math"), add_edge("plan", "geo")  → two branches
   • add_edge("math", "synth"), add_edge("geo", "synth") → merge
   • GraphBuilder may run branches in parallel (same parent, no dependency)
   • result.results["node_id"].result.message["content"][0]["text"] to extract

5. Compliant streaming — enable_a2a_compliant_streaming=True
   • A2AServer default emits UserWarning: legacy != A2A spec
   • start_server_bg(agent, port, enable_a2a_compliant_streaming=True)
   • A2AAgent client handles BOTH wire formats transparently
   • Prefer compliant mode for interop with non-Strands A2A clients

6. Dynamic discovery — a2a_discover_agent at runtime
   • Provider seeded with subset of agents; discovers rest via tool
   • a2a_discover_agent("http://host:port") → adds to cache
   • Enables service-registry patterns: orchestrator learns topology at run time
   • a2a_list_discovered_agents() confirms before routing

7. A2A + Workflow hybrid — @tool wrapper bridges DAG and network
   • @tool def ask_remote(q): return str(A2AAgent(endpoint=...)( q))
   • Workflow task: "tools": ["ask_remote"] → sub-agent calls remote agent
   • Parallel workflow tasks (remote_a, remote_b) → both call :9100 in parallel
   • Fan-in task uses calculator on the two remote results
   • L31 DAG determinism + L32 network transparency = distributed pipelines

8. Graph integration — transparent mixing (any topology)
   • A2AAgent extends AgentBase → GraphBuilder.add_node() accepts it
   • builder.add_node(a2a_agent, "node")  ← identical to local Agent

9. Background server pattern (for scripts)
   • to_starlette_app() + uvicorn.Server + daemon thread + asyncio.run()
   • while not server.started: time.sleep(0.05)
   • start_server_bg(agent, port, **server_kwargs) — pass A2AServer options

10. Caveats
    • A2A is experimental; expect breaking changes across SDK versions
    • Python only ("Not yet supported in TypeScript SDK")
    • install: strands-agents[otel,a2a] + strands-agents-tools
""")

"""
Level 28: SDK Advances — Concurrency, MCP Tasks, Hooks, Declarative Config
===========================================================================
Strands SDK 1.19.x — four focused iterations, each with running proof.

Goal: parallel tool execution, typed hook system, MCP task lifecycle,
      declarative agent config.

Depends on: L9 (MCP), L21 (Observability/hooks pattern)
Unlocks:    L29 (Steering), L30 (Skills Plugin) — both use the HookProvider API

Iterations:
  1. Parallel Execution   — asyncio.gather() + ConcurrentToolExecutor
  2. Hook System          — add_callback (inline) + HookProvider (class-based)
  3. MCP Tasks            — asyncio simulation of the full task lifecycle
  4. config_to_agent      — declarative dict + JSON file agent creation

Usage:
    uv run python 11_platform/sdk_advances.py

Key insight (concurrency):
    ConcurrentToolExecutor fires only when the LLM returns multiple tool_use
    blocks in ONE turn. Claude serialises by default. Demonstrate the mechanism
    directly via asyncio, then wire it into the agent for the cases where
    batching does occur.

Key insight (MCP Tasks):
    Strands MCPClient (1.19.x) covers tools/call but not tasks/create.
    The mcp library ships full server-side task infrastructure in
    mcp.server.experimental but FastMCP has no task decorator yet.
    We demonstrate the exact protocol lifecycle in-process with asyncio;
    map each step to the real MCP type names.
"""

import sys
import os
import time
import asyncio
import json
import uuid
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands.hooks import (
    HookProvider,
    HookRegistry,
    BeforeToolCallEvent,
    AfterToolCallEvent,
    BeforeInvocationEvent,
    AfterInvocationEvent,
    MessageAddedEvent,
)
from strands.tools.executors.concurrent import ConcurrentToolExecutor
from strands.experimental.agent_config import config_to_agent
from tools import get_model


# =============================================================================
# ITERATION 1: Parallel Execution
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 1: Parallel Execution")
print("=" * 70)
print("""
Two layers:
  A) asyncio.gather() — direct proof of parallel tool execution (3x speedup)
  B) ConcurrentToolExecutor — agent-integrated version; fires when LLM batches
""")

TOOL_SLEEP = 1.0


@tool
def fetch_population(city: str) -> dict:
    """Fetch population data for a city (simulates I/O latency)."""
    time.sleep(TOOL_SLEEP)
    return {"city": city, "population": 4_618_000}


@tool
def fetch_gdp(city: str) -> dict:
    """Fetch GDP data for a city (simulates I/O latency)."""
    time.sleep(TOOL_SLEEP)
    return {"city": city, "gdp_usd_bn": 110}


@tool
def fetch_crime_index(city: str) -> dict:
    """Fetch crime index for a city (simulates I/O latency)."""
    time.sleep(TOOL_SLEEP)
    return {"city": city, "crime_index": 67.4}


# --- 1A: Direct asyncio parallel execution ---
print("-" * 50)
print("1A: asyncio.gather() — direct parallel proof")
print("-" * 50)


async def run_tools_parallel(city: str) -> list[dict]:
    """Run three slow tools concurrently using asyncio.to_thread."""
    return await asyncio.gather(
        asyncio.to_thread(fetch_population, city),
        asyncio.to_thread(fetch_gdp, city),
        asyncio.to_thread(fetch_crime_index, city),
    )


async def run_tools_sequential(city: str) -> list[dict]:
    """Run three slow tools one-at-a-time for comparison."""
    return [
        fetch_population(city),
        fetch_gdp(city),
        fetch_crime_index(city),
    ]


print("\n[Sequential]")
t0 = time.time()
seq_results = asyncio.run(run_tools_sequential("Johannesburg"))
t_seq = time.time() - t0
for r in seq_results:
    print(f"  {r}")
print(f"Time: {t_seq:.2f}s  (expected ≈ {TOOL_SLEEP * 3:.1f}s)")

print("\n[Parallel — asyncio.gather()]")
t0 = time.time()
par_results = asyncio.run(run_tools_parallel("Johannesburg"))
t_par = time.time() - t0
for r in par_results:
    print(f"  {r}")
print(f"Time: {t_par:.2f}s  (expected ≈ {TOOL_SLEEP:.1f}s)")
print(f"Speedup: {t_seq / t_par:.1f}x ✓" if t_seq / t_par >= 2 else f"Speedup: {t_seq / t_par:.1f}x")

# --- 1B: ConcurrentToolExecutor in Agent ---
print("\n" + "-" * 50)
print("1B: ConcurrentToolExecutor — agent-integrated")
print("-" * 50)
print("""
ConcurrentToolExecutor applies the same asyncio.gather() pattern inside the
agent event loop automatically, but ONLY when the LLM returns multiple
tool_use blocks in a single response turn.

  API (all versions):  Agent(..., tool_executor=ConcurrentToolExecutor())

  NOTE: Agent(..., concurrent_invocation_mode=...) is v1.30+ but controls
  thread-safety for simultaneous agent *calls* from multiple threads — NOT
  parallel tool execution. For parallel tools, ConcurrentToolExecutor is
  always the right API.

Claude serialises tool calls by default, so the speedup is only visible when
the model batches — which does occur with explicit system prompts and certain
models. Wire it in defensively so the speedup is captured whenever it happens.
""")

model = get_model("haiku")

agent_con = Agent(
    model=model,
    system_prompt=(
        "You are a data assistant. When asked for multiple data points, "
        "always issue ALL tool calls in a single batched response."
    ),
    tools=[fetch_population, fetch_gdp, fetch_crime_index],
    callback_handler=None,
    tool_executor=ConcurrentToolExecutor(),
)

t0 = time.time()
result = agent_con(
    "Fetch population, GDP, and crime index for Cape Town — all three at once."
)
t_agent = time.time() - t0
print(result)
print(f"\nAgent + ConcurrentToolExecutor: {t_agent:.2f}s")
print("(Speedup visible when LLM batches; falls back gracefully if serialised.)")


# =============================================================================
# ITERATION 2: Hook System
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 2: Hook System")
print("=" * 70)


@tool
def word_count(text: str) -> dict:
    """Count words, characters, and sentences in a text."""
    words = text.split()
    sentences = text.count(".") + text.count("!") + text.count("?")
    return {"words": len(words), "chars": len(text), "sentences": max(sentences, 1)}


# --- 2A: Inline add_callback ---
print("\n" + "-" * 50)
print("2A: Inline add_callback — simplest hook wiring")
print("-" * 50)
print("""
  SDK v1.19 API:  agent.hooks.add_callback(EventType, fn)
  SDK v1.26+ API: agent.add_hook(event="before_tool_call", handler=fn)  [planned]
""")

agent_inline = Agent(model=model, tools=[word_count], callback_handler=None)

call_log: list[str] = []


def on_before(event: BeforeToolCallEvent) -> None:
    name = event.tool_use["name"]
    call_log.append(name)
    print(f"  → before_tool_call: {name}  input={dict(list(event.tool_use.get('input', {}).items())[:2])}")


def on_after(event: AfterToolCallEvent) -> None:
    print(f"  ← after_tool_call:  {event.tool_use['name']}")


agent_inline.hooks.add_callback(BeforeToolCallEvent, on_before)
agent_inline.hooks.add_callback(AfterToolCallEvent, on_after)

result = agent_inline("Count the words in: 'The quick brown fox jumps over the lazy dog.'")
print(result)
print(f"Captured: {call_log}")

# --- 2B: HookProvider class ---
print("\n" + "-" * 50)
print("2B: HookProvider — composable, reusable hook bundles")
print("-" * 50)


class TimingHooks(HookProvider):
    """Records wall-clock time per invocation and per tool call."""

    def __init__(self, label: str = "timer"):
        self.label = label
        self._t_invoke: float = 0.0
        self._t_tools: dict[str, float] = {}

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeInvocationEvent, self._start)
        registry.add_callback(AfterInvocationEvent, self._end)
        registry.add_callback(BeforeToolCallEvent, self._tool_start)
        registry.add_callback(AfterToolCallEvent, self._tool_end)

    def _start(self, event: BeforeInvocationEvent) -> None:
        self._t_invoke = time.perf_counter()
        print(f"  [{self.label}] invocation start")

    def _end(self, event: AfterInvocationEvent) -> None:
        elapsed = time.perf_counter() - self._t_invoke
        print(f"  [{self.label}] invocation end  ({elapsed:.3f}s total)")

    def _tool_start(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]
        self._t_tools[name] = time.perf_counter()
        print(f"  [{self.label}] tool start: {name}")

    def _tool_end(self, event: AfterToolCallEvent) -> None:
        name = event.tool_use["name"]
        elapsed = time.perf_counter() - self._t_tools.get(name, time.perf_counter())
        print(f"  [{self.label}] tool end:   {name}  ({elapsed:.3f}s)")


class MessageAuditHooks(HookProvider):
    """Logs role + content length for every message added to history."""

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(MessageAddedEvent, self._on_msg)

    def _on_msg(self, event: MessageAddedEvent) -> None:
        role = event.message.get("role", "?")
        length = len(str(event.message.get("content", "")))
        print(f"  [audit] msg added  role={role}  len={length}")


# Multiple providers compose cleanly — pass as hooks=[...]
agent_hooks = Agent(
    model=model,
    tools=[word_count],
    callback_handler=None,
    hooks=[TimingHooks("perf"), MessageAuditHooks()],
)

result = agent_hooks("How many words are in: 'To be or not to be, that is the question.'")
print(result)


# =============================================================================
# ITERATION 3: MCP Tasks — Protocol Lifecycle Simulation
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 3: MCP Tasks — Protocol Lifecycle")
print("=" * 70)
print("""
MCP defines three primitive server content types:
  Resources  — static/queryable data (file contents, DB rows)
  Prompts    — reusable prompt templates
  Tasks      — async work units that return immediately with a task_id

Tasks use a distinct protocol from tools:
  tools/call    → blocking; returns result in same response
  tasks/create  → non-blocking; returns {task_id, status: "working"} immediately
  tasks/get     → poll for current status
  tasks/result  → retrieve result when status == "completed"
  tasks/cancel  → abort

Strands MCPClient 1.19.x covers tools/call but not the tasks/ endpoints.
mcp.server.experimental has full server-side infrastructure (TaskSupport,
ServerTaskContext, InMemoryTaskStore) but no FastMCP decorator yet.

Below: an asyncio simulation of the exact task lifecycle using the real
mcp.types names. This is the same pattern a real MCP task server runs —
just in-process rather than over stdio.
""")

# --- MCP Task lifecycle types (mirroring mcp.types) ---
from mcp.types import (
    TASK_STATUS_WORKING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_CANCELLED,
)


@dataclass
class SimTask:
    """Mirrors mcp.types.Task — the object a client receives after tasks/create."""
    task_id: str
    status: str  # TASK_STATUS_* constants
    status_message: str = ""
    result: Any = None
    error: str = ""


class InProcessTaskServer:
    """
    Asyncio simulation of an MCP tasks endpoint.

    Mirrors the protocol:
        tasks/create  → _create()
        tasks/get     → _get()
        tasks/result  → _result()
        tasks/cancel  → _cancel()

    A real MCP server implementation would use:
        mcp.server.lowlevel.Server + server.experimental.enable_tasks()
        with mcp.server.experimental.task_context.ServerTaskContext
    """

    def __init__(self) -> None:
        self._store: dict[str, SimTask] = {}

    async def create(self, fn, *args, **kwargs) -> SimTask:
        """tasks/create — fires immediately; runs work in background."""
        task_id = str(uuid.uuid4())[:8]
        task = SimTask(task_id=task_id, status=TASK_STATUS_WORKING,
                       status_message="Task accepted, working...")
        self._store[task_id] = task

        # Background coroutine — mirrors server spawning a task group worker
        asyncio.create_task(self._run_worker(task, fn, args, kwargs))
        return task

    async def _run_worker(self, task: SimTask, fn, args, kwargs) -> None:
        try:
            task.status_message = "Processing..."
            result = await asyncio.to_thread(fn, *args, **kwargs)
            task.result = result
            task.status = TASK_STATUS_COMPLETED
            task.status_message = "Done."
        except Exception as exc:
            task.error = str(exc)
            task.status = TASK_STATUS_FAILED
            task.status_message = f"Failed: {exc}"

    def get(self, task_id: str) -> SimTask:
        """tasks/get — returns current status (what a client polls)."""
        task = self._store.get(task_id)
        if task is None:
            raise KeyError(f"Unknown task_id: {task_id}")
        return task

    def result(self, task_id: str) -> Any:
        """tasks/result — returns the payload; raises if not completed."""
        task = self.get(task_id)
        if task.status != TASK_STATUS_COMPLETED:
            raise RuntimeError(f"Task {task_id} not completed (status={task.status})")
        return task.result

    def cancel(self, task_id: str) -> None:
        """tasks/cancel — marks task as cancelled."""
        task = self.get(task_id)
        task.status = TASK_STATUS_CANCELLED
        task.status_message = "Cancelled by client."


# --- A slow "report generation" function — simulates real async work ---
def generate_city_report(city: str) -> dict:
    """Slow city report — simulates a multi-step data pipeline (2s)."""
    time.sleep(2)
    return {
        "city": city,
        "report": f"Comprehensive analysis of {city}",
        "sections": ["demographics", "economy", "infrastructure"],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


async def demo_task_lifecycle() -> None:
    server = InProcessTaskServer()

    print("── tasks/create ──────────────────────────────")
    t0 = time.time()
    task = await server.create(generate_city_report, "Nairobi")
    t_create = time.time() - t0
    print(f"  task_id : {task.task_id}")
    print(f"  status  : {task.status}  ({t_create*1000:.0f}ms — non-blocking ✓)")
    print(f"  message : {task.status_message}")

    # Client is free to do other work while the task runs
    print("\n── client does other work (non-blocking) ─────")
    for i in range(1, 4):
        await asyncio.sleep(0.5)
        current = server.get(task.task_id)
        print(f"  [{i * 500}ms] tasks/get → status={current.status}")
        if current.status in (TASK_STATUS_COMPLETED, TASK_STATUS_FAILED, TASK_STATUS_CANCELLED):
            break

    # Poll until done
    while server.get(task.task_id).status == TASK_STATUS_WORKING:
        await asyncio.sleep(0.2)

    print("\n── tasks/result ──────────────────────────────")
    report = server.result(task.task_id)
    for k, v in report.items():
        print(f"  {k}: {v}")

    print("\n── cancel demo ───────────────────────────────")
    task2 = await server.create(generate_city_report, "Lagos")
    print(f"  created task {task2.task_id}  status={task2.status}")
    await asyncio.sleep(0.3)
    server.cancel(task2.task_id)
    print(f"  after cancel: status={server.get(task2.task_id).status}")

    t_total = time.time() - t0
    print(f"\nTotal wall time: {t_total:.2f}s  (without non-blocking: would be 4s+)")


asyncio.run(demo_task_lifecycle())

print("""
Protocol note:
  The simulation above maps 1-to-1 with real MCP tasks/ endpoints.
  To deploy as a real MCP server:
    1. Use mcp.server.lowlevel.Server
    2. Call server.experimental.enable_tasks() (in-memory store built-in)
    3. Register task handlers using ServerTaskContext from
       mcp.server.experimental.task_context
    4. Client connects via MCPClient; calls session.send_request("tasks/create")
  Full server-side support lands in Strands MCPClient ≥ 1.23.0.
""")


# =============================================================================
# ITERATION 4: Declarative Agent Config
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 4: Declarative Agent Config — config_to_agent")
print("=" * 70)
print("""
strands.experimental.agent_config.config_to_agent(config, **kwargs)

Config schema (JSON Draft-7 validated):
  { "name": str, "model": str, "prompt": str, "tools": [str] }

Two forms: dict (in-memory) and JSON file (file:// or path string).
Extra kwargs forwarded directly to Agent() — use for model, callback_handler, etc.
""")


@tool
def current_temperature(city: str) -> dict:
    """Get the current temperature for a city."""
    return {"city": city, "temp_c": 21, "feels_like_c": 19}


# --- 4A: Dict config ---
print("-" * 50)
print("4A: Dict config")
print("-" * 50)

dict_config = {
    "name": "WeatherBriefing",
    "prompt": "You are a concise weather briefing assistant. Answer in one sentence.",
}

agent_dict = config_to_agent(
    dict_config,
    model=get_model("haiku"),
    tools=[current_temperature],
    callback_handler=None,
)

print(f"Created: name={agent_dict.name!r}  type={type(agent_dict).__name__}")
result = agent_dict("What's the temperature in Durban?")
print(f"Response: {result}")

# --- 4B: JSON file config ---
print("\n" + "-" * 50)
print("4B: JSON file config")
print("-" * 50)

file_config = {
    "name": "EconomyBriefing",
    "prompt": "You are a concise economic briefing assistant. Answer in one sentence.",
}

with tempfile.NamedTemporaryFile(
    mode="w", suffix=".json", delete=False, prefix="agent_config_"
) as f:
    json.dump(file_config, f)
    config_path = f.name

print(f"Config written to: {config_path}")

agent_file = config_to_agent(
    config_path,  # path string — config_to_agent resolves it automatically
    model=get_model("haiku"),
    tools=[fetch_gdp],
    callback_handler=None,
)

print(f"Created: name={agent_file.name!r}  type={type(agent_file).__name__}")
result = agent_file("What's the GDP of Johannesburg?")
print(f"Response: {result}")

os.unlink(config_path)

print("""
Limitation: tools needing constructor args can't be declared in the JSON.
Add them programmatically after creation:
    agent = config_to_agent(config)
    agent.tool_registry.process_tools([MyTool(HttpConn("localhost"))])
""")

# =============================================================================
# Summary
# =============================================================================
print("\n" + "=" * 70)
print("L28 COMPLETE — Key Takeaways")
print("=" * 70)
print("""
1. Parallel Execution
   • asyncio.gather() + asyncio.to_thread() gives provable 3x speedup on I/O tools
   • ConcurrentToolExecutor is the agent-integrated version of the same pattern
   • SDK v1.19 API: tool_executor=ConcurrentToolExecutor()
   • SDK v1.26+ API: concurrent_invocation_mode=True  (planned)
   • Caveat: Claude serialises tool calls by default; speedup fires when LLM batches

2. Hook System
   • agent.hooks.add_callback(EventType, fn) — inline, per-agent
   • HookProvider protocol — composable class-based bundles
   • Constructor: Agent(..., hooks=[Provider1(), Provider2()])
   • Events: BeforeInvocation, AfterInvocation, BeforeToolCall, AfterToolCall,
             MessageAdded, BeforeModelCall, AfterModelCall

3. MCP Tasks
   • tasks/create is non-blocking — returns task_id immediately
   • Client polls tasks/get; retrieves payload via tasks/result
   • mcp.server.experimental has InMemoryTaskStore + ServerTaskContext
   • Strands MCPClient tasks/ support lands in ≥ 1.23.0
   • Pattern: fire → free client → poll → result (vs blocking tools/call)

4. config_to_agent  (strands.experimental.agent_config)
   • Dict: config_to_agent({name, prompt, tools}, model=..., ...)
   • File: config_to_agent("/path/to/config.json", ...)
   • Schema validated (JSON Draft-7) at load time
   • Extra kwargs forwarded to Agent() constructor
""")

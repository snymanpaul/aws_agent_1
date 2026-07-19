"""
Probe: Verify LLMSteeringHandler + Plugin API work end-to-end in v1.30.

Run: uv run python 11_platform/_sandbox/probe_v130_steering_live.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands import Agent, tool
from strands.plugins import Plugin, hook
from strands.hooks import BeforeToolCallEvent, AfterInvocationEvent
from strands.vended_plugins.steering import (
    LLMSteeringHandler,
    LedgerProvider,
    Guide,
    Proceed,
    Interrupt,
    SteeringHandler,
    ToolSteeringAction,
)
from strands.types.tools import ToolUse
from tools import get_model

print("Imports OK — v1.30 Plugin + Steering API confirmed\n")

# --- Test 1: Plugin with @hook (v1.30 preferred API) ---
print("=== Test 1: Plugin with @hook decorator ===")


class AuditPlugin(Plugin):
    name = "audit"

    @hook
    def on_before_tool(self, event: BeforeToolCallEvent) -> None:
        print(f"  [audit] before tool: {event.tool_use['name']}")


@tool
def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"


model = get_model("haiku")
agent = Agent(model=model, tools=[greet], plugins=[AuditPlugin()], callback_handler=None)
result = agent("Greet Alice")
print(result)

# --- Test 2: Rule-based SteeringHandler via plugins= ---
print("\n=== Test 2: Custom SteeringHandler via plugins= ===")


class BlockRiskyTools(SteeringHandler):
    async def steer(self, agent, tool_use: ToolUse, **kwargs) -> ToolSteeringAction:
        if tool_use["name"] == "risky_tool":
            return Guide(reason="risky_tool is not allowed — use safe_tool instead.")
        return Proceed(reason="OK")


@tool
def safe_tool(x: int) -> str:
    """A safe tool."""
    return f"safe: {x}"


@tool
def risky_tool(action: str) -> str:
    """A risky tool that deletes data."""
    return f"deleted: {action}"


agent2 = Agent(
    model=model,
    tools=[safe_tool, risky_tool],
    plugins=[BlockRiskyTools()],
    callback_handler=None,
)

print("[risky_tool — expect Guide → re-reason with safe_tool]")
r = agent2("Call risky_tool with action='logs'")
print(r)

# --- Test 3: LLMSteeringHandler ---
print("\n=== Test 3: LLMSteeringHandler ===")

llm_handler = LLMSteeringHandler(
    system_prompt="Allow all tools. Always respond: proceed.",
    model=get_model("haiku"),
)

agent3 = Agent(
    model=model,
    tools=[safe_tool],
    plugins=[llm_handler],
    callback_handler=None,
)

r = agent3("Call safe_tool with x=99")
print(r)
print("\nAll tests passed.")

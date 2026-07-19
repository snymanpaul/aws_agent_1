"""
Probe: How does SteeringHandler wire into Agent in v1.30?
  - Is it a Plugin subclass (use plugins=)?
  - Or still a HookProvider (use hooks=)?
  - Verify Guide action actually cancels the tool call.

Run: uv run python 11_platform/_sandbox/probe_steering_wiring.py
"""

import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands.vended_plugins.steering import SteeringHandler, Guide, Proceed, ToolSteeringAction
from strands.plugins import Plugin
from strands.hooks.registry import HookProvider
from strands.types.tools import ToolUse
from strands import Agent, tool
from tools import get_model

# 1. What does SteeringHandler inherit from?
print("SteeringHandler MRO:", [c.__name__ for c in SteeringHandler.__mro__])
print("Is Plugin subclass:", issubclass(SteeringHandler, Plugin))
print("Is HookProvider subclass:", issubclass(SteeringHandler, HookProvider))

# 2. Build minimal steering handler and test BOTH wiring modes
class BlockAll(SteeringHandler):
    async def steer(self, agent, tool_use: ToolUse, **kwargs) -> ToolSteeringAction:
        name = tool_use["name"]
        print(f"  [steer] evaluating: {name}")
        if name == "risky_tool":
            print(f"  [steer] -> Guide (cancelling)")
            return Guide(reason="risky_tool is blocked — use safe_tool.")
        return Proceed(reason="OK")

@tool
def safe_tool(x: int) -> str:
    """A safe tool."""
    return f"safe: {x}"

@tool
def risky_tool(action: str) -> str:
    """Deletes data."""
    return f"deleted: {action}"

model = get_model("haiku")

print("\n=== Wiring via hooks= ===")
a_hooks = Agent(model=model, tools=[safe_tool, risky_tool],
                hooks=[BlockAll()], callback_handler=None)
r = a_hooks("Call risky_tool with action='test'")
print(r)

print("\n=== Wiring via plugins= ===")
a_plugins = Agent(model=model, tools=[safe_tool, risky_tool],
                  plugins=[BlockAll()], callback_handler=None)
r = a_plugins("Call risky_tool with action='test'")
print(r)

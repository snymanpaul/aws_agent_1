"""
Probe: Hook system — verify add_callback and HookProvider in SDK 1.19.x

Tests:
  1. agent.hooks.add_callback(EventType, fn) — inline registration
  2. HookProvider protocol — class-based bulk registration
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands import Agent, tool
from strands.hooks import (
    HookProvider,
    HookRegistry,
    BeforeToolCallEvent,
    AfterToolCallEvent,
    BeforeInvocationEvent,
    AfterInvocationEvent,
)
from tools import get_model

model = get_model("haiku")


@tool
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


# --- 1. Inline add_callback ---
print("=== Test 1: inline add_callback ===")

agent1 = Agent(model=model, tools=[greet], callback_handler=None)


def before_tool(event: BeforeToolCallEvent):
    print(f"  [before_tool] tool={event.tool_use['name']}")


def after_tool(event: AfterToolCallEvent):
    print(f"  [after_tool]  tool={event.tool_use['name']}")


agent1.hooks.add_callback(BeforeToolCallEvent, before_tool)
agent1.hooks.add_callback(AfterToolCallEvent, after_tool)

result = agent1("Greet Alice")
print(result)

# --- 2. HookProvider class ---
print("\n=== Test 2: HookProvider class ===")


class AuditHooks(HookProvider):
    def __init__(self, label: str):
        self.label = label

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeInvocationEvent, self.on_start)
        registry.add_callback(AfterInvocationEvent, self.on_end)
        registry.add_callback(BeforeToolCallEvent, self.on_tool)

    def on_start(self, event: BeforeInvocationEvent):
        print(f"  [{self.label}] invocation started")

    def on_end(self, event: AfterInvocationEvent):
        print(f"  [{self.label}] invocation ended")

    def on_tool(self, event: BeforeToolCallEvent):
        print(f"  [{self.label}] tool call: {event.tool_use['name']}")


agent2 = Agent(model=model, tools=[greet], callback_handler=None, hooks=[AuditHooks("audit")])
result = agent2("Greet Bob")
print(result)

"""
Probe: Verify basic steering wiring in SDK 1.19.x

Tests:
  1. Custom SteeringHandler (rule-based, no LLM) — Proceed, Guide, Interrupt
  2. LLMSteeringHandler — basic wiring and structured output decision

Run: uv run python 11_platform/_sandbox/probe_steering_basic.py
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands import Agent, tool
from strands.experimental.steering import (
    SteeringHandler,
    LLMSteeringHandler,
    LedgerProvider,
    Guide,
    Proceed,
    Interrupt,
    SteeringAction,
)
from strands.types.tools import ToolUse
from tools import get_model


@tool
def safe_tool(x: int) -> str:
    """A safe, approved tool."""
    return f"safe result: {x}"


@tool
def risky_tool(action: str) -> str:
    """A risky tool that deletes things."""
    return f"deleted: {action}"


@tool
def dangerous_tool(target: str) -> str:
    """An extremely dangerous tool."""
    return f"destroyed: {target}"


# --- Test 1: Rule-based custom handler ---
print("=== Test 1: Rule-based SteeringHandler ===\n")


class RuleBasedSteering(SteeringHandler):
    """Deterministic steering — no LLM call, fast and predictable."""

    BLOCKED = {"dangerous_tool"}
    GUIDED  = {"risky_tool"}

    async def steer(self, agent: "Agent", tool_use: ToolUse, **kwargs) -> SteeringAction:
        name = tool_use["name"]
        if name in self.BLOCKED:
            return Interrupt(reason=f"{name} requires human approval before proceeding.")
        if name in self.GUIDED:
            return Guide(reason=f"{name} is risky — consider using safe_tool instead.")
        return Proceed(reason="Tool approved.")


model = get_model("haiku")
agent1 = Agent(
    model=model,
    tools=[safe_tool, risky_tool, dangerous_tool],
    callback_handler=None,
    hooks=[RuleBasedSteering()],
)

# Should proceed
print("[safe_tool — expect: Proceed]")
r = agent1("Call safe_tool with x=42")
print(r)

# Should guide (tool cancelled, agent re-reasons)
print("\n[risky_tool — expect: Guide → agent finds alternative]")
r = agent1("Call risky_tool with action='old_files'")
print(r)

# --- Test 2: LLMSteeringHandler ---
print("\n=== Test 2: LLMSteeringHandler (LLM-based policy) ===\n")

POLICY = """\
You are a data governance steering agent.
Evaluate each tool call and decide:
- proceed: tool is safe and appropriate
- guide:   tool call looks risky; suggest a safer alternative
- interrupt: tool would cause irreversible harm; require human approval
"""

llm_handler = LLMSteeringHandler(
    system_prompt=POLICY,
    model=get_model("haiku"),
    context_providers=[LedgerProvider()],
)

agent2 = Agent(
    model=model,
    tools=[safe_tool, risky_tool],
    callback_handler=None,
    hooks=[llm_handler],
)

print("[safe_tool via LLM policy]")
r = agent2("Call safe_tool with x=7")
print(r)

print("\n[risky_tool via LLM policy]")
r = agent2("Call risky_tool with action='production_db'")
print(r)

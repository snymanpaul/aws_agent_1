"""
Level 29: Strands Steering — Contextual Guidance via the Plugin API
====================================================================
Strands SDK 1.30.x — three focused iterations.

Goal: inject context-aware guidance at two lifecycle points without modifying
agent code. Steering sits *beside* the agent as a plugin, not inside it.

Depends on: L28 (HookProvider pattern), L22 (safety — know what you're steering from)
Unlocks:    L30 (Skills Plugin — same Plugin base class)

Two injection points (v1.30):
  steer_before_tool()  — evaluate intent; Proceed | Guide | Interrupt
  steer_after_model()  — evaluate response; Proceed | Guide (retry)

Three before-tool actions:
  Proceed(reason)   — allow tool call through unchanged
  Guide(reason)     — cancel call; inject reason as feedback; agent re-reasons
  Interrupt(reason) — pause for human approval; cancel if denied

One extra after-model action:
  Guide(reason)     — discard model response; add reason to conversation; retry

vs L22 Safety:     L22 = hard block (raises exception)
                   L29 = contextual guidance (agent re-reasons with feedback)
vs L28 Hooks:      Hooks = observe/measure; Steering = actively redirect

Usage:
    uv run python 11_platform/steering.py

Architecture:
    Agent receives prompt
         |
         v
    [LLM reasons] --> tool calls
         |
    BeforeToolCallEvent
         |
    SteeringHandler.steer_before_tool()
         |
    +----+----+--------+
    |         |        |
  Proceed   Guide  Interrupt
    |         |        |
  tool   cancel +  human
  runs   feedback  approval
         |
    agent re-reasons
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands.plugins import Plugin, hook
from strands.hooks import BeforeToolCallEvent, AfterInvocationEvent
from strands.types.content import Message
from strands.types.streaming import StopReason
from strands.vended_plugins.steering import (
    LLMSteeringHandler,
    LedgerProvider,
    Guide,
    Proceed,
    Interrupt,
    SteeringHandler,
    ToolSteeringAction,
    ModelSteeringAction,
)
from strands.types.tools import ToolUse
from tools import get_model


# =============================================================================
# Shared tools used across iterations
# =============================================================================

@tool
def read_file(path: str) -> str:
    """Read a file from the filesystem."""
    return f"[contents of {path}]"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file — overwrites if it exists."""
    return f"Written {len(content)} bytes to {path}"


@tool
def delete_file(path: str) -> str:
    """Permanently delete a file. This cannot be undone."""
    return f"Deleted {path}"


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to a recipient."""
    return f"Email sent to {to}: {subject}"


@tool
def summarise_text(text: str) -> str:
    """Summarise text into bullet points."""
    return f"Summary: {text[:40]}..."


model = get_model("haiku")


# =============================================================================
# ITERATION 1: Plugin API — the v1.30 primitive
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 1: Plugin API — the v1.30 primitive")
print("=" * 70)
print("""
The Plugin base class (v1.30) replaces HookProvider for composable extensions.

  Plugin =  @hook methods  (lifecycle observers/interceptors)
          + @tool methods  (tools added to the agent)
          + init_agent()   (custom setup logic)

plugins=[MyPlugin()] on Agent registers both hooks AND tools automatically.
@hook infers the event type from the method's type hint — no explicit EventType arg.
""")


class ObserverPlugin(Plugin):
    """Minimal plugin — logs invocation start/end via @hook."""

    name = "observer"

    @hook
    def on_start(self, event: BeforeToolCallEvent) -> None:
        print(f"  [observer] tool call: {event.tool_use['name']}")

    @hook
    def on_end(self, event: AfterInvocationEvent) -> None:
        print("  [observer] invocation complete")


agent_plugin = Agent(
    model=model,
    tools=[read_file, summarise_text],
    plugins=[ObserverPlugin()],
    callback_handler=None,
)

result = agent_plugin("Read the file 'notes.txt' then summarise it.")
print(result)


# =============================================================================
# ITERATION 2: SteeringHandler — before-tool steering
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 2: SteeringHandler — before-tool steering")
print("=" * 70)
print("""
SteeringHandler is a Plugin subclass that fires before every tool call.
Override steer_before_tool() to return Proceed | Guide | Interrupt.

  Proceed(reason)   — tool runs normally
  Guide(reason)     — tool cancelled; reason injected as feedback; agent re-reasons
  Interrupt(reason) — tool paused; human can approve/deny (HITL)
""")


class DataGovernanceSteering(SteeringHandler):
    """
    Policy:
      - delete_file  → always Interrupt (requires explicit approval)
      - send_email   → Guide if recipient looks external (no @company.com)
      - everything else → Proceed
    """

    DESTRUCTIVE = {"delete_file"}
    EXTERNAL_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "outlook.com"}

    async def steer_before_tool(self, *, agent, tool_use: ToolUse, **kwargs) -> ToolSteeringAction:
        name = tool_use["name"]
        args = tool_use.get("input", {})

        if name in self.DESTRUCTIVE:
            return Interrupt(
                reason=f"'{name}' is destructive and irreversible. Explicit human approval required."
            )

        if name == "send_email":
            to = args.get("to", "")
            domain = to.split("@")[-1] if "@" in to else ""
            if domain in self.EXTERNAL_EMAIL_DOMAINS:
                return Guide(
                    reason=(
                        f"Email to external domain '{domain}' is restricted. "
                        "Only @company.com addresses are permitted. "
                        "Ask the user to confirm the recipient."
                    )
                )

        return Proceed(reason="Tool approved by governance policy.")


# --- 2A: Guide in action ---
print("-" * 50)
print("2A: Guide — risky send_email redirected")
print("-" * 50)

agent_steer = Agent(
    model=model,
    tools=[read_file, write_file, send_email],
    plugins=[DataGovernanceSteering()],
    callback_handler=None,
)

result = agent_steer("Send an email to user@gmail.com with subject 'Report' and body 'See attached.'")
print(result)

# --- 2B: Proceed — safe operation passes through ---
print("\n" + "-" * 50)
print("2B: Proceed — safe read_file passes through")
print("-" * 50)

result = agent_steer("Read the file 'config.yaml'")
print(result)


# =============================================================================
# ITERATION 3: steer_after_model — response steering (v1.30 exclusive)
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 3: steer_after_model — response steering")
print("=" * 70)
print("""
v1.30 adds a second injection point: AFTER the model generates a response.
steer_after_model() receives the full response + stop_reason and can:

  Proceed(reason)  — accept response, return to user
  Guide(reason)    — discard response; add reason to conversation; model retries

Use case: enforce tone, format, or completeness requirements without
hardcoding them into the system prompt.
""")


class ToneEnforcementSteering(SteeringHandler):
    """Reject responses that are shorter than 2 sentences (lazy answers)."""

    MAX_RETRIES = 2
    _retry_count: int = 0

    async def steer_after_model(
        self, *, agent, message: Message, stop_reason: StopReason, **kwargs
    ) -> ModelSteeringAction:
        # Extract text from the response message
        content = message.get("content", [])
        text = " ".join(
            block.get("text", "") for block in content
            if isinstance(block, dict) and "text" in block
        )

        sentence_count = text.count(".") + text.count("!") + text.count("?")

        if sentence_count < 2 and self._retry_count < self.MAX_RETRIES:
            self._retry_count += 1
            return Guide(
                reason=(
                    f"Response is too brief ({sentence_count} sentence(s)). "
                    "Please provide a more complete answer with at least 2 sentences."
                )
            )

        self._retry_count = 0
        return Proceed(reason="Response meets quality standard.")


agent_tone = Agent(
    model=model,
    tools=[summarise_text],
    plugins=[ToneEnforcementSteering()],
    system_prompt="You are a helpful assistant. Answer questions concisely.",
    callback_handler=None,
)

result = agent_tone("What is 2 + 2?")
print(result)


# =============================================================================
# ITERATION 4: LLMSteeringHandler + LedgerProvider
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 4: LLMSteeringHandler + LedgerProvider")
print("=" * 70)
print("""
LLMSteeringHandler uses a secondary LLM to evaluate each tool call against
a natural-language policy. No code required to express the rules.

LedgerProvider tracks tool call history (name, args, result, timing) so the
steering LLM can make CONTEXT-AWARE decisions — e.g., notice the agent has
already called send_email once and block a second attempt.
""")

POLICY = """\
You are a data governance agent evaluating tool calls for a financial services firm.

Rules:
1. delete_file — always respond: interrupt
2. send_email — respond: guide  (emails must be reviewed before sending)
3. write_file to paths containing 'prod' or 'production' — respond: guide
4. Everything else — respond: proceed

Be brief. Only return the decision word and a one-sentence reason.
"""

llm_steering = LLMSteeringHandler(
    system_prompt=POLICY,
    model=get_model("haiku"),
    context_providers=[LedgerProvider()],
)

agent_llm = Agent(
    model=model,
    tools=[read_file, write_file, delete_file, send_email],
    plugins=[llm_steering],
    callback_handler=None,
)

print("[Safe: read_file]")
r = agent_llm("Read the file 'report.pdf'")
print(r)

print("\n[Steered: write_file to prod path]")
r = agent_llm("Write 'hello' to '/prod/config.yaml'")
print(r)

print("\n[Steered: send_email]")
r = agent_llm("Send email to finance@company.com with subject 'Q1 Results' and body 'See attached.'")
print(r)

print("\n" + "=" * 70)
print("L29 COMPLETE — Key Takeaways")
print("=" * 70)
print("""
1. Plugin API (v1.30)
   • Plugin ABC + @hook (auto event-type inference) + @tool (auto-registered)
   • Agent(plugins=[MyPlugin()]) — registers hooks AND tools in one shot
   • Replaces HookProvider for composable, self-contained extensions

2. steer_before_tool() — three actions
   • Proceed(reason)   — tool runs normally
   • Guide(reason)     — cancel + feedback; agent re-reasons (no hard block)
   • Interrupt(reason) — pause for human approval (HITL)

3. steer_after_model() — two actions (v1.30 exclusive)
   • Proceed(reason)  — accept response
   • Guide(reason)    — discard + retry with reason injected into conversation

4. LLMSteeringHandler
   • Natural-language policy in system_prompt — no code rules needed
   • LedgerProvider context: tool history + timing for context-aware decisions
   • Isolated steering LLM — no shared conversation state with main agent

5. vs L22 Safety / vs L28 Hooks
   • Safety (L22)  = hard block — exception, agent stops
   • Hooks  (L28)  = observe/measure — no intervention in flow
   • Steering(L29) = soft redirect — agent re-reasons with new information
""")

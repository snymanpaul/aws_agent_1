"""
L44 Probe 2: correct module names + API shapes.
"""
import inspect
import ag_ui_strands as agui
from ag_ui.core import (
    RunAgentInput, Message, RunStartedEvent, TextMessageStartEvent,
    TextMessageContentEvent, TextMessageEndEvent, ToolCallStartEvent,
    ToolCallArgsEvent, ToolCallEndEvent, RunFinishedEvent,
)

# ── Q1: ag_ui_strands key classes ─────────────────────────────────────────────
print("=== Q1: StrandsAgent signature ===")
print(inspect.signature(agui.StrandsAgent.__init__))

print("\n=== Q2: create_strands_app signature ===")
print(inspect.signature(agui.create_strands_app))

print("\n=== Q3: add_strands_fastapi_endpoint signature ===")
print(inspect.signature(agui.add_strands_fastapi_endpoint))

# ── Q4: RunAgentInput fields ───────────────────────────────────────────────────
print("\n=== Q4: RunAgentInput fields ===")
print(list(RunAgentInput.model_fields.keys()))

# ── Q5: Message fields ────────────────────────────────────────────────────────
print("\n=== Q5: Message type ===")
print(type(Message))
try:
    print(list(Message.model_fields.keys()))
except:
    # May be a discriminated union
    print(f"  type: {Message}")

# ── Q6: StrandsAgentConfig ────────────────────────────────────────────────────
print("\n=== Q6: StrandsAgentConfig ===")
print(inspect.signature(agui.StrandsAgentConfig.__init__))

# ── Q7: ToolBehavior ──────────────────────────────────────────────────────────
print("\n=== Q7: ToolBehavior fields ===")
print(inspect.signature(agui.ToolBehavior.__init__))

# ── Q8: can we instantiate StrandsAgent with a dummy Strands agent? ────────────
print("\n=== Q8: StrandsAgent instantiation test ===")
from strands import Agent
from tools import get_model
import sys
sys.path.insert(0, '.')

fast = get_model("haiku")
strands_agent = Agent(model=fast, tools=[], callback_handler=None)
try:
    wrapped = agui.StrandsAgent(agent=strands_agent)
    print(f"  ✓ StrandsAgent created: {type(wrapped)}")
    print(f"  attributes: {[a for a in dir(wrapped) if not a.startswith('_')][:15]}")
except Exception as e:
    print(f"  ✗ {e}")

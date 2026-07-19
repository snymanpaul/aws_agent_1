"""
Probe: new structured_output API (non-deprecated)
"""
import inspect
from pydantic import BaseModel
from strands import Agent

# 1. Check __call__ signature
print("=== Agent.__call__ signature ===")
sig = inspect.signature(Agent.__call__)
for name, param in sig.parameters.items():
    if name != 'self':
        print(f"  {name}: {param.annotation}")

print()

# 2. Try the invocation-time pattern
from tools import get_model
model = get_model("haiku")

class SimpleOutput(BaseModel):
    answer: str
    confidence: float

agent = Agent(model=model, tools=[], callback_handler=None)
result = agent("What is 2 + 2? Answer with high confidence.", structured_output_model=SimpleOutput)

print("Result type:", type(result))
print("Result:", result)
print()
for attr in ['output', 'structured_output', 'message', 'stop_reason']:
    if hasattr(result, attr):
        val = getattr(result, attr)
        print(f"  result.{attr}: {val!r} ({type(val).__name__})")

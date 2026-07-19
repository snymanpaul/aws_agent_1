"""
Probe: ConcurrentToolExecutor — verify parallel tool dispatch in SDK 1.19.x

Runs two slow tools; concurrent execution should finish in ~0.5s (not ~1s).
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands import Agent, tool
from strands.tools.executors.concurrent import ConcurrentToolExecutor
from tools import get_model

model = get_model("haiku")


@tool
def slow_tool_a(x: int) -> str:
    """Slow tool A — simulates I/O latency."""
    time.sleep(0.5)
    return f"A={x * 2}"


@tool
def slow_tool_b(x: int) -> str:
    """Slow tool B — simulates I/O latency."""
    time.sleep(0.5)
    return f"B={x * 3}"


print("--- Sequential (default ToolExecutor) ---")
agent_seq = Agent(model=model, tools=[slow_tool_a, slow_tool_b], callback_handler=None)
t0 = time.time()
result = agent_seq("Call slow_tool_a(4) AND slow_tool_b(4) simultaneously")
print(result)
print(f"Time: {time.time() - t0:.2f}s\n")

print("--- Concurrent (ConcurrentToolExecutor) ---")
agent_con = Agent(
    model=model,
    tools=[slow_tool_a, slow_tool_b],
    callback_handler=None,
    tool_executor=ConcurrentToolExecutor(),
)
t0 = time.time()
result = agent_con("Call slow_tool_a(4) AND slow_tool_b(4) simultaneously")
print(result)
print(f"Time: {time.time() - t0:.2f}s")

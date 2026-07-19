"""
Probe: Force parallel tool batching — does sonnet-4 batch multiple tool calls
in a SINGLE response turn when instructed?

Strategy: system prompt that explicitly demands single-turn batching.
Measures: wall-clock time with sequential vs concurrent executor.
Success: concurrent run meaningfully faster when tools sleep 1s each.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands import Agent, tool
from strands.tools.executors.concurrent import ConcurrentToolExecutor
from tools import get_model

PARALLEL_SYSTEM_PROMPT = """\
You are a data-fetching assistant. When asked to retrieve multiple pieces of
information, you MUST issue ALL tool calls in a single batched response — never
split them across multiple turns. Always call every required tool simultaneously.
"""

SLEEP = 1.0  # seconds per tool — gap must be obvious


@tool
def get_population(city: str) -> dict:
    """Get the population of a city."""
    time.sleep(SLEEP)
    return {"city": city, "population": 4_618_000}


@tool
def get_gdp(city: str) -> dict:
    """Get the GDP (USD billions) of a city."""
    time.sleep(SLEEP)
    return {"city": city, "gdp_usd_bn": 110}


@tool
def get_timezone(city: str) -> dict:
    """Get the timezone of a city."""
    time.sleep(SLEEP)
    return {"city": city, "tz": "Africa/Johannesburg"}


model = get_model("claude-sonnet-4")
PROMPT = "Get the population, GDP, AND timezone for Johannesburg — all three at once."

print("=== Sequential executor ===")
agent_seq = Agent(
    model=model,
    system_prompt=PARALLEL_SYSTEM_PROMPT,
    tools=[get_population, get_gdp, get_timezone],
    callback_handler=None,
)
t0 = time.time()
result = agent_seq(PROMPT)
t_seq = time.time() - t0
print(result)
print(f"Sequential: {t_seq:.2f}s  (expected ~{SLEEP * 3:.1f}s if serialised)")

print("\n=== Concurrent executor ===")
agent_con = Agent(
    model=model,
    system_prompt=PARALLEL_SYSTEM_PROMPT,
    tools=[get_population, get_gdp, get_timezone],
    callback_handler=None,
    tool_executor=ConcurrentToolExecutor(),
)
t0 = time.time()
result = agent_con(PROMPT)
t_con = time.time() - t0
print(result)
print(f"Concurrent: {t_con:.2f}s  (expected ~{SLEEP:.1f}s if batched)")

ratio = t_seq / t_con if t_con > 0 else 0
print(f"\nSpeedup ratio: {ratio:.1f}x")
if ratio >= 1.8:
    print("PASS — parallel batching confirmed")
else:
    print("FAIL — LLM likely still serialising across turns; fallback needed")

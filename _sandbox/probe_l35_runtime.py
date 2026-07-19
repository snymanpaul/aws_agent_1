"""Probe EventLoopMetrics structure and TopicPlanner.plan_topics_async signature."""
import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands_evals.generators.topic_planner import TopicPlanner
from tools import get_model

print("=== TopicPlanner.plan_topics_async signature ===")
print(inspect.signature(TopicPlanner.plan_topics_async))

print("\n=== Agent result.metrics ===")
model = get_model("claude-sonnet-4")

@tool
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b

agent = Agent(model=model, tools=[add], callback_handler=None)
result = agent("What is 2 + 2?")
print(f"result type: {type(result)}")
print(f"result.metrics type: {type(result.metrics)}")
metrics = result.metrics
print(f"metrics attrs: {[x for x in dir(metrics) if not x.startswith('_')]}")
# Try to get tool usage
if hasattr(metrics, "tool_metrics"):
    print(f"tool_metrics: {metrics.tool_metrics}")
if hasattr(metrics, "__dict__"):
    print(f"metrics.__dict__: {metrics.__dict__}")
print(f"str(metrics): {str(metrics)[:200]}")

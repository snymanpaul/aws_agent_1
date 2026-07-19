"""
Probe: why does HelpfulnessEvaluator fail with output-only task results?
And what Bedrock models can TopicPlanner use?
"""
import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands_evals import Experiment, Case
from strands_evals.evaluators import HelpfulnessEvaluator
from strands_evals.generators.topic_planner import TopicPlanner
from tools import get_model

model = get_model("claude-sonnet-4")

# --- 1. Print _get_last_turn and _format_trace_level_prompt source ---
print("=== HelpfulnessEvaluator._get_last_turn source ===")
src = inspect.getsource(HelpfulnessEvaluator._get_last_turn)
print(src)

print("\n=== HelpfulnessEvaluator._format_trace_level_prompt source ===")
try:
    src2 = inspect.getsource(HelpfulnessEvaluator._format_trace_level_prompt)
    print(src2)
except Exception as e:
    print(f"  {e}")

# --- 2. Check what EvaluationData looks like when run_evaluations calls our task ---
print("\n=== Experiment internals: how EvaluationData is built ===")
src3 = inspect.getsource(Experiment.run_evaluations)
print(src3[:3000])

# --- 3. What model IDs can TopicPlanner use? ---
print("\n=== TopicPlanner full source ===")
src4 = inspect.getsource(TopicPlanner)
print(src4[:3000])

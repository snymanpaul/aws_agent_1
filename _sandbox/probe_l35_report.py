"""Probe the actual structure of EvaluationReport returned by run_evaluations."""
from strands import Agent, tool
from strands_evals import Experiment, Case
from strands_evals.evaluators import Contains, Equals
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import get_model
import json

model = get_model("claude-sonnet-4")

@tool
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b

agent = Agent(model=model, tools=[add], callback_handler=None)

def task(case):
    result = agent(case.input)
    return {"output": str(result)}

cases = [Case(name="c1", input="What is 2 + 2?", expected_output="4")]
experiment = Experiment(
    cases=cases,
    evaluators=[Contains("4"), Equals("4")]
)

reports = experiment.run_evaluations(task)

print(f"type(reports): {type(reports)}")
print(f"len(reports): {len(reports)}")
for i, r in enumerate(reports):
    print(f"\nreport[{i}]:")
    print(f"  type: {type(r).__name__}")
    print(f"  fields: {list(r.model_fields.keys())}")
    print(f"  dict: {json.dumps(r.model_dump(), indent=2, default=str)[:500]}")

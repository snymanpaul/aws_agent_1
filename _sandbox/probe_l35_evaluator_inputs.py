"""
Probe: what inputs do each evaluator type need?
Test with minimal synthetic data — no LLM agent call needed for shape probing.

Questions to answer:
1. ToolCalled — does trajectory need to be a list? What field?
2. HelpfulnessEvaluator — can we pass model=OpenAIModel? What keys in task result?
3. OutputEvaluator(rubric) — does it accept model=OpenAIModel?
4. TrajectoryEvaluator(rubric) — what trajectory format?
5. TopicPlanner — what constructor signature? What model arg?
"""
import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands_evals import Experiment, Case
from strands_evals.evaluators import (
    Contains, ToolCalled, HelpfulnessEvaluator,
    OutputEvaluator, TrajectoryEvaluator,
)
from strands_evals.generators.topic_planner import TopicPlanner
from strands_evals.generators.experiment_generator import ExperimentGenerator
from tools import get_model

model = get_model("claude-sonnet-4")

# --- 1. Inspect evaluator __init__ signatures ---
print("=== Evaluator signatures ===")
for cls in [Contains, ToolCalled, HelpfulnessEvaluator, OutputEvaluator, TrajectoryEvaluator]:
    print(f"  {cls.__name__}: {inspect.signature(cls.__init__)}")

print("\n=== ToolCalled source ===")
import inspect as _i
print(_i.getsource(ToolCalled))

print("\n=== HelpfulnessEvaluator source (first 60 lines) ===")
src = _i.getsource(HelpfulnessEvaluator)
print("\n".join(src.splitlines()[:60]))

print("\n=== OutputEvaluator source (first 60 lines) ===")
src2 = _i.getsource(OutputEvaluator)
print("\n".join(src2.splitlines()[:60]))

print("\n=== TrajectoryEvaluator source (first 60 lines) ===")
src3 = _i.getsource(TrajectoryEvaluator)
print("\n".join(src3.splitlines()[:60]))

# --- 2. TopicPlanner constructor ---
print("\n=== TopicPlanner __init__ signature ===")
print(inspect.signature(TopicPlanner.__init__))
print(_i.getsource(TopicPlanner.__init__))

# --- 3. Experiment.run_evaluations signature ---
print("\n=== Experiment.run_evaluations signature ===")
print(inspect.signature(Experiment.run_evaluations))

# --- 4. Run ToolCalled with synthetic trajectory ---
print("\n=== ToolCalled: test with synthetic trajectory ===")
cases = [Case(name="t1", input="dummy", expected_output="x")]

def task_with_trajectory(case):
    return {"output": "the answer is 120", "trajectory": ["multiply"]}

def task_output_only(case):
    return {"output": "the answer is 120"}

exp_tc = Experiment(cases=cases, evaluators=[ToolCalled("multiply")])
print("Running ToolCalled with trajectory key...")
try:
    reports = exp_tc.run_evaluations(task_with_trajectory)
    r = reports[0]
    print(f"  EvaluationReport fields: {list(r.model_fields.keys())}")
    print(f"  scores: {r.scores}, test_passes: {r.test_passes}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\nRunning ToolCalled without trajectory key...")
try:
    exp_tc2 = Experiment(cases=cases, evaluators=[ToolCalled("multiply")])
    reports2 = exp_tc2.run_evaluations(task_output_only)
    r2 = reports2[0]
    print(f"  scores: {r2.scores}, test_passes: {r2.test_passes}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 5. OutputEvaluator with model=OpenAIModel ---
print("\n=== OutputEvaluator: model param ===")
try:
    ev = OutputEvaluator(rubric="Pass if answer contains 120.", model=model)
    print(f"  OutputEvaluator(model=OpenAIModel) constructed OK: {type(ev)}")
    exp_oe = Experiment(cases=cases, evaluators=[ev])
    r_oe = exp_oe.run_evaluations(task_output_only)[0]
    print(f"  scores: {r_oe.scores}, test_passes: {r_oe.test_passes}")
except Exception as e:
    print(f"  ERROR with OpenAIModel: {e}")

print("\n=== OutputEvaluator: no model (Bedrock default) ===")
try:
    ev2 = OutputEvaluator(rubric="Pass if answer contains 120.")
    print(f"  OutputEvaluator() constructed OK")
    # Don't run — would need Bedrock creds
    print("  (skipping run — needs Bedrock)")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 6. HelpfulnessEvaluator with model=OpenAIModel ---
print("\n=== HelpfulnessEvaluator: model=OpenAIModel ===")
try:
    ev_h = HelpfulnessEvaluator(model=model)
    print(f"  constructed OK: {type(ev_h)}")
    exp_h = Experiment(cases=cases, evaluators=[ev_h])
    r_h = exp_h.run_evaluations(task_output_only)[0]
    print(f"  scores: {r_h.scores}, test_passes: {r_h.test_passes}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\nDone.")

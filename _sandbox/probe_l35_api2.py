"""Probe strands_evals generators, Case, and run_evaluations."""
import inspect
from strands_evals import Case, Experiment
from strands_evals.generators.topic_planner import TopicPlanner
from strands_evals.generators.experiment_generator import ExperimentGenerator

print("=== Case ===")
print(inspect.signature(Case.__init__))
print("fields:", [f for f in dir(Case) if not f.startswith("_")])

print("\n=== TopicPlanner ===")
print(inspect.signature(TopicPlanner.__init__))
print("methods:", [m for m in dir(TopicPlanner) if not m.startswith("_") and callable(getattr(TopicPlanner, m))])

print("\n=== ExperimentGenerator ===")
print(inspect.signature(ExperimentGenerator.__init__))
print("methods:", [m for m in dir(ExperimentGenerator) if not m.startswith("_") and callable(getattr(ExperimentGenerator, m))])

print("\n=== Experiment.run_evaluations ===")
print(inspect.signature(Experiment.run_evaluations))

print("\n=== ActorSimulator ===")
from strands_evals import ActorSimulator, UserSimulator
print("ActorSimulator:", inspect.signature(ActorSimulator.__init__))
print("UserSimulator:", inspect.signature(UserSimulator.__init__))

print("\n=== EvaluationReport / types ===")
from strands_evals.types.evaluation_report import EvaluationReport
print("EvaluationReport:", [f for f in dir(EvaluationReport) if not f.startswith("_")])
from strands_evals.types.evaluation import EvaluationResult
print("EvaluationResult:", [f for f in dir(EvaluationResult) if not f.startswith("_")])

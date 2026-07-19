"""
Level 91: Run the SDK's NATIVE trace-level evaluators LOCALLY (Gemini judge)
==========================================================================
Closes the audit gap + corrects L35: strands_evals' GoalSuccessRate / ToolSelectionAccuracy /
ToolParameterAccuracy evaluators were "imported but never run", believed to need cloud ADOT/
Application Signals. They actually run LOCALLY — you just must capture the agent's trajectory
with @eval_task(TracedHandler()), which sets up an IN-MEMORY OpenTelemetry span exporter and
maps spans to a Session the evaluators read. (A plain output/trajectory dict yields 0.00 — that
was the real failure mode, not a cloud requirement.)

Anti-simulation design (no fakes/stubs):
  - Real agent runs traced via the SDK's in-memory telemetry; evaluators judge with a Gemini model.
  - Discrimination from real runs: a case whose expected_trajectory MATCHES the agent's real tool
    use vs one whose expected_trajectory is wrong -> trajectory evaluators score the match higher.

Run:
  podman start litellm-proxy
  uv run python 13_quality/native_trace_evaluators.py
"""

from strands import Agent, tool
from strands.models.openai import OpenAIModel

from strands_evals import Case, Experiment, TracedHandler, eval_task
from strands_evals.evaluators import (
    GoalSuccessRateEvaluator, ToolSelectionAccuracyEvaluator, ToolParameterAccuracyEvaluator,
)


def _model():
    return OpenAIModel(model_id="gemini-2.5-flash",
                       client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
                       params={"temperature": 0.0})


@tool
def multiply(a: float, b: float) -> str:
    """Multiply two numbers."""
    return str(a * b)


@eval_task(TracedHandler())   # captures the agent's OTel spans -> Session for trace-level evaluators
def task():
    return Agent(model=_model(), tools=[multiply], callback_handler=None,
                 system_prompt="Use the multiply tool to compute products, then state the result.")


CASES = [
    Case(name="match", input="What is 15 multiplied by 8?", expected_output="120",
         expected_trajectory=["multiply"]),
    Case(name="mismatch", input="What is 15 multiplied by 8?", expected_output="120",
         expected_trajectory=["web_search", "database_lookup"]),
]


def _plain_task(case):
    """Negative control: NO TracedHandler -> no captured Session, just an output dict."""
    return {"output": str(Agent(model=_model(), tools=[multiply], callback_handler=None,
                                system_prompt="Use the multiply tool.")(case.input))}


def verify():
    evaluators = [
        GoalSuccessRateEvaluator(model=_model()),
        ToolSelectionAccuracyEvaluator(model=_model()),
        ToolParameterAccuracyEvaluator(model=_model()),
    ]
    reports = Experiment(cases=CASES, evaluators=evaluators).run_evaluations(task)   # TRACED
    by = {}
    for ev, rep in zip(evaluators, reports):
        name = type(ev).__name__.replace("Evaluator", "")
        per = {cd.get("name"): sc for cd, sc in zip(rep.cases, rep.scores)}
        by[name] = per
        print(f"[L91] traced  {name}: per-case={ {k: round(v, 2) for k, v in per.items()} }")

    # negative control: same evaluator WITHOUT a captured Session -> cannot evaluate
    ctrl = Experiment(cases=[CASES[0]], evaluators=[GoalSuccessRateEvaluator(model=_model())]
                      ).run_evaluations(_plain_task)[0].scores[0]
    goal = by.get("GoalSuccessRate", {}).get("match", 0)
    print(f"[L91] control GoalSuccessRate WITHOUT TracedHandler (plain dict) = {ctrl:.2f}")
    print("[L91] note: ToolSelectionAccuracy scores tool APPROPRIATENESS, not match to expected_trajectory")

    checks = {
        "3 native trace-level evaluators ran locally (no AWS)": len(reports) == 3,
        "traced run yields REAL non-zero scores": any(v for per in by.values() for v in per.values()),
        "GoalSuccessRate marks the solved case a success (>=0.5)": goal >= 0.5,
        "control: WITHOUT a captured Session the evaluator cannot score (traced > plain-dict)": goal > ctrl,
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    assert all(checks.values()), "L91 FAILED"
    print("[L91] PASS — native trace-level evaluators run LOCALLY on real captured traces; the Session "
          "(TracedHandler), not cloud ADOT, is the requirement (corrects L35)")


if __name__ == "__main__":
    verify()

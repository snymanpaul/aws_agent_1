"""
Level 35: Strands Evals SDK — Local Structured Evaluation
==========================================================
Run structured, reproducible evaluation experiments locally — no cloud
infrastructure needed. Complement to L34's cloud-side online sampling.

Goal: understand the full local eval lifecycle:
  - Case: unit of evaluation (input + expected output/trajectory)
  - Experiment: collection of Cases + Evaluators
  - Evaluators: LLM-as-judge, deterministic, custom rubric
  - Generators: AI-powered test case generation (TopicPlanner + ExperimentGenerator)
  - Persistence: to_file / from_file for CI artefacts and regression baselines

Package: strands-agents-evals  (pip install strands-agents-evals)
  NOT part of strands-agents extras — separate package.

L34 vs L35:
    L34 = cloud, continuous, samples live production traffic (ADOT required)
    L35 = local, structured, explicit test cases (no infra required)

Evaluator taxonomy:
    LLM-judge  : Helpfulness, Faithfulness, Coherence, Conciseness,
                 ResponseRelevance, GoalSuccessRate, Harmfulness
    Custom     : OutputEvaluator(rubric), TrajectoryEvaluator(rubric),
                 InteractionsEvaluator(rubric)
    Deterministic: Contains, Equals, StartsWith, ToolCalled

Task function rules (CRITICAL):
    run_agent(case)                 → {"output": str}
        Use for: LLM-judge evaluators (Helpfulness, OutputEvaluator)
        Why: LLM evaluators parse actual_trajectory as Session; a plain
             list trajectory raises "Trace parsing requires Session" error.

    run_agent_with_trajectory(case) → {"output": str, "trajectory": list[str]}
        Use for: ToolCalled, TrajectoryEvaluator
        Why: deterministic and trajectory-based evaluators read the
             "trajectory" key as a list of tool names called.

Usage:
    AWS_PROFILE=<your-sso-profile> uv run python 11_platform/evals_sdk.py
"""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# TopicPlanner uses BedrockModel internally — needs AWS credentials
# Set AWS_PROFILE (your SSO profile) in the environment before running.
from strands import Agent, tool
from strands_evals import Experiment, Case
from strands_evals.evaluators import (
    OutputEvaluator,
    Contains,
    Equals,
    ToolCalled,
    TrajectoryEvaluator,
    ToolSelectionAccuracyEvaluator,
)
from strands_evals.generators.topic_planner import TopicPlanner
from strands_evals.generators.experiment_generator import ExperimentGenerator
from tools import get_model

model = get_model("claude-sonnet-4")


# ---------------------------------------------------------------------------
# Agent under test: a simple math + unit-conversion agent
# ---------------------------------------------------------------------------

@tool
def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b

@tool
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b

@tool
def convert_celsius_to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return celsius * 9 / 5 + 32

AGENT_SYSTEM_PROMPT = (
    "You are a precise math and unit-conversion assistant. "
    "Always use the provided tools for calculations — never compute mentally. "
    "Return only the final answer, no explanation needed."
)


def make_agent() -> Agent:
    """Create a fresh Agent per call — metrics do NOT persist across instances."""
    return Agent(
        model=model,
        tools=[multiply, add, convert_celsius_to_fahrenheit],
        system_prompt=AGENT_SYSTEM_PROMPT,
        callback_handler=None,
    )


def run_agent(case: Case) -> dict:
    """Output only — use for LLM-judge evaluators (Helpfulness, OutputEvaluator).

    Do NOT use for ToolCalled/TrajectoryEvaluator — they need trajectory.
    Do NOT return a 'trajectory' key here — LLM evaluators parse actual_trajectory
    as a Session object; a plain list raises 'Trace parsing requires Session'.
    """
    result = make_agent()(case.input)
    return {"output": str(result)}


def run_agent_with_trajectory(case: Case) -> dict:
    """Output + tool trajectory — use for ToolCalled / TrajectoryEvaluator.

    tool_metrics is a dict keyed by tool name; keys give the call order.
    """
    result = make_agent()(case.input)
    trajectory = list(result.metrics.tool_metrics.keys())
    return {"output": str(result), "trajectory": trajectory}


# ---------------------------------------------------------------------------
# ITERATION 1: Manual Cases + deterministic evaluators
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 1: Manual Cases + deterministic evaluators")
print("=" * 70)
print("""
Case = unit of evaluation: input + optional expected_output/trajectory.
Deterministic evaluators are cheap and fast:
  Contains(value)      — output contains a string (case-sensitive by default)
  Equals(value)        — exact match
  StartsWith(value)    — output starts with string
  ToolCalled(name)     — tool appeared in trajectory

ToolCalled needs trajectory → use run_agent_with_trajectory.
Contains works with or without trajectory key.

HelpfulnessEvaluator is NOT for local eval — it is TRACE_LEVEL and requires
actual_trajectory to be a Session (OTel/ADOT from L34 cloud instrumentation).
For local LLM judging, use OutputEvaluator(rubric, model=model) — see Iteration 2.
""")

cases_iter1 = [
    Case(name="multiply_15_8",  input="What is 15 multiplied by 8?",  expected_output="120"),
    Case(name="add_37_45",      input="What is 37 plus 45?",           expected_output="82"),
    Case(name="celsius_100",    input="Convert 100°C to Fahrenheit.",  expected_output="212"),
]

# NOTE: HelpfulnessEvaluator is a TRACE_LEVEL evaluator — it requires actual_trajectory
# to be a Session object with AgentInvocationSpan (OTel/ADOT traces from L34-style cloud
# instrumentation). It cannot be used with a plain {"output": str} task result.
# For local LLM judging, use OutputEvaluator(rubric, model=model) instead (Iteration 2).

print("--- Contains + ToolCalled  (run_agent_with_trajectory) ---")
experiment1 = Experiment(
    cases=cases_iter1,
    evaluators=[
        Contains("120", case_sensitive=False),   # loose match — only case 1 passes
        ToolCalled("multiply"),                   # only case 1 used multiply
    ],
)
reports1 = experiment1.run_evaluations(run_agent_with_trajectory)

for evaluator, report in zip(experiment1.evaluators, reports1):
    ev_name = type(evaluator).__name__
    print(f"\n  Evaluator: {ev_name}  overall_score={report.overall_score:.2f}")
    for case_data, score, passed, reason in zip(
        report.cases, report.scores, report.test_passes,
        report.reasons + [""] * len(report.cases)
    ):
        status = "PASS" if passed else "FAIL"
        name = case_data.get("name", "?")
        print(f"    [{status}] {name}  score={score:.2f}  {str(reason)[:70]}")


# ---------------------------------------------------------------------------
# ITERATION 2: Custom rubric evaluators (OutputEvaluator + TrajectoryEvaluator)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 2: Custom rubric evaluators")
print("=" * 70)
print("""
OutputEvaluator(rubric, model=model) — LLM judges the output against a custom rubric.
TrajectoryEvaluator(rubric, model=model) — LLM judges the tool call sequence.
Both accept free-text rubrics; the LLM produces {test_pass, score, reason}.

model=model (OpenAIModel) bypasses Bedrock default — works with LiteLLM proxy.

Use OutputEvaluator when:
  - The expected output has multiple valid forms (rounding, formatting)
  - Partial credit matters (score 0.0-1.0, not just pass/fail)

Use TrajectoryEvaluator when:
  - You care which tools were called and in what order
  - You want to catch unnecessary tool use or wrong-tool choices

Both need run_agent_with_trajectory so TrajectoryEvaluator has a trajectory.
OutputEvaluator ignores the trajectory key (uses output only).
""")

cases_iter2 = [
    Case(
        name="multi_step",
        input="Multiply 12 by 7, then add 15 to the result.",
        expected_output="99",
        expected_trajectory=["multiply", "add"],
    ),
    Case(
        name="temp_conversion",
        input="What is 37°C in Fahrenheit? (body temperature)",
        expected_output="98.6",
    ),
]

experiment2 = Experiment(
    cases=cases_iter2,
    evaluators=[
        OutputEvaluator(
            rubric=(
                "Pass if the final numeric answer is correct within ±0.5. "
                "Score 1.0 for exact, 0.5 for close but not exact, 0.0 for wrong."
            ),
            model=model,   # OpenAIModel — bypasses Bedrock default
        ),
        TrajectoryEvaluator(
            rubric=(
                "Pass if the agent used exactly the tools needed — no extras. "
                "Score 1.0 for perfect tool sequence, 0.5 for correct tools in wrong order, "
                "0.0 for wrong tools or unnecessary calls."
            ),
            model=model,   # OpenAIModel — bypasses Bedrock default
        ),
    ],
)

print("--- running 2 cases ---")
reports2 = experiment2.run_evaluations(run_agent_with_trajectory)

for evaluator, report in zip(experiment2.evaluators, reports2):
    ev_name = type(evaluator).__name__
    print(f"\n  Evaluator: {ev_name}  overall_score={report.overall_score:.2f}")
    for case_data, score, passed, reason in zip(
        report.cases, report.scores, report.test_passes,
        report.reasons + [""] * len(report.cases)
    ):
        status = "PASS" if passed else "FAIL"
        reason_str = str(reason).strip().replace("\n", " ")
        print(f"    [{status}] {case_data.get('name')}  score={score:.2f}  {reason_str[:90]}")


# ---------------------------------------------------------------------------
# ITERATION 3: Persistence — to_file / from_file
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 3: Persistence — to_file / from_file for CI baselines")
print("=" * 70)
print("""
Experiment.to_file(path) serialises the entire experiment (cases +
evaluators + results) to JSON. from_file(path) reloads it.

CI workflow:
  1. Run experiment on PR → compare scores vs baseline
  2. If avg score drops > threshold → fail the PR check
  3. Baseline file checked into the repo as a regression artefact

EvaluationReport.to_file / from_file works the same way for per-case results.
""")

with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
    baseline_path = f.name

print(f"--- save experiment to {baseline_path} ---")
experiment2.to_file(baseline_path)

print("--- reload and verify ---")
reloaded = Experiment.from_file(baseline_path)
print(f"  cases reloaded:     {len(reloaded.cases)}")
print(f"  evaluators reloaded: {len(reloaded.evaluators)}")

# Compare avg scores
def avg_score(reports):
    scores = [s for r in reports for s in r.scores if s is not None]
    return sum(scores) / len(scores) if scores else 0.0

orig_avg  = avg_score(reports2)
print(f"  original avg score:  {orig_avg:.3f}")
print(f"  (reloaded experiment ready for run_evaluations on new agent version)")

os.unlink(baseline_path)


# ---------------------------------------------------------------------------
# ITERATION 4: AI-powered test case generation (TopicPlanner)
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 4: AI-powered test case generation — TopicPlanner")
print("=" * 70)
print("""
TopicPlanner.plan_topics_async(context, task_description, num_topics, num_cases)
uses a Bedrock LLM to generate a topic distribution for a task.
Then ExperimentGenerator creates Cases from scratch based on those topics.

TopicPlanner.__init__(model: str | None) accepts a Bedrock model ID string
(NOT an OpenAIModel instance). Pass None to use the default Bedrock model.
Requires AWS credentials (AWS_PROFILE or env vars).

4-phase AI eval SOP:
  1. Plan     → TopicPlanner generates topic distribution
  2. Generate → ExperimentGenerator creates cases
               (30% easy / 50% medium / 20% hard by default)
  3. Execute  → run_evaluations(task_fn)
  4. Report   → scores + reasons per case

This iteration demonstrates Phase 1 (plan) — topic planning is fast.
Full generation (Phase 2) uses multiple LLM calls and is slower;
showing the shape here without running all cases.
""")

import asyncio

TASK_DESCRIPTION = (
    "A math assistant that multiplies, adds numbers, and converts "
    "Celsius to Fahrenheit using dedicated tools."
)

print("--- TopicPlanner.plan_topics_async ---")
# TopicPlanner accepts model: str | None (Bedrock model ID).
# model=None defaults to us.anthropic.claude-sonnet-4-... which is blocked on channel
# program accounts. Use amazon.nova-micro-v1:0 — fast, cheap, accessible.
planner = TopicPlanner(model="amazon.nova-micro-v1:0")
topics = asyncio.run(planner.plan_topics_async(
    context="",
    task_description=TASK_DESCRIPTION,
    num_topics=4,
    num_cases=6,
))
print(f"  generated {len(topics.topics)} topics:")
for t in topics.topics:
    print(f"    - {t}")

print("""
  ExperimentGenerator.from_scratch_async(task_description, num_cases, ...)
  would then generate Case objects from these topics. Skipping execution
  here to avoid ~10 LLM calls, but the pattern is:

    generator = ExperimentGenerator(input_type=str, output_type=str)
    experiment = asyncio.run(generator.from_scratch_async(
        task_description=TASK_DESCRIPTION,
        num_cases=6,
    ))
    reports = experiment.run_evaluations(run_agent)
""")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("L35 COMPLETE — Key Takeaways")
print("=" * 70)
print("""
1. Package
   • pip install strands-agents-evals  (NOT part of strands-agents extras)
   • from strands_evals import Experiment, Case
   • from strands_evals.evaluators import HelpfulnessEvaluator, Contains, ...
   • from strands_evals.generators.topic_planner import TopicPlanner

2. Case
   • Case(name, input, expected_output=None, expected_trajectory=None)
   • Pydantic model — serialize to/from dict/JSON

3. Experiment
   • Experiment(cases=[...], evaluators=[...])
   • run_evaluations(task_fn)  where task_fn(Case) → dict {output, trajectory}
   • Returns list[EvaluationReport] — one per EVALUATOR (not per case)
   • to_file(path) / from_file(path) for CI baselines

4. Task function split (CRITICAL)
   run_agent → {"output": str}
     Use for: OutputEvaluator (LLM judge) — output-only evaluators
     Why: TRACE_LEVEL evaluators (HelpfulnessEvaluator) require actual_trajectory
          to be a Session object (OTel/ADOT); they cannot be used locally

   run_agent_with_trajectory → {"output": str, "trajectory": list[str]}
     Use for: ToolCalled, TrajectoryEvaluator (trajectory-aware evaluators)
     tool_metrics is a dict keyed by tool name — keys() gives call order

5. Evaluator taxonomy
   TRACE_LEVEL (needs OTel Session — L34/ADOT only):
                  HelpfulnessEvaluator, FaithfulnessEvaluator, GoalSuccessRate,
                  CoherenceEvaluator, ConcisenessEvaluator, ResponseRelevance
   Custom rubric (local, works with {"output": str}):
                  OutputEvaluator(rubric, model=model), TrajectoryEvaluator(rubric, model=model),
                  InteractionsEvaluator(rubric)
   Deterministic: Contains(value), Equals(value), StartsWith(value),
                  ToolCalled(tool_name)   — fast, no LLM needed
   Tool accuracy: ToolSelectionAccuracyEvaluator, ToolParameterAccuracyEvaluator

6. model= parameter
   • OutputEvaluator/TrajectoryEvaluator: accept model=OpenAIModel (bypasses Bedrock)
   • TopicPlanner(model: str | None): Bedrock model ID string only (NOT OpenAIModel)
     Use "amazon.nova-micro-v1:0" — Anthropic models blocked on channel accounts
   • Without model=, evaluators default to BedrockModel (needs AWS creds)

7. AI-powered generation (4-phase SOP)
   Phase 1: TopicPlanner.plan_topics_async(context, task, num_topics, num_cases)
   Phase 2: ExperimentGenerator.from_scratch_async(task, num_cases)
            → auto-generates inputs, expected outputs, rubrics
            → 30% easy / 50% medium / 20% hard
   Phase 3: experiment.run_evaluations(task_fn)
   Phase 4: inspect EvaluationReport.evaluation_results for scores

8. EvaluationReport
   • Per-evaluator report with parallel arrays: cases / scores / test_passes / reasons
   • report.overall_score — mean across all cases
   • EvaluationReport.to_file() / from_file()
   • report.display() — rich-formatted table output

9. L34 vs L35
   • L34 = cloud, production sampling, ADOT required, continuous
   • L35 = local, explicit test cases, no infra, deterministic
   • Stack: L35 in CI (every PR), L34 in production (every request)
""")

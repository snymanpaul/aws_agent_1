"""Tests for tools/eval_harness.py, the harness every eval claim in this repo rests on.

The harness decides what counts as a passing run: quality thresholds, cost ceilings, and
whether a drop against a baseline is significant. Until now none of that was tested, so
"gate passed" was an unverified claim about the thing that verifies everything else.

No model, no network, no credentials. `run_suite` already takes an injectable `run_fn`,
so a scripted local function exercises the whole path. `perm_test` seeds its own
`random.Random(13)`, so p-values here are deterministic rather than flaky.

    uv run pytest tests/test_eval_harness.py -q
"""

import importlib.util
import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HARNESS_PATH = REPO_ROOT / "tools" / "eval_harness.py"


def _load_harness():
    """Import by path, bypassing tools/__init__.py, which pulls in strands."""
    spec = importlib.util.spec_from_file_location("_eval_harness_uut", HARNESS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


eh = _load_harness()

CORRECT = lambda out, case: 1.0 if case.expected in out else 0.0


def scripted(mapping, tokens=10):
    """A run_fn that returns a recorded answer per input, with fixed token counts."""
    def run(inp):
        return mapping[inp], tokens
    return run


def result_with(scores, tokens=None):
    """Build a result dict directly, for testing the pure decision functions."""
    return {
        "scores": {"correct": list(scores)},
        "tokens": list(tokens) if tokens is not None else [],
        "latency": [],
        "n": 1,
        "cases": len(scores),
    }


# ---------------------------------------------------------------------------
# run_suite
# ---------------------------------------------------------------------------


def test_run_suite_calls_run_fn_once_per_case_per_repetition():
    cases = [eh.Case("a", "x"), eh.Case("b", "y")]
    calls = []

    def counting(inp):
        calls.append(inp)
        return "x", 5

    result = eh.run_suite(cases, counting, {"correct": CORRECT}, n=3)

    assert len(calls) == 6
    assert calls.count("a") == 3 and calls.count("b") == 3
    assert result["n"] == 3
    assert result["cases"] == 2
    assert len(result["scores"]["correct"]) == 6
    assert len(result["tokens"]) == 6
    assert len(result["latency"]) == 6


def test_run_suite_scores_each_case_against_its_own_expectation():
    cases = [eh.Case("a", "apple"), eh.Case("b", "banana")]
    run = scripted({"a": "apple pie", "b": "not the fruit"})

    result = eh.run_suite(cases, run, {"correct": CORRECT}, n=1)

    assert result["scores"]["correct"] == [1.0, 0.0]


def test_run_suite_supports_multiple_evaluators():
    cases = [eh.Case("a", "apple")]
    run = scripted({"a": "apple"})
    evaluators = {"correct": CORRECT, "short": lambda out, c: 1.0 if len(out) < 10 else 0.0}

    result = eh.run_suite(cases, run, evaluators, n=2)

    assert result["scores"]["correct"] == [1.0, 1.0]
    assert result["scores"]["short"] == [1.0, 1.0]


def test_run_suite_treats_missing_token_count_as_zero():
    """A run_fn that cannot report usage must not crash the suite or inflate cost."""
    result = eh.run_suite([eh.Case("a", "a")], lambda inp: ("a", None), {"correct": CORRECT}, n=1)
    assert result["tokens"] == [0]


# ---------------------------------------------------------------------------
# wilson
# ---------------------------------------------------------------------------


def test_wilson_on_empty_input_returns_zero_interval():
    assert eh.wilson([]) == (0.0, 0.0)


def test_wilson_known_value_for_four_successes():
    """Pins the arithmetic so a silent change to the formula fails here."""
    assert eh.wilson([1.0, 1.0, 1.0, 1.0]) == (0.51, 1.0)


def test_wilson_interval_narrows_as_evidence_grows():
    """The property that makes the interval worth reporting at all."""
    small_lo, small_hi = eh.wilson([1.0] * 4)
    large_lo, large_hi = eh.wilson([1.0] * 100)
    assert (large_hi - large_lo) < (small_hi - small_lo)
    assert large_lo > small_lo


def test_wilson_counts_half_and_above_as_success():
    """The success threshold is >= 0.5, so partial credit below it does not count."""
    assert eh.wilson([0.5, 0.5, 0.5, 0.5]) == eh.wilson([1.0, 1.0, 1.0, 1.0])
    assert eh.wilson([0.49, 0.49, 0.49, 0.49]) == eh.wilson([0.0, 0.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# perm_test
# ---------------------------------------------------------------------------


def test_perm_test_is_deterministic_across_calls():
    a, b = [1.0] * 8, [0.0] * 8
    assert eh.perm_test(a, b) == eh.perm_test(a, b)


def test_perm_test_reports_separated_distributions_as_significant():
    p = eh.perm_test([1.0] * 10, [0.0] * 10)
    assert p < 0.05


def test_perm_test_reports_identical_distributions_as_not_significant():
    p = eh.perm_test([1.0, 0.0] * 6, [1.0, 0.0] * 6)
    assert p > 0.05


def test_perm_test_p_value_stays_in_range():
    p = eh.perm_test([1.0, 0.0, 1.0], [0.0, 1.0, 0.0])
    assert 0.0 < p <= 1.0


# ---------------------------------------------------------------------------
# quality and gate
# ---------------------------------------------------------------------------


def test_quality_is_the_mean_of_the_named_metric():
    assert eh.quality(result_with([1.0, 0.0, 1.0, 1.0]), "correct") == 0.75


def test_gate_passes_when_no_criteria_are_given():
    passed, reasons = eh.gate(result_with([0.0, 0.0]), metric="correct")
    assert passed is True
    assert reasons == []


def test_gate_fails_below_the_quality_floor():
    passed, reasons = eh.gate(result_with([0.0, 0.0, 1.0, 0.0]), min_quality=0.8, metric="correct")
    assert passed is False
    assert any("quality" in r for r in reasons)


def test_gate_passes_at_the_quality_floor():
    """The comparison is strictly less than, so exactly meeting the floor passes."""
    passed, _ = eh.gate(result_with([1.0, 1.0, 1.0, 0.0]), min_quality=0.75, metric="correct")
    assert passed is True


def test_gate_fails_above_the_cost_ceiling():
    passed, reasons = eh.gate(
        result_with([1.0, 1.0], tokens=[500, 700]), max_mean_tokens=100, metric="correct"
    )
    assert passed is False
    assert any("tokens" in r for r in reasons)


def test_gate_reports_every_failed_criterion_not_just_the_first():
    passed, reasons = eh.gate(
        result_with([0.0, 0.0], tokens=[900, 900]),
        min_quality=0.9,
        max_mean_tokens=100,
        metric="correct",
    )
    assert passed is False
    assert len(reasons) == 2


def test_gate_fails_on_a_significant_regression_against_baseline():
    baseline = result_with([1.0] * 10)
    candidate = result_with([0.0] * 10)
    passed, reasons = eh.gate(candidate, baseline=baseline, metric="correct")
    assert passed is False
    assert any("regression" in r for r in reasons)


def test_gate_tolerates_a_drop_that_is_not_significant():
    """A single unlucky run must not be reported as a regression."""
    baseline = result_with([1.0, 1.0, 1.0, 1.0])
    candidate = result_with([1.0, 1.0, 1.0, 0.0])
    passed, reasons = eh.gate(candidate, baseline=baseline, metric="correct")
    assert passed is True
    assert reasons == []


def test_gate_does_not_penalise_beating_the_baseline():
    baseline = result_with([0.0] * 10)
    candidate = result_with([1.0] * 10)
    passed, _ = eh.gate(candidate, baseline=baseline, metric="correct")
    assert passed is True


def test_gate_handles_a_result_with_no_token_data():
    passed, _ = eh.gate(result_with([1.0, 1.0]), max_mean_tokens=10, metric="correct")
    assert passed is True


# ---------------------------------------------------------------------------
# baseline persistence
# ---------------------------------------------------------------------------


def test_baseline_survives_a_save_and_load_round_trip(tmp_path):
    original = result_with([1.0, 0.0, 1.0], tokens=[10, 20, 30])
    path = tmp_path / "baseline.json"

    eh.save_baseline(str(path), original)
    restored = eh.load_baseline(str(path))

    assert restored == original
    assert json.loads(path.read_text()) == original


def test_load_baseline_returns_none_when_absent(tmp_path):
    """First run has no baseline, and that is not an error."""
    assert eh.load_baseline(str(tmp_path / "does_not_exist.json")) is None


def test_a_restored_baseline_still_drives_the_gate(tmp_path):
    """The round trip has to preserve enough to make the same decision."""
    path = tmp_path / "baseline.json"
    eh.save_baseline(str(path), result_with([1.0] * 10))
    restored = eh.load_baseline(str(path))

    passed, reasons = eh.gate(result_with([0.0] * 10), baseline=restored, metric="correct")
    assert passed is False
    assert any("regression" in r for r in reasons)

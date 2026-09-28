"""Tests for eval_harness, the harness every eval claim in this repo rests on.

The harness decides what counts as a passing run: quality thresholds, cost ceilings, and
whether a drop against a baseline is significant. Until now none of that was tested, so
"gate passed" was an unverified claim about the thing that verifies everything else.

No model, no network, no credentials. `run_suite` already takes an injectable `run_fn`,
so a scripted local function exercises the whole path. `perm_test` seeds its own
`random.Random(13)`, so p-values here are deterministic rather than flaky.

    uv run pytest tests/test_eval_harness.py -q
"""

import json

import pytest

from agent_build_gates import eval_harness as eh

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
    """A single unlucky case must not be reported as a regression. 8 cases, so the
    comparison has the power to detect one and the pass is a real non-detection."""
    baseline = result_with([1.0] * 8)
    candidate = result_with([1.0] * 7 + [0.0])
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


# ---------------------------------------------------------------------------
# case-level statistics (0.2.0: the case, not the run, is the unit of evidence)
# ---------------------------------------------------------------------------


def runs(per_case, n):
    """A result with n identical runs per case, as run_suite lays them out (case-major)."""
    flat = [s for s in per_case for _ in range(n)]
    return {"scores": {"correct": flat}, "tokens": [], "latency": [], "n": n, "cases": len(per_case)}


def test_case_means_averages_each_case_over_its_runs():
    result = {"scores": {"correct": [1.0, 0.0, 1.0, 0.0, 0.0, 0.0]}, "n": 3, "cases": 2}
    assert eh.case_means(result, "correct") == [2 / 3, 0.0]


def test_quality_is_unchanged_by_repeating_runs():
    assert eh.quality(runs([1.0, 0.0, 1.0], n=1), "correct") == eh.quality(runs([1.0, 0.0, 1.0], n=7), "correct")


def test_sign_flip_exact_p_for_six_cases_all_one_direction():
    """2 of the 64 sign patterns are as extreme: p = 2 / 64."""
    assert eh.sign_flip_test([0.0] * 6, [1.0] * 6) == 2 / 64


def test_sign_flip_identical_arms_are_not_significant():
    """Negative control: no differing case, no evidence."""
    assert eh.sign_flip_test([1.0, 0.0, 1.0], [1.0, 0.0, 1.0]) == 1.0


def test_sign_flip_matches_its_floor_when_every_case_moves_one_way():
    for k in range(1, 10):
        assert eh.sign_flip_test([0.0] * k, [1.0] * k) == eh.min_p(k)


def test_sign_flip_large_suite_uses_a_deterministic_estimate():
    """Above EXACT_MAX differing cases the test samples sign patterns with a fixed seed."""
    a, b = [0.0] * 20, [1.0] * 20
    p = eh.sign_flip_test(a, b)
    assert p == eh.sign_flip_test(a, b)
    assert p < 0.001


def test_repeats_do_not_manufacture_significance():
    """R1: 3 cases x 4 runs is 3 samples, not 12. The old flat unpaired test called this
    significant; at case level no 3-case comparison can reach p < 0.05."""
    baseline, candidate = runs([1.0] * 3, n=4), runs([0.0] * 3, n=4)
    assert eh.perm_test(candidate["scores"]["correct"], baseline["scores"]["correct"]) < 0.05  # the old flaw
    passed, reasons = eh.gate(candidate, baseline=baseline, metric="correct")
    assert passed is False
    assert not any("significant" in r for r in reasons)
    assert any("undetectable" in r for r in reasons)


def test_gate_fails_closed_when_too_few_cases_to_detect_a_regression():
    """R3: with 5 cases the best achievable p is 0.0625, so even an unchanged candidate
    cannot be cleared against the baseline."""
    passed, reasons = eh.gate(runs([1.0] * 5, n=3), baseline=runs([1.0] * 5, n=3), metric="correct")
    assert passed is False
    assert any("undetectable" in r for r in reasons)


def test_six_cases_is_enough_to_clear_an_unchanged_candidate():
    passed, reasons = eh.gate(runs([1.0] * 6, n=3), baseline=runs([1.0] * 6, n=3), metric="correct")
    assert passed is True
    assert reasons == []


def test_six_cases_is_enough_to_detect_a_full_regression():
    """Positive control for the power gate: the smallest suite that can detect one does."""
    passed, reasons = eh.gate(runs([0.0] * 6, n=3), baseline=runs([1.0] * 6, n=3), metric="correct")
    assert passed is False
    assert any("significant" in r for r in reasons)


def test_power_counts_only_cases_the_baseline_scored_on():
    """10 cases, but the baseline scores on only 3: a drop can show on at most 3."""
    baseline = runs([1.0] * 3 + [0.0] * 7, n=2)
    passed, reasons = eh.gate(runs([0.0] * 10, n=2), baseline=baseline, metric="correct")
    assert passed is False
    assert any("undetectable" in r and "3 baseline-scoring" in r for r in reasons)


def test_a_baseline_that_scores_nothing_cannot_be_regressed_against():
    passed, _ = eh.gate(runs([1.0] * 3, n=2), baseline=runs([0.0] * 3, n=2), metric="correct")
    assert passed is True


def test_gate_refuses_to_pair_different_case_sets():
    with pytest.raises(ValueError, match="same cases"):
        eh.gate(runs([1.0] * 6, n=1), baseline=runs([1.0] * 7, n=1), metric="correct")


def test_a_0_1_0_baseline_file_still_pairs_by_case(tmp_path):
    """0.1.0 saved only the flat list plus n; case_means recovers the cases from that."""
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"scores": {"correct": [1.0] * 16}, "tokens": [], "latency": [], "n": 2, "cases": 8}))
    passed, reasons = eh.gate(runs([0.0] * 8, n=2), baseline=eh.load_baseline(str(path)), metric="correct")
    assert passed is False
    assert any("significant" in r and "8 paired cases" in r for r in reasons)


# ---------------------------------------------------------------------------
# label_match (R4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("out", ["positive", "Positive", " positive.\n", "**positive**", "'positive'"])
def test_label_match_accepts_the_label_alone(out):
    assert eh.label_match(out, eh.Case("x", "positive")) == 1.0


@pytest.mark.parametrize("out", ["positive, not negative", "negative", "It is positive", ""])
def test_label_match_rejects_anything_but_the_label(out):
    assert eh.label_match(out, eh.Case("x", "positive")) == 0.0


def test_label_match_is_case_insensitive_on_the_expected_side():
    """The 0.1.0 substring grader never matched an expected label with capitals."""
    assert eh.label_match("positive", eh.Case("x", "Positive")) == 1.0


# ---------------------------------------------------------------------------
# baseline provenance (R6)
# ---------------------------------------------------------------------------


def test_run_suite_records_the_case_set_and_what_produced_the_runs():
    cases = [eh.Case("a", "x"), eh.Case("b", "y")]
    meta = {"model": "m", "temperature": 0.0}
    result = eh.run_suite(cases, lambda inp: ("x", 1), {"correct": CORRECT}, n=1, meta=meta)
    assert result["cases_sha256"] == eh.cases_sha256(cases)
    assert result["meta"] == meta


def test_case_set_hash_changes_with_any_input_or_label():
    base = [eh.Case("a", "x"), eh.Case("b", "y")]
    assert eh.cases_sha256(base) == eh.cases_sha256([eh.Case("a", "x"), eh.Case("b", "y")])
    assert eh.cases_sha256(base) != eh.cases_sha256([eh.Case("a", "x"), eh.Case("b", "z")])
    assert eh.cases_sha256(base) != eh.cases_sha256(list(reversed(base)))


def test_gate_refuses_a_baseline_from_a_different_case_set_of_the_same_size():
    one = [eh.Case(str(i), "x") for i in range(6)]
    other = [eh.Case(str(i), "y") for i in range(6)]
    run = lambda inp: ("x", 1)
    with pytest.raises(ValueError, match="same cases"):
        eh.gate(eh.run_suite(one, run, {"correct": CORRECT}, n=1),
                baseline=eh.run_suite(other, run, {"correct": CORRECT}, n=1), metric="correct")


def test_provenance_survives_the_baseline_round_trip(tmp_path):
    result = eh.run_suite([eh.Case("a", "x")], lambda inp: ("x", 1), {"correct": CORRECT}, n=1,
                          meta={"model": "m"})
    path = tmp_path / "b.json"
    eh.save_baseline(str(path), result)
    restored = eh.load_baseline(str(path))
    assert restored["meta"] == {"model": "m"}
    assert restored["cases_sha256"] == result["cases_sha256"]

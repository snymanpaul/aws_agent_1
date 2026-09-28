"""Tests for ship_gate, the single GO/NO-GO verdict over a candidate.

This is the last thing consulted before something ships, so a wrong GO is the most
expensive failure in the repo. Its verdict logic went untested because the only way to
reach it was a paid run.

`ship_gate` now takes an optional `run_fn`, mirroring the injection point `run_suite`
already exposes. That supplies the runs without softening the thresholds: quality,
cost and significance are still judged by the same code path used in production.

No model, no network, no credentials, no spend.

    uv run pytest tests/test_ship_gate.py -q
"""

import json
import pathlib

import pytest

# Needs the [strands] extra. Skip rather than fail if the optional dependency is absent,
# so the three stdlib gates stay testable on a bare install.
sg = pytest.importorskip(
    "agent_build_gates.ship_gate",
    reason="ship_gate needs the [strands] extra: pip install 'agent-build-gates[strands]'",
)

CASES = [sg.Case("a", "positive"), sg.Case("b", "negative")]
EVALUATORS = {"correct": sg.CORRECT}


def answering(mapping, tokens=20):
    """A run_fn returning a recorded answer per input, with a fixed token count."""
    def run(inp):
        return mapping[inp], tokens
    return run


PERFECT = answering({"a": "positive", "b": "negative"})
WRONG = answering({"a": "negative", "b": "positive"})

# Baseline comparisons need at least 6 cases to have the power to detect a regression;
# the package's own 8-case suite is used for those, answered by label.
SUITE = sg.CASES
SUITE_PERFECT = lambda tokens=20: answering({c.input: c.expected for c in SUITE}, tokens)
SUITE_WRONG = answering({c.input: {"positive": "negative", "negative": "positive"}[c.expected] for c in SUITE})


def test_a_passing_candidate_ships(tmp_path):
    verdict, result = sg.ship_gate(
        "unused", CASES, EVALUATORS, n=2, label="good",
        audit_dir=str(tmp_path), run_fn=PERFECT,
    )
    assert verdict["decision"] == "GO"
    assert verdict["reasons"] == []
    assert verdict["quality"] == 1.0
    assert verdict["n"] == 2
    assert result["cases"] == 2


def test_a_failing_candidate_is_blocked(tmp_path):
    verdict, _ = sg.ship_gate(
        "unused", CASES, EVALUATORS, n=2, label="bad",
        audit_dir=str(tmp_path), run_fn=WRONG,
    )
    assert verdict["decision"] == "NO-GO"
    assert verdict["reasons"], "a block must cite at least one concrete reason"
    assert any("quality" in r for r in verdict["reasons"])


def test_the_quality_floor_is_what_decides(tmp_path):
    """Same runs, different threshold: the verdict has to follow the threshold."""
    strict, _ = sg.ship_gate(
        "unused", CASES, EVALUATORS, n=2, label="strict", min_quality=0.9,
        audit_dir=str(tmp_path), run_fn=answering({"a": "positive", "b": "wrong"}),
    )
    lenient, _ = sg.ship_gate(
        "unused", CASES, EVALUATORS, n=2, label="lenient", min_quality=0.4,
        audit_dir=str(tmp_path), run_fn=answering({"a": "positive", "b": "wrong"}),
    )
    assert strict["decision"] == "NO-GO"
    assert lenient["decision"] == "GO"


def test_a_token_blowout_against_baseline_is_blocked(tmp_path):
    """max_tokens_factor is applied to the baseline mean, not an absolute number."""
    _, baseline = sg.ship_gate(
        "unused", SUITE, EVALUATORS, n=2, label="base",
        audit_dir=str(tmp_path), run_fn=SUITE_PERFECT(tokens=10),
    )
    verdict, _ = sg.ship_gate(
        "unused", SUITE, EVALUATORS, n=2, label="expensive", baseline=baseline,
        max_tokens_factor=2.0, audit_dir=str(tmp_path), run_fn=SUITE_PERFECT(tokens=500),
    )
    assert verdict["decision"] == "NO-GO"
    assert any("tokens" in r for r in verdict["reasons"])


def test_equal_cost_against_baseline_still_ships(tmp_path):
    """Negative control for the cost gate: same tokens must not trip it."""
    _, baseline = sg.ship_gate(
        "unused", SUITE, EVALUATORS, n=2, label="base2",
        audit_dir=str(tmp_path), run_fn=SUITE_PERFECT(tokens=10),
    )
    verdict, _ = sg.ship_gate(
        "unused", SUITE, EVALUATORS, n=2, label="same_cost", baseline=baseline,
        max_tokens_factor=2.0, audit_dir=str(tmp_path), run_fn=SUITE_PERFECT(tokens=10),
    )
    assert verdict["decision"] == "GO"


def test_a_significant_regression_against_baseline_is_blocked(tmp_path):
    _, baseline = sg.ship_gate(
        "unused", SUITE, EVALUATORS, n=2, label="base3",
        audit_dir=str(tmp_path), run_fn=SUITE_PERFECT(),
    )
    verdict, _ = sg.ship_gate(
        "unused", SUITE, EVALUATORS, n=2, label="regressed", baseline=baseline,
        min_quality=0.0, audit_dir=str(tmp_path), run_fn=SUITE_WRONG,
    )
    assert verdict["decision"] == "NO-GO"
    assert any("significant" in r for r in verdict["reasons"])


def test_too_few_cases_against_a_baseline_is_not_a_go(tmp_path):
    """R3: 2 cases cannot detect a regression, so an unchanged candidate is not cleared."""
    _, baseline = sg.ship_gate(
        "unused", CASES, EVALUATORS, n=8, label="base4",
        audit_dir=str(tmp_path), run_fn=PERFECT,
    )
    verdict, _ = sg.ship_gate(
        "unused", CASES, EVALUATORS, n=8, label="underpowered", baseline=baseline,
        audit_dir=str(tmp_path), run_fn=PERFECT,
    )
    assert verdict["decision"] == "NO-GO"
    assert any("undetectable" in r for r in verdict["reasons"])


def test_the_verdict_is_written_as_an_audit_artifact(tmp_path):
    """A verdict nobody can reproduce is not an audit trail."""
    verdict, _ = sg.ship_gate(
        "unused", CASES, EVALUATORS, n=2, label="audited",
        audit_dir=str(tmp_path), run_fn=PERFECT,
    )
    path = pathlib.Path(verdict["audit_file"])
    assert path.exists()

    saved = json.loads(path.read_text())
    assert saved["decision"] == verdict["decision"]
    assert saved["label"] == "audited"
    assert saved["reasons"] == verdict["reasons"]
    assert "result" in saved, "the artifact must carry the underlying runs, not just the verdict"
    assert len(saved["result"]["scores"]["correct"]) == 4


def test_the_audit_file_is_named_for_its_label(tmp_path):
    """Two candidates in one session must not overwrite each other's evidence."""
    first, _ = sg.ship_gate("unused", CASES, EVALUATORS, n=1, label="alpha",
                            audit_dir=str(tmp_path), run_fn=PERFECT)
    second, _ = sg.ship_gate("unused", CASES, EVALUATORS, n=1, label="beta",
                             audit_dir=str(tmp_path), run_fn=PERFECT)
    assert first["audit_file"] != second["audit_file"]
    assert pathlib.Path(first["audit_file"]).exists()
    assert pathlib.Path(second["audit_file"]).exists()


def test_the_injected_run_fn_is_what_gets_judged(tmp_path):
    """Guards the seam itself: if the default runner were used, this would try to
    reach the proxy and the recorded answers below would never appear."""
    seen = []

    def recording(inp):
        seen.append(inp)
        return "positive", 7

    sg.ship_gate("unused", CASES, EVALUATORS, n=3, label="seam",
                 audit_dir=str(tmp_path), run_fn=recording)

    assert seen == ["a", "a", "a", "b", "b", "b"]


def test_the_result_records_what_produced_it(tmp_path):
    """R6: an injected run_fn picks its own model, so only the prompt hash is claimed."""
    import hashlib
    _, result = sg.ship_gate("the prompt", CASES, EVALUATORS, n=1, label="prov",
                             audit_dir=str(tmp_path), run_fn=PERFECT)
    assert result["meta"] == {"system_prompt_sha256": hashlib.sha256(b"the prompt").hexdigest(),
                              "run_fn": "injected"}
    from agent_build_gates.eval_harness import cases_sha256
    assert result["cases_sha256"] == cases_sha256(CASES)

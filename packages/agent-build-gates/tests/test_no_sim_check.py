"""Tests for no_sim_check, the tripwire this repo's evidence standard rests on.

A tripwire with no test proving it fires is an unevidenced claim. These tests apply
the same positive/negative control discipline the evals track (L83 to L92) applies to
every evaluator:

  - POSITIVE CONTROLS: source the checker MUST flag. If these stop failing, the gate
    has gone blind and every "passes no_sim_check" claim in the repo is worthless.
  - NEGATIVE CONTROLS: source the checker MUST NOT flag, including the two documented
    escape routes (a line that prohibits the practice, and an explicit `nosim:ok`).
  - CHARACTERIZATION: `test_known_limitation_*` pin behaviour that is currently a gap.
    They assert what the checker DOES, not what it SHOULD do, so the gap is visible in
    the test report rather than assumed away. Flip them when the rule is tightened.

Fixture source is built line by line rather than as triple-quoted blocks so each
physical line here that embeds trigger text can carry its own `nosim:ok`. Without that
this file would trip the very checker it tests. Run
`no-sim-check <path>` to confirm it stays clean.

    uv run pytest tests/test_no_sim_check.py -q
"""

import pytest

from agent_build_gates import no_sim_check as nsc


def write_py(tmp_path, lines, name="lesson.py"):
    """Write fixture lines to a .py file and return its path."""
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n")
    return path


def rules_fired(path):
    """Return the set of rule names the checker reports for a file."""
    return {rule for _, rule, _ in nsc.scan_file(path)}


# ---------------------------------------------------------------------------
# Positive controls: the checker MUST fire
# ---------------------------------------------------------------------------


FAKE_RETURN_PHRASES = [  # nosim:ok fixture constant
    "Blueprint data prepared for persistence",  # nosim:ok fixture text
    "the record would be written here",  # nosim:ok fixture text
    "placeholder until the API lands",  # nosim:ok fixture text
    "sample data for the demo",  # nosim:ok fixture text
    "queued to persist later",  # nosim:ok fixture text
    "TODO wire up the client",  # nosim:ok fixture text
]


@pytest.mark.parametrize("phrase", FAKE_RETURN_PHRASES)  # nosim:ok fixture constant
def test_fires_on_fake_success_return(tmp_path, phrase):  # nosim:ok test name
    """Every phrase in the fake-success-return rule must be caught."""  # nosim:ok
    path = write_py(tmp_path, [
        "def save(record):",
        f'    return "{phrase}"',
    ])
    assert "fake-success-return" in rules_fired(path)  # nosim:ok rule name


@pytest.mark.parametrize("line", [
    "# In production, this would call the billing API",  # nosim:ok fixture text
    "# in production it will persist to DynamoDB",  # nosim:ok fixture text
    "# In production, we should retry here",  # nosim:ok fixture text
])
def test_fires_on_in_production_deferral(tmp_path, line):
    """Deferring the real call to an imagined future must be caught."""
    path = write_py(tmp_path, [line, "print(payload)"])
    assert "in-production-deferral" in rules_fired(path)


@pytest.mark.parametrize("line", [
    '    resp = simulate("payment")',  # nosim:ok fixture text
    "    values = [simulated(x) for x in rows]",  # nosim:ok fixture text
    "    resp = simulate_payment()",  # nosim:ok fixture text
    "    handler = SimulatedGateway()",  # nosim:ok fixture text
])
def test_fires_on_simulated_integration(tmp_path, line):  # nosim:ok test name
    """The simulat* family must be caught in code, including inside identifiers."""  # nosim:ok
    path = write_py(tmp_path, ["def run(rows):", line])
    assert "simulated-integration" in rules_fired(path)  # nosim:ok rule name


@pytest.mark.parametrize("line", [
    "    client = Mock()",  # nosim:ok fixture text
    "    client = stub()",  # nosim:ok fixture text
    '    tracking = "fake"',  # nosim:ok fixture text
    "    payload = dummy",  # nosim:ok fixture text
    '    account = "hardcoded"',  # nosim:ok fixture text
    '    account = "hard coded"',  # nosim:ok fixture text
    "    client = mock_client()",  # nosim:ok fixture text
    "    value = fake_row",  # nosim:ok fixture text
    "    queue = MockSQSQueue()",  # nosim:ok fixture text
])
def test_fires_on_mock_stub_fake_vocabulary(tmp_path, line):  # nosim:ok test name
    """Substitute-object vocabulary, including inside snake_case and CamelCase names."""
    path = write_py(tmp_path, ["def build():", line])
    assert "mock-stub-fake" in rules_fired(path)  # nosim:ok rule name


def test_fires_on_assume_good_default_under_except(tmp_path):
    """A True returned straight out of an except block claims unearned success."""
    path = write_py(tmp_path, [
        "def delivered():",
        "    try:",
        "        return post()",
        "    except Exception:",
        "        return True",
    ])
    assert "assume-good-default" in rules_fired(path)


def test_fires_on_every_rule_at_once(tmp_path):
    """A file carrying all five smells reports all five, not just the first."""
    path = write_py(tmp_path, [
        "def save(record):",
        '    return "sample data for the demo"',  # nosim:ok fixture text
        "",
        "def defer(payload):",
        "    # In production, this would call the billing API",  # nosim:ok fixture text
        "    return payload",
        "",
        "def run():",
        '    return simulate("payment")',  # nosim:ok fixture text
        "",
        "def build():",
        "    client = Mock()",  # nosim:ok fixture text
        "    return client",
        "",
        "def delivered():",
        "    try:",
        "        return post()",
        "    except Exception:",
        "        return True",
    ])
    assert rules_fired(path) == {
        "fake-success-return",  # nosim:ok rule name
        "in-production-deferral",
        "simulated-integration",  # nosim:ok rule name
        "mock-stub-fake",  # nosim:ok rule name
        "assume-good-default",
    }


# ---------------------------------------------------------------------------
# Negative controls: the checker MUST NOT fire
# ---------------------------------------------------------------------------


def test_clean_real_integration_passes(tmp_path):
    """Ordinary code that calls a real service must not be flagged."""
    path = write_py(tmp_path, [
        "import boto3",
        "",
        "def put(record):",
        '    table = boto3.resource("dynamodb").Table("lessons")',
        "    resp = table.put_item(Item=record)",
        '    return resp["ResponseMetadata"]["HTTPStatusCode"]',
    ])
    assert nsc.scan_file(path) == []


@pytest.mark.parametrize("line", [
    "# never simulate the integration, call the real service",  # nosim:ok fixture text
    "# no mocks anywhere in this repo",  # nosim:ok fixture text
    "# real client, instead of a stub",  # nosim:ok fixture text
    "# fail if the response is fake",  # nosim:ok fixture text
])
def test_guard_line_prohibiting_the_practice_is_ignored(tmp_path, line):
    """A line that talks ABOUT the rule is not a violation of it."""
    path = write_py(tmp_path, [line, "resp = client.invoke(payload)"])
    assert nsc.scan_file(path) == []


def test_nosim_ok_escape_hatch_is_honoured(tmp_path):
    """An explicitly justified line is skipped."""
    path = write_py(tmp_path, [
        "def build():",
        '    tracking = "hardcoded"  # nosim:ok deliberate constant in the L56 fixture',
        "    return tracking",
    ])
    assert nsc.scan_file(path) == []


def test_good_default_not_under_except_is_ignored(tmp_path):
    """An optimistic value is only suspicious when it swallows an exception."""
    path = write_py(tmp_path, [
        "def perfect_score():",
        "    return 1.0",
    ])
    assert nsc.scan_file(path) == []


def test_good_default_two_lines_below_except_is_ignored(tmp_path):
    """The positional rule is documented as 'directly under an except:'.

    Pins the boundary of the rule so a future widening is a deliberate change.
    """
    path = write_py(tmp_path, [
        "def score():",
        "    try:",
        "        return measure()",
        "    except Exception:",
        '        log("failed")',
        "        return 1.0",
    ])
    assert nsc.scan_file(path) == []


def test_empty_file_is_clean(tmp_path):
    path = write_py(tmp_path, [])
    assert nsc.scan_file(path) == []


# ---------------------------------------------------------------------------
# Reporting: line numbers, rule names, counts, exit codes
# ---------------------------------------------------------------------------


def test_reports_correct_line_number(tmp_path):
    path = write_py(tmp_path, [
        "def save(record):",
        "    validate(record)",
        '    return "sample data for the demo"',  # nosim:ok fixture text
    ])
    hits = nsc.scan_file(path)
    assert len(hits) == 1
    line_no, rule, text = hits[0]
    assert line_no == 3
    assert rule == "fake-success-return"  # nosim:ok rule name
    assert text.startswith("return")


def test_reported_text_is_truncated_to_100_chars(tmp_path):
    path = write_py(tmp_path, [
        "def save():",
        '    return "sample data for the demo ' + "x" * 200 + '"',  # nosim:ok fixture text
    ])
    _, _, text = nsc.scan_file(path)[0]
    assert len(text) == 100


def test_main_returns_1_and_prints_findings(tmp_path, capsys):
    path = write_py(tmp_path, [
        "def save():",
        '    return "sample data for the demo"',  # nosim:ok fixture text
    ])
    assert nsc.main([str(path)]) == 1
    out = capsys.readouterr().out
    assert f"{path}:2: [fake-success-return]" in out  # nosim:ok rule name
    assert "scanned 1 file(s), 1 simulation smell(s)" in out  # nosim:ok expected output


def test_main_returns_0_on_clean_input(tmp_path, capsys):
    path = write_py(tmp_path, ["resp = client.invoke(payload)"])
    assert nsc.main([str(path)]) == 0
    assert "scanned 1 file(s), 0 simulation smell(s)" in capsys.readouterr().out  # nosim:ok expected output


def test_main_returns_2_without_arguments(capsys):
    assert nsc.main([]) == 2
    assert "usage:" in capsys.readouterr().out


def test_main_scans_a_directory_recursively(tmp_path, capsys):
    write_py(tmp_path, ["resp = client.invoke(payload)"], name="clean.py")
    nested = tmp_path / "sub"
    nested.mkdir()
    write_py(nested, [
        "def save():",
        '    return "sample data for the demo"',  # nosim:ok fixture text
    ], name="dirty.py")

    assert nsc.main([str(tmp_path)]) == 1
    assert "scanned 2 file(s), 1 simulation smell(s)" in capsys.readouterr().out  # nosim:ok expected output


# ---------------------------------------------------------------------------
# File selection
# ---------------------------------------------------------------------------


def test_iter_py_selects_only_python_files(tmp_path):
    (tmp_path / "lesson.py").write_text("x = 1\n")
    (tmp_path / "notes.md").write_text('return "sample data for the demo"\n')  # nosim:ok fixture text
    (tmp_path / "data.json").write_text("{}\n")

    assert {p.name for p in nsc.iter_py([str(tmp_path)])} == {"lesson.py"}


def test_iter_py_never_scans_the_checker_itself(tmp_path):
    """Self-exclusion by filename, so the rule definitions do not trip their own rules."""
    (tmp_path / "no_sim_check.py").write_text('return "sample data for the demo"\n')  # nosim:ok fixture text
    (tmp_path / "lesson.py").write_text("x = 1\n")

    assert {p.name for p in nsc.iter_py([str(tmp_path)])} == {"lesson.py"}
    assert list(nsc.iter_py([str(tmp_path / "no_sim_check.py")])) == []


def test_iter_py_accepts_explicit_file_paths(tmp_path):
    target = tmp_path / "lesson.py"
    target.write_text("x = 1\n")
    assert [p.name for p in nsc.iter_py([str(target)])] == ["lesson.py"]


def test_undecodable_bytes_do_not_crash_the_scan(tmp_path):
    """read_text(errors="replace") means a binary-ish .py must not abort a repo sweep."""
    path = tmp_path / "lesson.py"
    path.write_bytes(b'\xff\xfe\ndef save():\n    return "sample data for the demo"\n')  # nosim:ok fixture text
    assert "fake-success-return" in rules_fired(path)  # nosim:ok rule name


# ---------------------------------------------------------------------------
# Characterization: known gaps, pinned so they stay visible
# ---------------------------------------------------------------------------


def test_trailing_comment_cannot_mask_a_real_smell(tmp_path):
    """A guard word in a trailing comment must not exempt the code on the line.

    GUARD is evaluated against the code portion when the line has one, so an
    incidental negation in a comment no longer blinds the rule.
    """
    path = write_py(tmp_path, [
        "def save(record):",
        '    return "sample data for the demo"  # not yet wired up',  # nosim:ok fixture text
    ])
    assert "fake-success-return" in rules_fired(path)  # nosim:ok rule name


@pytest.mark.parametrize("default", ['""', "''", "[]", "{}", "1.0", "5.0", "0.0"])
def test_non_true_defaults_are_deliberately_ignored(tmp_path, default):
    """Only `return True` counts as an assume-good default.

    A bare number cannot be judged optimistic without knowing the metric. In this
    repo's pass-ratio scorers 0.0 is the floor, and every numeric hit found by the
    old rule was a false positive.
    """
    path = write_py(tmp_path, [
        "def score():",
        "    try:",
        "        return measure()",
        "    except Exception:",
        f"        return {default}",
    ])
    assert nsc.scan_file(path) == []


def test_vocabulary_rules_do_not_fire_on_comments(tmp_path):
    """Prose cannot fake an integration, so comments are exempt from the two
    vocabulary rules. This is what removes the bulk of the historical noise.
    """
    path = write_py(tmp_path, [
        "# simulate network latency so the parallel speedup is visible",  # nosim:ok fixture text
        "# Mock some items for demonstration",  # nosim:ok fixture text
        "time.sleep(0.1)",
    ])
    assert nsc.scan_file(path) == []


def test_vocabulary_rules_do_not_fire_on_docstrings(tmp_path):
    """A docstring describing a scenario is prose, not a substituted call."""
    path = write_py(tmp_path, [
        "def flaky_api_call():",
        '    """Simulates an API that fails a few times before succeeding."""',  # nosim:ok fixture text
        '    raise ConnectionError("Connection refused")',
    ])
    assert nsc.scan_file(path) == []


def test_deferral_rule_still_reads_comments(tmp_path):
    """The deferral rule is not suppressed on prose: a deferral comment is the
    marker for a call that was never made, which is exactly the webhook case.
    """
    path = write_py(tmp_path, [
        "def send(event):",
        "    # In production, this would POST to the webhook",  # nosim:ok fixture text
        "    return True",
    ])
    assert "in-production-deferral" in rules_fired(path)


def test_class_standing_in_for_a_service_is_caught_by_its_name(tmp_path):
    """The regression that motivated the boundary fix.

    `class MockSQSQueue:` was previously invisible; only its docstring tripped the
    rule. With docstrings exempt, the name has to carry the detection.
    """
    path = write_py(tmp_path, [
        "class MockSQSQueue:",  # nosim:ok fixture text
        '    """An in-memory queue."""',
        "    def send_message(self, body):",
        "        return body",
    ])
    assert "mock-stub-fake" in rules_fired(path)  # nosim:ok rule name


def test_known_limitation_vendor_directories_are_not_excluded(tmp_path):
    """iter_py rglobs every .py under a directory, including .venv and site-packages.

    Pointing the checker at the repo root therefore sweeps dependencies. Callers must
    pass explicit paths until an exclusion list exists.
    """
    vendored = tmp_path / ".venv" / "lib"
    vendored.mkdir(parents=True)
    (vendored / "third_party.py").write_text("x = 1\n")

    assert "third_party.py" in {p.name for p in nsc.iter_py([str(tmp_path)])}

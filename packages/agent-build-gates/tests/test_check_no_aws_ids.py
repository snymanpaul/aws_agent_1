"""Tests for check_no_aws_ids, the tripwire that keeps account identifiers out of the repo.

This gate had no tests while it was the only thing enforced on every commit. Packaging then
forced a real change to it: it used to resolve every path against its own location
(`Path(__file__).parents[1]`), which is correct when vendored at `tools/` and wrong from
site-packages, where it would point into the virtualenv instead of the caller's repo. It now
resolves against the working directory.

That is a behavioural change to a security control, so the paired controls below cover both
what it must catch and what it must not.

    uv run pytest packages/agent-build-gates/tests/test_check_no_aws_ids.py -q
"""

import pathlib

import pytest

from agent_build_gates import check_no_aws_ids as cna


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Run each test from a scratch directory, since paths now resolve against cwd."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write(workdir, name, text):
    path = workdir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")
    return name


# ---------------------------------------------------------------------------
# Positive controls: one per pattern the gate claims to catch
# ---------------------------------------------------------------------------


def test_catches_a_bare_account_id(workdir, capsys):
    name = write(workdir, "notes.md", "deployed into account 481516234299 last week")  # noaws:ok fixture for this gate's own tests
    assert cna.scan([name]) == 1
    assert "12-digit AWS account id" in capsys.readouterr().out


def test_catches_an_sso_admin_profile_string(workdir, capsys):
    name = write(workdir, "setup.md", "export AWS_PROFILE=AWSAdministratorAccess-481516")  # noaws:ok fixture for this gate's own tests
    assert cna.scan([name]) == 1
    assert "SSO admin profile string" in capsys.readouterr().out


def test_catches_an_sso_account_reference(workdir, capsys):  # noaws:ok fixture for this gate's own tests
    name = write(workdir, "conf.py", 'SSO_ACCOUNT = "redacted"')  # noaws:ok fixture for this gate's own tests
    assert cna.scan([name]) == 1
    assert "sso_account reference" in capsys.readouterr().out  # noaws:ok fixture for this gate's own tests


def test_catches_an_arn_carrying_an_account_field(workdir, capsys):
    """Caught, though reported under the account-id label rather than the ARN one.

    Patterns are checked in order and break on the first match, and every standard ARN
    account field is also a bare 12-digit run, so the first pattern always claims it.
    That makes the ARN rule's own label unreachable in practice. Harmless, since the
    leak is still blocked, but pinned here so the ordering is a decision rather than an
    accident: reordering the list would change the label without changing the verdict.
    """
    name = write(workdir, "policy.md", "arn:aws:iam::481516234299:role/Admin")  # noaws:ok fixture for this gate's own tests
    assert cna.scan([name]) == 1
    assert "12-digit AWS account id" in capsys.readouterr().out


def test_reports_the_line_number_and_the_offending_line(workdir, capsys):
    name = write(workdir, "notes.md", "clean line\nsecond clean\naccount 481516234299 here")  # noaws:ok fixture for this gate's own tests
    cna.scan([name])
    out = capsys.readouterr().out
    assert f"{name}:3:" in out
    assert "account 481516234299 here" in out  # noaws:ok fixture for this gate's own tests


def test_counts_every_offending_file(workdir):
    a = write(workdir, "a.md", "account 481516234299")  # noaws:ok fixture for this gate's own tests
    b = write(workdir, "b.py", "account = 481516234298")  # noaws:ok fixture for this gate's own tests
    assert cna.scan([a, b]) == 2


# ---------------------------------------------------------------------------
# Negative controls: what it must not flag
# ---------------------------------------------------------------------------


def test_clean_content_passes(workdir):
    name = write(workdir, "notes.md", "no identifiers here, just prose and a number 42")
    assert cna.scan([name]) == 0


@pytest.mark.parametrize("literal", sorted(cna.ALLOW))
def test_known_safe_literals_are_not_flagged(workdir, literal):
    """The allow-list exists so documented placeholders do not block every commit."""
    name = write(workdir, "notes.md", f"placeholder value {literal} in the docs")
    assert cna.scan([name]) == 0


def test_the_allow_list_is_overridable_at_the_call_site(workdir):
    """A consumer with its own placeholders extends the set rather than editing the module."""
    name = write(workdir, "notes.md", "vendor reference 481516234299")  # noaws:ok fixture for this gate's own tests
    assert cna.scan([name]) == 1
    assert cna.scan([name], allow=cna.ALLOW | {"481516234299"}) == 0  # noaws:ok fixture for this gate's own tests


def test_a_shorter_or_longer_run_of_digits_is_not_an_account_id(workdir):
    """The pattern is word-bounded at exactly twelve digits."""
    name = write(workdir, "notes.md", "ids 48151623429 and 4815162342990 are other things")
    assert cna.scan([name]) == 0


def test_non_text_extensions_are_skipped(workdir):
    """The rule is scoped to .md and .py, where a bare 12-digit run is never legitimate."""
    name = write(workdir, "data.json", '{"account": "481516234299"}')  # noaws:ok fixture for this gate's own tests
    assert cna.scan([name]) == 0


def test_a_missing_path_is_ignored_rather_than_raising(workdir):
    """The pre-commit hook passes staged names, which can include a deleted file."""
    assert cna.scan(["never_existed.md"]) == 0


def test_the_module_does_not_flag_its_own_pattern_definitions():
    """Self-exclusion by resolved path, not by a hardcoded repo-relative string."""
    assert cna.scan([str(cna.SELF_PATH)]) == 0


def test_a_line_marked_noaws_ok_is_skipped(workdir):
    """The per-line escape, mirroring no_sim_check's nosim:ok.

    Without it, a test suite for this gate cannot contain the strings it detects, and
    neither can documentation describing them. This file relies on it throughout.
    """
    name = write(workdir, "notes.py", 'ACCOUNT = "481516234299"  # noaws:ok fixture')  # noaws:ok
    assert cna.scan([name]) == 0


def test_the_escape_works_in_markdown_comments_too(workdir):
    """Markdown has no # comment, so the marker is matched anywhere on the line."""
    name = write(workdir, "doc.md", "example id 481516234299 <!-- noaws:ok docs -->")  # noaws:ok
    assert cna.scan([name]) == 0


def test_the_escape_only_covers_its_own_line(workdir):
    """Negative control: a marker must not blanket the rest of the file."""
    name = write(
        workdir,
        "notes.md",
        "first 481516234299 <!-- noaws:ok -->\nsecond 481516234298 with no marker",  # noaws:ok
    )
    assert cna.scan([name]) == 1


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def test_main_returns_zero_and_reports_the_count_when_clean(workdir, capsys):
    name = write(workdir, "notes.md", "nothing to see")
    assert cna.main([name]) == 0
    assert "scanned 1 file(s), clean." in capsys.readouterr().out


def test_main_returns_one_and_says_blocked_on_a_hit(workdir, capsys):
    name = write(workdir, "notes.md", "account 481516234299")  # noaws:ok fixture for this gate's own tests
    assert cna.main([name]) == 1
    assert "BLOCKED" in capsys.readouterr().out


def test_main_with_no_arguments_falls_back_to_tracked_files(workdir, monkeypatch, capsys):
    """With no arguments it asks git for the tracked set, in the caller's repo."""
    write(workdir, "tracked.md", "clean content")
    monkeypatch.setattr(cna, "tracked_md_py", lambda: ["tracked.md"])
    assert cna.main([]) == 0
    assert "scanned 1 file(s), clean." in capsys.readouterr().out


def test_paths_resolve_against_the_working_directory(tmp_path, monkeypatch):
    """The packaging fix. Resolving against the module's own location would look
    inside site-packages and silently find nothing to scan."""
    (tmp_path / "leak.md").write_text("account 481516234299\n")  # noaws:ok fixture for this gate's own tests
    monkeypatch.chdir(tmp_path)
    assert cna.scan(["leak.md"]) == 1

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert cna.scan(["leak.md"]) == 0, "a relative path must be read from the new cwd"
    assert cna.scan([str(tmp_path / "leak.md")]) == 1, "an absolute path must still resolve"

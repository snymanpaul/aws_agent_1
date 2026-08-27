"""Append what publishing agent-build-gates 0.1.0 to PyPI actually involved."""

import json
import pathlib

LOG = pathlib.Path(__file__).resolve().parent.parent / ".claude/learnings/observations.jsonl"
TS = "2026-08-27T05:40:00Z"

ENTRIES = [
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="insight",
        topic="agent-build-gates-0-1-0-is-on-pypi",
        obs="Published 2026-08-27 through release.yml: build, smoke-test both artifacts in "
            "isolation, assert the licence ships, twine check, TestPyPI, then PyPI behind the "
            "required reviewer. All three jobs green. Verified by installing from each real index "
            "rather than from disk: both console scripts run, and the installed dist-info carries "
            "License-Expression: MIT, License-File: LICENSE and licenses/LICENSE. That closes the "
            "gap this repo shipped with, a package asserting MIT with no MIT text. `pip install "
            "agent-build-gates` is now a true statement; it returned 404 the same morning.",
        ctx="Run 33041958664. sha256 98358e7b... for the sdist, upload-time 05:19:28Z.",
        entities=["PyPI", "agent-build-gates", "Release", "TrustedPublishing"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="pattern",
        topic="pypi-gates-account-management-behind-mandatory-2fa",
        obs="Registering the trusted publishers could not be automated at all, for two independent "
            "reasons found in order. First, PyPI documents no API for it: the API index lists "
            "Index, JSON, Upload, Integrity, Stats, BigQuery, RSS and Secret-reporting, and trusted "
            "publisher management is not among them, so it is web UI only. Second, "
            "/manage/account/publishing/ redirects to a 2FA enrolment gate until 2FA is enabled, "
            "and PyPI states that once enabled it cannot be disabled. Enrolment needs recovery "
            "codes and a TOTP secret or hardware key, which is a security-settings change and a "
            "credential handling task, so it was Paul's to do. What WAS automatable: the two GitHub "
            "Environments, created through `gh api` with the pypi one carrying a required reviewer, "
            "and the form-filling itself once he had logged in and enrolled.",
        ctx="Browser-driven form fill on pypi.org and test.pypi.org after 2FA enrolment.",
        entities=["PyPI", "2FA", "Automation", "Boundary", "TrustedPublishing"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="insight",
        topic="publishing-dissolved-the-cross-repo-coupling",
        obs="The whole packaging thread started from Paul asking whether the git dependency was "
            "brittle. It was, though not in the way first reported: `uv sync --frozen` already "
            "pinned a SHA rather than floating on main, so the real risks were narrower and "
            "different (a branch commit is not durable against a history rewrite; 12 MB cloned per "
            "CI run for a 304 KB subdirectory; silent movement on `uv lock --upgrade`; and a doc "
            "claim of `pip install agent-build-gates` that 404'd). Publishing removed all four at "
            "once. aws_data_engineering now declares `agent-build-gates>=0.1.0` with no "
            "[tool.uv.sources] block, and its lockfile contains ZERO references to aws_agent_1, "
            "resolving from the PyPI registry with a sha256 instead.",
        ctx="uv lock: 'Updated agent-build-gates v0.1.0 (b82c35f2) -> v0.1.0'.",
        entities=["Packaging", "Coupling", "uv", "Architecture", "PyPI"],
    ),
]


def main() -> None:
    before = len(LOG.read_text().splitlines())
    with LOG.open("a") as fh:
        for e in ENTRIES:
            fh.write(json.dumps(e) + "\n")
    after = len(LOG.read_text().splitlines())
    print(f"observations.jsonl: {before} -> {after} entries")
    for e in ENTRIES:
        print(f"  {e['cat']:8} {e['topic']}")


if __name__ == "__main__":
    main()

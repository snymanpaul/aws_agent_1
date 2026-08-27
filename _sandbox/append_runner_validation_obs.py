"""Append what running the workflows on a real runner turned up.

Everything before this was static analysis. The runner found a defect that three rounds
of local checking, including actionlint, did not.
"""

import json
import pathlib

LOG = pathlib.Path(__file__).resolve().parent.parent / ".claude/learnings/observations.jsonl"
TS = "2026-08-27T03:30:00Z"

ENTRIES = [
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="mistake",
        topic="asserted-a-verification-boundary-instead-of-checking-it",
        obs="Wrote 'nothing here proves the workflows run on a GitHub runner ... will not be until "
            "a push triggers them', framing it as an unavoidable limit. It was not. `origin` was "
            "configured, `gh` was authenticated with workflow scope, and `gh run list` answers part "
            "of it with no push at all: the gates workflow had already run 12 times, all success, "
            "most recently against b82c35f which is exactly origin/main. I had also been treating "
            "that green baseline as fact for the whole session without ever checking it. GENERAL "
            "FORM: 'I cannot verify X' is itself a claim and needs the same proof as any other. "
            "Check what the tooling already knows before declaring a boundary.",
        ctx="Challenged by Paul: 'why are you hand waving again? remote on github is configured'.",
        entities=["Validation", "CI", "gh", "Boundary", "Mistake"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="insight",
        topic="the-runner-found-what-actionlint-could-not",
        obs="First real run of the changed workflows (branch ci-validate, run 33034322404): both "
            "jobs PASSED, including the new diagrams job with Chromium at 2m16s, so the workflow "
            "was functionally correct. But the run carried an annotation no local check produced: "
            "'Node.js 20 is deprecated. The following actions target Node.js 20 but are being "
            "forced to run on Node.js 24: actions/checkout@v4, actions/setup-node@v4'. This "
            "directly refuted the version decision I had defended one commit earlier, that v4 was "
            "fine because only artifact v3 and below are deprecated. The deprecation is on the "
            "RUNTIME the action declares, not on the action version, which is why release notes "
            "missed it. Confirmed by reading each action.yml: v4 declares `using: node20`, v5+ "
            "declares node24, across checkout, setup-node, upload-artifact and download-artifact. "
            "Bumped to v7/v7/v7/v8; re-run 33034522176 is green with ZERO annotations.",
        ctx="A green run is not a clean run. Read the annotations, not just the conclusion.",
        entities=["CI", "GitHubActions", "NodeDeprecation", "Annotations", "Evidence"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="pattern",
        topic="a-throwaway-branch-is-the-cheap-way-to-test-ci",
        obs="Verified without touching main or publishing anything: pushed the 5 unpushed commits "
            "to a `ci-validate` branch, which gates.yml picks up because it triggers on "
            "`push: branches: [\"**\"]`, while release.yml stayed inert because it triggers only on "
            "agent-build-gates-v* tags. Two runs, one defect found and fixed, branch deleted. One "
            "trap worth noting: `git push -u origin HEAD:ci-validate` repointed local main's "
            "upstream at ci-validate as a side effect; use plain `git push origin HEAD:branch`, or "
            "reset the upstream immediately.",
        ctx="Runs 33034322404 (annotated) and 33034522176 (clean), 2026-08-27.",
        entities=["CI", "Validation", "git", "Method"],
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

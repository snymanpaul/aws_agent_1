"""Append the packaging-readiness observations for agent-build-gates."""

import json
import pathlib

LOG = pathlib.Path(__file__).resolve().parent.parent / ".claude/learnings/observations.jsonl"
TS = "2026-08-27T01:30:00Z"

ENTRIES = [
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="mistake",
        topic="package-claimed-mit-and-shipped-no-licence",
        obs="agent-build-gates declared `license = { text = \"MIT\" }` and shipped NO licence text: "
            "`unzip -l` on the wheel and `tar -tzf` on the sdist both had zero matches for 'licen'. "
            "An MIT claim with no MIT file. Two causes, one legal and one mechanical: the repo had "
            "no LICENSE file at all (`git ls-files | grep -i licen` was empty), and the deprecated "
            "PEP 621 `{text = ...}` table only sets a metadata string, it never packages a file. "
            "FIX: add LICENSE, use the PEP 639 form `license = \"MIT\"` plus "
            "`license-files = [\"LICENSE\"]`. Metadata now emits License-Expression: MIT and "
            "License-File: LICENSE, and the file lands at dist-info/licenses/LICENSE in the wheel.",
        ctx="Verified by building with uv and inspecting the artifacts, not by reading pyproject.",
        entities=["Packaging", "PyPI", "PEP639", "Licence", "Mistake"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="insight",
        topic="twine-check-passes-a-package-with-five-defects",
        obs="`twine check` returned PASSED on both artifacts while the package had: no licence file, "
            "a deprecated license table, no project URLs, no classifiers and no author. It validates "
            "that the long description RENDERS, not that the distribution is complete or its claims "
            "are true. Treating it as the packaging gate is the same error as treating a 200 OK as "
            "proof of correctness. The check that actually caught the licence gap was unzipping the "
            "artifact and grepping for the file, which is now an explicit step in release.yml rather "
            "than a thing to remember.",
        ctx="uvx twine check over agent_build_gates-0.1.0 wheel + sdist, before any fix.",
        entities=["Packaging", "twine", "FalseGreen", "Gates", "Evidence"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="pattern",
        topic="trusted-publishing-is-the-current-pypi-path",
        obs="Researched against primary sources for release.yml. PyPA's guide states API tokens are "
            "legacy verbatim: 'If you followed earlier versions of this guide, you have created the "
            "secrets PYPI_API_TOKEN and TEST_PYPI_API_TOKEN ... These are obsolete now'. Structure "
            "that matters: `id-token: write` at JOB level only, so the build job never holds the "
            "credential; separate build and publish jobs for the same reason; a `pypi` GitHub "
            "environment with a required reviewer, which PyPA states as an obligation ('you must "
            "require manual approval on each run for the pypi environment'); TestPyPI as a separate "
            "account with its own pending publisher. A pending publisher does NOT reserve the name "
            "until first publish, so the name can still be taken between registration and release.",
        ctx="Raw sources: pypa/packaging.python.org guide rst + sample yml, astral-sh/uv "
            "docs/guides/integration/github.md, docs.pypi.org trusted-publishers.",
        entities=["PyPI", "TrustedPublishing", "OIDC", "GitHubActions", "Security"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="mistake",
        topic="toml-table-header-swallowed-the-keys-after-it",
        obs="Inserted [project.urls] in the middle of the [project] table, which made every "
            "subsequent bare key part of it. Build failed: 'TypeError: URL `dependencies` of field "
            "`project.urls` must be a string'. A [table] header ends the preceding table, so any "
            "sub-table must come after ALL of the parent's scalar keys. Caught by building rather "
            "than by reading, which is the only reason it took one minute instead of a review cycle.",
        ctx="hatchling metadata validate_fields during uv build.",
        entities=["TOML", "Packaging", "Mistake", "hatchling"],
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

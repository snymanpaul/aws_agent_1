"""Append what revalidating the packaging work actually turned up.

Re-ran the whole chain from a clean clone rather than trusting the first pass, and
checked the release.yml claims that had been written from research rather than run.
"""

import json
import pathlib

LOG = pathlib.Path(__file__).resolve().parent.parent / ".claude/learnings/observations.jsonl"
TS = "2026-08-27T02:10:00Z"

ENTRIES = [
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="mistake",
        topic="uv-publish-default-continues-when-trusted-publishing-fails",
        obs="release.yml called bare `uv publish`, which is wrong for a release path. From "
            "`uv help publish`: 'By default, uv checks for trusted publishing when running in a "
            "supported environment, but IGNORES IT IF IT ISN'T CONFIGURED', and the `automatic` "
            "mode is documented as 'Attempt trusted publishing when we're in a supported "
            "environment, CONTINUE IF THAT FAILS'. So a misconfigured OIDC setup would not stop "
            "the release, it would fall through to whatever other credential source it finds. That "
            "is the silent-fallback shape no_sim_check exists to catch, in the one workflow that "
            "holds publishing rights. FIX: `--trusted-publishing always` on both publish steps. "
            "Found by revalidating a flag I had written from documentation rather than run.",
        ctx="uv 0.8.22 `uv help publish`; flag combination confirmed accepted (fails at runtime "
            "with 'No files found to publish', not at parse).",
        entities=["PyPI", "uv", "TrustedPublishing", "SilentFallback", "Mistake"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="insight",
        topic="hatchling-does-not-fail-on-an-unmatched-license-files-glob",
        obs="Negative control for the release workflow's licence assertion: deleted LICENSE and "
            "removed `license-files` from pyproject, then rebuilt. The build SUCCEEDED with no "
            "warning, emitting `License-Expression: MIT` and no `License-File`, producing exactly "
            "the defective artifact the package shipped before. twine check returned PASSED on it. "
            "So nothing in the standard toolchain objects to a licence claim with no licence: not "
            "the backend, not the metadata validator. The unzip-and-grep assertion in release.yml "
            "is the only thing between a deleted LICENSE and a licence-less release, which is "
            "exactly why it is a step rather than a habit. Control also confirms the assertion "
            "fires: it correctly failed on both wheel and sdist.",
        ctx="hatchling via uv build, agent_build_gates 0.1.0, control copy under the scratchpad.",
        entities=["Packaging", "hatchling", "NegativeControl", "twine", "Licence"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="pattern",
        topic="revalidate-from-a-clean-clone-not-the-working-tree",
        obs="Rebuilt agent-build-gates from `git clone --depth 1` of the committed tree rather than "
            "the working directory, then ran every step release.yml runs, in order. This caught "
            "that the sdist smoke-test arm had never actually been executed: the first pass ran "
            "both console scripts from the WHEEL twice and never from the tarball. Both pass now. "
            "PATTERN: a check written into CI but never run locally is a claim, not a check. Run "
            "each CI step by hand once against a clean checkout before trusting the workflow.",
        ctx="Also verified: astral-sh/attest-action v0.0.6 tag resolves (HTTP 200), `--publish-url` "
            "is a real uv flag. Version drift noted, not changed: setup-uv v5 (latest v10.0.1), "
            "upload/download-artifact v4 (latest v7.0.1/v8.0.1); v4 artifact actions are current "
            "enough, only v3 and below are deprecated.",
        entities=["Validation", "CI", "CleanClone", "Method"],
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

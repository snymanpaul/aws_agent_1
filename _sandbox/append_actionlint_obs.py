"""Append what running a real workflow linter turned up.

The previous pass claimed the workflows were validated. They had been parsed as YAML,
which is a different and much weaker statement.
"""

import json
import pathlib

LOG = pathlib.Path(__file__).resolve().parent.parent / ".claude/learnings/observations.jsonl"
TS = "2026-08-27T03:00:00Z"

ENTRIES = [
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="mistake",
        topic="claimed-yaml-valid-when-only-yaml-was-checked",
        obs="Reported release.yml as validated on the basis of `yq` parsing it. That proves the "
            "file is YAML and nothing about the GitHub Actions schema, which is the layer that "
            "would actually fail. Running the real linter (actionlint 1.7.12) took one command and "
            "found two genuine issues the yq check could never see. GENERAL FORM: naming the tool "
            "in the report would have exposed this. 'Validated' hides which layer was checked; "
            "'yq parsed it' would have invited the obvious question.",
        ctx="Challenged by Paul with one word: 'hand waving?'",
        entities=["Validation", "CI", "actionlint", "Evidence", "Mistake"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="insight",
        topic="unquoted-git-ls-files-crashes-the-gate-on-a-space",
        obs="actionlint's shellcheck pass flagged SC2046 on `uv run no-sim-check $(git ls-files "
            "'*.py')` in both repos' gates.yml. Control run rather than assumed: a file named "
            "`has space.py` makes the unquoted form crash with `FileNotFoundError: 'space.py'`, "
            "while `git ls-files -z ... | xargs -0 ...` scans it correctly. Both repos have zero "
            "such filenames right now (`git ls-files | grep -c ' '` returns 0), so it was latent, "
            "not live. Fixed anyway: a gate that breaks on a legal filename is not a gate you can "
            "point at. Verified the two forms give identical output on the current tree, 282 files "
            "scanned either way. Also caught a broken check on the way: my first attempt to count "
            "space-containing files used `... | head && echo FOUND`, and head exits 0 on empty "
            "input, so it reported SPACES FOUND in both clean repos.",
        ctx="actionlint 1.7.12 over .github/workflows/*.yml in both repos.",
        entities=["Shell", "SC2046", "Gates", "NegativeControl", "xargs"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="pattern",
        topic="floating-major-tags-are-not-universal",
        obs="Was about to pin `astral-sh/setup-uv@v10` after deciding v5 (published 2024-12-20, "
            "twenty months and five majors stale) was wrong for a credential-bearing workflow. "
            "Checked before writing it: github.com/astral-sh/setup-uv/tree/v10 returns 404, and so "
            "does v9. That repo publishes a floating v5 but not v9 or v10, so only the exact "
            "v10.0.1 resolves. Pinning @v10 would have failed at runtime with a confusing error. "
            "Also verified v10.0.1 still accepts the `enable-cache` input before bumping. Left "
            "checkout, setup-node and the artifact actions on v4: all still supported (only "
            "artifact v3 and below are deprecated), and churning five action pins I cannot execute "
            "locally is worse than leaving working ones. actionlint clean on all three workflows.",
        ctx="Curl against github.com/<repo>/tree/<ref> for each candidate ref.",
        entities=["GitHubActions", "Pinning", "Versions", "SupplyChain"],
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

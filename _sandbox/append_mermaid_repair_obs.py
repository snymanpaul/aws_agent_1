"""Append the outcome of repairing the broken mermaid diagrams.

Follow-up to the audit entries earlier the same day. The log is append-only, so the
earlier "reported, not repaired" entry stands and this records what changed after it.
"""

import json
import pathlib

LOG = pathlib.Path(__file__).resolve().parent.parent / ".claude/learnings/observations.jsonl"
TS = "2026-08-27T00:40:00Z"

ENTRIES = [
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="pattern",
        topic="mermaid-reserved-words-collide-with-participant-ids",
        obs="level-42's sequence diagram failed for a cause no amount of reading the error text "
            "gave up: the participant was named `Loop`, which collides with the `loop ... end` "
            "block keyword, and once that was renamed the next failure was `Actor`, which "
            "collides with `actor` as a participant declaration. Both are case-insensitive "
            "keyword collisions and the parser reports them as a lexical or parse error on the "
            "USE site, several lines below the declaration that caused them. Found by bisection "
            "against mmdc (bare 2-line diagram renders; add `participant Loop as ...` and it "
            "breaks), not by reading the message. FIX: rename to RL and Act, keeping the display "
            "text in the `as` alias so the rendered diagram is unchanged.",
        ctx="mermaid 11 via mmdc; 4 minimal repro files under the session scratchpad.",
        entities=["Mermaid", "SequenceDiagram", "ReservedWords", "Debugging", "Bisection"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="mistake",
        topic="225-labels-rendered-a-literal-backslash-n",
        obs="Second, larger defect class found while fixing the first, and it never failed a "
            "parse so nothing would ever have surfaced it: 225 lines across 46 tracked files use "
            "`\\n` inside a mermaid label. Verified against mmdc that `A[first\\nsecond]` renders "
            "the SVG text 'first\\nsecond' with ZERO tspan splits, while `<br/>` produces two. So "
            "every one of those labels was printing a literal backslash-n to readers, in "
            "LEARNING_PLAN.md and 15 public level docs among others. FIXED by a fence-scoped awk "
            "rewrite (_sandbox/fix_mermaid_literal_newlines.sh) that only touches lines inside a "
            "```mermaid block, because prose outside one legitimately contains \\n. 225 lines "
            "rewritten, 0 remaining, all 133 blocks render.",
        ctx="Dry-run first, then applied; 50 files changed, 240 insertions, 240 deletions.",
        entities=["Mermaid", "Docs", "Defect", "Repair", "SilentFailure"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="insight",
        topic="a-defect-class-with-no-gate-is-a-defect-class-with-no-bound",
        obs="Both mermaid defect classes had existed since the diagrams were written, across 110 "
            "files, and neither had ever been detected, because nothing in this repo had ever "
            "rendered a diagram. The parse failures were at least loud once rendered; the literal "
            "`\\n` never fails anything and would have grown without limit. Repairing without "
            "adding the gate would only reset the counter, so tools/check_mermaid.sh is now a "
            "`diagrams` job in .github/workflows/gates.yml in both repos, split from `gates` "
            "because a headless browser is a heavier failure surface than the rest of the suite. "
            "GENERAL FORM: any convention enforced only by intention accumulates violations at "
            "the rate it is applied.",
        ctx="5 parse failures + 225 literal-newline labels, all pre-existing, all now fixed and gated.",
        entities=["Gates", "CI", "Mermaid", "Regression", "Method"],
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

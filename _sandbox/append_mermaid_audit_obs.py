"""Append the mermaid-render audit findings to the append-only log.

Ran a renderer over every tracked mermaid block for the first time. Two findings: the
checker itself under-reported until fixed, and five diagrams in this repo do not parse.
"""

import json
import pathlib

LOG = pathlib.Path(__file__).resolve().parent.parent / ".claude/learnings/observations.jsonl"
TS = "2026-08-26T23:55:00Z"

ENTRIES = [
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="mistake",
        topic="my-checker-silently-skipped-64-percent-of-its-input",
        obs="Wrote a mermaid validator that extracts each ```mermaid block to a temp file and "
            "renders it with mmdc. It reported '12 blocks, 0 failed' and looked green. It was "
            "checking 48 of 133 blocks here. Cause: temp names were built with `tr '/' '_'`, so "
            "a path under a dot-directory (.claude/learnings/reflections/...) produced a "
            "LEADING-DOT filename, and the `\"$TMP\"/*.mmd` glob does not match dotfiles. Every "
            "one of the 97 reflections was skipped. FIX: prefix every temp name (blk_), "
            "enumerate with `find` not a glob, AND reconcile extracted-count against fence-count "
            "with a hard failure on mismatch. LESSON: a checker that under-reports is worse than "
            "no checker, because it converts an unknown into a false green. Any extractor needs "
            "a count reconciliation, not just a pass/fail.",
        ctx="Discovered when 110 files were known to contain fences but only 48 blocks rendered.",
        entities=["Tooling", "Validation", "FalseGreen", "Mermaid", "Mistake"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="insight",
        topic="five-tracked-mermaid-diagrams-do-not-parse",
        obs="First render of all 133 tracked mermaid blocks: 5 fail. "
            "docs/levels/L46-hybrid-llm-deterministic-systems-4-itera.md block 1 (Parse error "
            "line 5, 'got SQS', a bracket-in-label problem), and blocks in the level-10, "
            "level-34, level-42 and level-76 reflections (lexical errors on lines 8/9 plus a "
            "LINK_ID parse error). These render as an error box for any reader, and L46 is "
            "linked from LEARNING_PLAN so it is public-facing. Pre-existing, none authored in "
            "this session. NOT fixed here: reported rather than silently repaired, because four "
            "of the five are in the historical reflection record. The repo has 110 markdown "
            "files carrying diagrams and had never rendered one in CI.",
        ctx="_sandbox check via mmdc (@mermaid-js/mermaid-cli, node v22.16.0), 2026-08-26.",
        entities=["Mermaid", "Docs", "Defect", "OpenItem", "L46"],
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

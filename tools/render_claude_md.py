"""A2: render CLAUDE.md's rule section from the promoted observations, and gate the result.

Before this, a promotion was a hand edit of the whole file and a removal was a deletion with
no record. Both lose in the same direction: the detail and the incident behind a rule go
first. Here the promoted subset of `observations.jsonl` is the source and the block between
the markers in `CLAUDE.md` is a view of it, so a rule carries the ids it came from and the
scar tissue is a lookup rather than a sentence someone has to keep retyping.

The line budget stays. Detail that does not fit moves into the store and stays retrievable,
which is the part that used to be deleted. Citations ride on the heading line so the rendered
block costs no extra lines.

    uv run python tools/render_claude_md.py            # print the block
    uv run python tools/render_claude_md.py --write    # rewrite CLAUDE.md between the markers
    uv run python tools/render_claude_md.py --check    # CI: fail on a hand edit inside it

A promotion is appended by a named script (see `_sandbox/promote_claude_md_rules.py`), never
by editing the log. A rule is withdrawn by appending an entry that supersedes it, so the
withdrawal is a record rather than a deletion.
"""

from __future__ import annotations

import difflib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG = ROOT / ".claude" / "learnings" / "observations.jsonl"
CLAUDE_MD = ROOT / "CLAUDE.md"

BEGIN = "<!-- BEGIN GENERATED: critical-rules -->"
END = "<!-- END GENERATED: critical-rules -->"
HEADER = ("<!-- Rendered from .claude/learnings/observations.jsonl by "
          "tools/render_claude_md.py. Do not hand-edit inside this block: CI re-renders it "
          "and compares. Each heading carries the observation ids the rule came from. -->")


def promoted_rules() -> list[dict]:
    """Every promoted rule entry, in id order, minus any a later entry supersedes."""
    entries = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    superseded = {e["supersedes"] for e in entries if e.get("supersedes")}
    return [e for e in entries
            if e.get("status") == "promoted" and e.get("cat") == "rule"
            and e["id"] not in superseded]


def render() -> str:
    lines = [BEGIN, HEADER, ""]
    for rule in promoted_rules():
        cites = ", ".join(rule.get("cites", []))
        lines.append(f"### {rule['rule_title']}  ({cites})")
        lines.append(rule["rule_body"])
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def split(text: str) -> tuple[str, str, str]:
    """(before, current block, after). Raises when the markers are missing or out of order."""
    if BEGIN not in text or END not in text:
        raise SystemExit(
            f"{CLAUDE_MD.name} has no generated block. Add these two markers around the rule "
            f"section:\n  {BEGIN}\n  {END}")
    head, _, rest = text.partition(BEGIN)
    block, _, tail = rest.partition(END)
    return head, BEGIN + block + END, tail


def main(argv: list[str]) -> int:
    fresh = render()
    n_rules = len(promoted_rules())

    if "--write" in argv:
        head, _, tail = split(CLAUDE_MD.read_text(encoding="utf-8"))
        CLAUDE_MD.write_text(head + fresh + tail, encoding="utf-8")
        print(f"render_claude_md: wrote {n_rules} rule(s) into {CLAUDE_MD.name}")
        return 0

    if "--check" in argv:
        _, current, _ = split(CLAUDE_MD.read_text(encoding="utf-8"))
        if current == fresh:
            print(f"render_claude_md: {CLAUDE_MD.name} matches a fresh render "
                  f"({n_rules} rule(s), every one citing at least one observation).")
            return 0
        print(f"BLOCKED: the generated block in {CLAUDE_MD.name} is not what the store renders.")
        for line in difflib.unified_diff(current.splitlines(), fresh.splitlines(),
                                         "CLAUDE.md", "rendered", lineterm="", n=1):
            print("  " + line)
        print("\nEdit the promoted observation and re-render, do not edit the block:")
        print("  uv run python tools/render_claude_md.py --write")
        return 1

    print(fresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

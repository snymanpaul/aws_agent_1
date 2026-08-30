"""A2: move the eight Critical Non-Obvious Rules into the observation store.

Until now a rule lived only in `CLAUDE.md`, and the run that produced it lived only in
`observations.jsonl`, with no link either way. Removing a rule left no record, and rewriting
the file whole is the one update pattern measured to lose accumulated detail.

This appends one `cat: "rule"` entry per rule, carrying:

    rule_title  the heading, unchanged
    rule_body   the body, read from CLAUDE.md rather than retyped, so the first render is
                a zero-diff and nothing is lost in transcription
    cites       the observation ids the rule came from, found by searching the log
    report      A6's evidence link. `incident:<ids>` for a rule adopted from a failure that
                is already in the log; `run:<path>` once a measured run justifies it.

The cites below were each read out of the log, not inferred. The eight ids under Probe First
are the eight L33 failures the rule's own text refers to.

    uv run python _sandbox/promote_claude_md_rules.py            # dry run
    uv run python _sandbox/promote_claude_md_rules.py --write
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.obs_log import append  # noqa: E402

CLAUDE_MD = ROOT / "CLAUDE.md"
TS = "2026-08-30T21:41:56Z"
SECTION = "## Critical Non-Obvious Rules"

# rule heading -> (observation ids the rule came from, one line saying what they are)
CITES: dict[str, tuple[list[str], str]] = {
    "Model Provider": (
        ["obs-0001", "obs-0002"],
        "L1 failed with a provider error using LiteLLMModel against the proxy."),
    "LiteLLM proxy runs on PODMAN: diagnose before declaring it \"down\"": (
        ["obs-0845", "obs-0864", "obs-0846", "obs-0725"],
        "L77 declared a running proxy dead from a docker check and a truncated podman ps."),
    "Streaming": (
        ["obs-0005"],
        "L2, on what Strands does by default."),
    "MCP Integration": (
        ["obs-0040", "obs-0042"],
        "L9, the client pattern and the prefix that avoids tool-name collisions."),
    "New AWS Service: Probe First": (
        ["obs-0341", "obs-0789", "obs-0381", "obs-0382", "obs-0383", "obs-0384",
         "obs-0385", "obs-0386", "obs-0387", "obs-0388"],
        "The eight L33 failures the rule refers to, plus the two-phase probe that ended them."),
    "AgentCore Deployment": (
        ["obs-0326", "obs-0327", "obs-0045"],
        "L27 hallucinated an entire AgentCore architecture before the real one was read."),
    "Streaming Swarm": (
        ["obs-0025", "obs-0026"],
        "L7 ping-ponged coder to reviewer four times to a FAILED status."),
    "Thread Safety": (
        ["obs-0259", "obs-0537"],
        "L19 and L46: a shared Agent corrupts state across threads."),
}


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def parse_rules(text: str) -> list[tuple[str, str]]:
    """(title, body) for every ### under the Critical Non-Obvious Rules heading."""
    start = text.index(SECTION) + len(SECTION)
    rest = text[start:]
    end = rest.index("\n## ")
    block = rest[:end]
    parts = re.split(r"^### ", block, flags=re.M)[1:]
    out = []
    for part in parts:
        title, _, body = part.partition("\n")
        out.append((title.strip(), body.strip("\n")))
    return out


def main(argv: list[str]) -> int:
    write = "--write" in argv
    rules = parse_rules(CLAUDE_MD.read_text(encoding="utf-8"))

    missing = [t for t, _ in rules if t not in CITES]
    if missing:
        print("no cites for: " + ", ".join(missing))
        print("A rule with no observation behind it cannot be promoted. Find the entry first.")
        return 1

    entries = []
    for title, body in rules:
        cites, why = CITES[title]
        entries.append(dict(
            ts=TS, level=0, cat="rule", topic=f"rule-{slug(title)}",
            obs=f"Promoted to CLAUDE.md: {title}. {why}",
            ctx="A2: CLAUDE.md's Critical Non-Obvious Rules are now rendered from this store "
                "by tools/render_claude_md.py, so a rule carries the ids it came from.",
            entities=["Rule", "CLAUDE.md", "A2"],
            status="promoted",
            rule_title=title,
            rule_body=body,
            cites=cites,
            report="incident:" + ",".join(cites),
        ))

    print(f"promote_claude_md_rules: {len(entries)} rule(s) parsed from {CLAUDE_MD.name}")
    for e in entries:
        print(f"  {e['rule_title'][:52]:<52} {len(e['rule_body'].splitlines()):>2} line(s)  "
              f"{len(e['cites'])} cite(s)")

    ids = append(entries, dry_run=not write)
    print(f"\n  {'wrote' if write else 'would write'} {ids[0]} .. {ids[-1]}")
    if not write:
        print("  dry run. Re-run with --write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

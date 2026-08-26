#!/usr/bin/env python3
"""no_sim_check.py — tripwire for faked / stubbed integrations.

Scans .py files for the exact patterns that forced this repo's rewrites (L14/L16/L26):
  - fake-success returns        e.g. return "Blueprint data prepared for ... persistence"
  - "in production this would"  deferrals that print the call instead of making it
  - substitute objects standing in for a real service
  - "simulate(d)" integrations
  - "assume-good" default returns inside except blocks (silent metric inflation)

Affirmative matches FAIL (exit 1). Lines that PROHIBIT the practice ("no mock", "never
simulate", "instead of a stub") are ignored. Escape a justified line with a trailing
`# nosim:ok` comment (use sparingly, with a reason).

Two deliberate scoping rules, both learned from a full classification of this repo's
hits (see tests/test_no_sim_check.py):

  1. Identifier-aware boundaries. Plain `\\b` stops at underscores and CamelCase humps,
     so `MockSQSQueue`, `mock_client` and `_simulate_human_response` all evaded the
     rule while their docstrings tripped it. The boundaries below break on those too.

  2. The two vocabulary rules (simulated-integration, mock-stub-fake) do not fire on
     comments or docstrings. Prose cannot fake an integration; code does. Every
     confirmed violation was a code construct: a class standing in for a service, or
     a return fabricating a result. The deferral and fake-return rules still read
     comments, because a deferral comment marks a call that was never made.

Usage:
    uv run python tools/no_sim_check.py <path> [<path> ...]
    # exit 0 = clean, exit 1 = smell found
"""

import pathlib
import re
import sys

# Boundaries that break on underscores and CamelCase humps as well as ordinary word
# edges. Scoped `(?-i:...)` keeps them case-sensitive inside otherwise-IGNORECASE
# patterns, so "MockSQSQueue" matches at the M/S hump while "mocking" does not.
_LEFT = r"(?-i:(?<![a-z0-9]))"
_RIGHT = r"(?-i:(?=[^a-z0-9]|$))"

# Only an unambiguous success flag. A bare number cannot be judged optimistic without
# knowing the metric: in this repo's pass-ratio scorers 0.0 is the floor, not an
# inflated default, and every numeric hit was a false positive.
GOOD_DEFAULTS = r"True"

# Vocabulary rules, suppressed on prose. The other rules read whole lines.
LEXICAL_RULES = {"simulated-integration", "mock-stub-fake"}

RED = [
    ("fake-success-return",
     re.compile(r"""return\s+["'][^"']*(prepared for|would be|placeholder|sample data|to persist|TODO)""", re.I)),
    ("in-production-deferral",
     re.compile(r"in production[, ]+\s*(this|it|you|we)?\s*(would|could|should|will)", re.I)),
    ("simulated-integration",
     re.compile(rf"{_LEFT}simulat(e|ed|es|ing|ion){_RIGHT}", re.I)),
    ("mock-stub-fake",
     re.compile(rf"{_LEFT}(mock(ed|s)?|stub(bed|s)?|fake(d|s)?|dummy|hard ?coded){_RIGHT}", re.I)),
]
ASSUME_GOOD = re.compile(rf"return\s+{GOOD_DEFAULTS}\b")
EXCEPT_LINE = re.compile(r"^\s*except\b.*:\s*$")

# A line that talks ABOUT the rule (prohibition) rather than doing the thing.
GUARD = re.compile(r"\b(no|not|never|avoid|don't|do not|isn't|aren't|without|instead of|rather than|"
                   r"prohibit|forbidden|must not|fail if|guardrail|anti-?sim)\b", re.I)
ALLOW = re.compile(r"#\s*nosim:ok")

TRIPLE_QUOTES = ('"""', "'''")


def strip_comment(line: str) -> str:
    """Return the line without a trailing # comment, keeping string literals.

    String contents are preserved on purpose: `return f"Mock response"` is a fake
    result, and stripping quoted text would hide it.
    """
    quote = None
    i = 0
    while i < len(line):
        char = line[i]
        if quote:
            if char == "\\":
                i += 2
                continue
            if line.startswith(quote, i):
                i += len(quote)
                quote = None
                continue
            i += 1
            continue
        if char == "#":
            return line[:i]
        if line.startswith(TRIPLE_QUOTES, i):
            quote = line[i:i + 3]
            i += 3
            continue
        if char in "\"'":
            quote = char
            i += 1
            continue
        i += 1
    return line


def scan_file(path: pathlib.Path):
    hits = []
    lines = path.read_text(errors="replace").splitlines()
    inside_block_string = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        is_prose = (
            inside_block_string
            or stripped.startswith("#")
            or stripped.startswith(TRIPLE_QUOTES)
        )
        # An odd number of triple-quote delimiters opens or closes a block string.
        if (line.count('"""') + line.count("'''")) % 2 == 1:
            inside_block_string = not inside_block_string

        if ALLOW.search(line):
            continue

        # Match against code where the line has any, otherwise the raw line, so a
        # prohibition comment stays exempt while a trailing comment cannot mask code.
        code = strip_comment(line)
        target = code if code.strip() else line
        if GUARD.search(target):
            continue

        for rule, pat in RED:
            if rule in LEXICAL_RULES and is_prose:
                continue
            if pat.search(target):
                hits.append((i, rule, stripped[:100]))

        # assume-good default return directly under an except:
        if ASSUME_GOOD.search(target):
            prev = lines[i - 2].strip() if i >= 2 else ""
            if EXCEPT_LINE.match(lines[i - 2]) if i >= 2 else False:
                hits.append((i, "assume-good-default", f"{prev} -> {stripped[:80]}"))
    return hits


def iter_py(paths):
    for p in paths:
        p = pathlib.Path(p)
        if p.is_dir():
            yield from (f for f in p.rglob("*.py") if f.name != "no_sim_check.py")
        elif p.suffix == ".py" and p.name != "no_sim_check.py":
            yield p


def main(argv):
    if not argv:
        print("usage: no_sim_check.py <path> [<path> ...]")
        return 2
    total, scanned = 0, 0
    for f in iter_py(argv):
        scanned += 1
        for ln, rule, text in scan_file(f):
            total += 1
            print(f"{f}:{ln}: [{rule}] {text}")
    print(f"\nno_sim_check: scanned {scanned} file(s), {total} simulation smell(s).")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

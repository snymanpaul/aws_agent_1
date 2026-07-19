#!/usr/bin/env python3
"""no_sim_check.py — tripwire for simulated / faked / stubbed integrations.

Scans .py files for the exact patterns that forced this repo's rewrites (L14/L16/L26):
  - fake-success returns        e.g. return "Blueprint data prepared for ... persistence"
  - "in production this would"  deferrals that print the call instead of making it
  - mock / stub / fake / dummy / hardcoded sample data
  - "simulate(d)" integrations
  - "assume-good" default returns inside except blocks (silent metric inflation)

Affirmative matches FAIL (exit 1). Lines that PROHIBIT simulation ("no mock", "never
simulate", "instead of a stub") are ignored. Escape a justified line with a trailing
`# nosim:ok` comment (use sparingly, with a reason).

Usage:
    uv run python tools/no_sim_check.py <path> [<path> ...]
    # exit 0 = clean, exit 1 = simulation smell found
"""

import pathlib
import re
import sys

GOOD_DEFAULTS = r"(1\.0|5\.0|0\.0|True|\"\"|''|\[\]|\{\})"

RED = [
    ("fake-success-return",
     re.compile(r"""return\s+["'][^"']*(prepared for|would be|placeholder|sample data|to persist|TODO)""", re.I)),
    ("in-production-deferral",
     re.compile(r"in production[, ]+\s*(this|it|you|we)?\s*(would|could|should|will)", re.I)),
    ("simulated-integration",
     re.compile(r"\bsimulat(e|ed|es|ing|ion)\b", re.I)),
    ("mock-stub-fake",
     re.compile(r"\b(mock(ed|s)?|stub(bed|s)?|fake(d|s)?|dummy|hard ?coded)\b", re.I)),
]
ASSUME_GOOD = re.compile(rf"return\s+{GOOD_DEFAULTS}\b")
EXCEPT_LINE = re.compile(r"^\s*except\b.*:\s*$")

# A line that talks ABOUT the rule (prohibition) rather than doing the thing.
GUARD = re.compile(r"\b(no|not|never|avoid|don't|do not|isn't|aren't|without|instead of|rather than|"
                   r"prohibit|forbidden|must not|fail if|guardrail|anti-?sim)\b", re.I)
ALLOW = re.compile(r"#\s*nosim:ok")


def scan_file(path: pathlib.Path):
    hits = []
    lines = path.read_text(errors="replace").splitlines()
    for i, line in enumerate(lines, 1):
        if ALLOW.search(line) or GUARD.search(line):
            continue
        for rule, pat in RED:
            if pat.search(line):
                hits.append((i, rule, line.strip()[:100]))
        # assume-good default return directly under an except:
        if ASSUME_GOOD.search(line):
            prev = lines[i - 2].strip() if i >= 2 else ""
            if EXCEPT_LINE.match(lines[i - 2]) if i >= 2 else False:
                hits.append((i, "assume-good-default", f"{prev} -> {line.strip()[:80]}"))
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

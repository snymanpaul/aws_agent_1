"""Tripwire: block AWS account info from entering .md / .py files (public repo).

Rule (user directive, 2026-07-18): NEVER include AWS account info in any markdown or python file.
This scans for the ways it leaks and exits non-zero on any hit, naming file:line.

Patterns (scoped to .md/.py, where a bare 12-digit decimal is essentially never legitimate):
  - a 12-digit AWS account id (word-bounded, all-decimal)
  - `AWSAdministratorAccess-<id>` and similar SSO profile strings
  - `sso_account_id` / `sso_account`
  - an ARN carrying a 12-digit account field

Usage:
  check-no-aws-ids <files...>     # explicit files (the pre-commit hook passes staged ones)
  check-no-aws-ids                # scan every tracked .md/.py in the current repo

Paths resolve against the caller's working directory, not against this module's location,
so it behaves the same vendored into a repo or installed from a wheel.

Install it as a git pre-commit hook so a leak cannot be committed. This repo does that in
tools/install_hooks.sh.
"""

import re
import subprocess
import sys
from pathlib import Path

# The file being scanned is skipped when it is this module: the tripwire names the
# patterns it hunts, so it would otherwise flag its own definitions.
SELF_PATH = Path(__file__).resolve()

PATTERNS = [
    (re.compile(r"(?<!\d)\d{12}(?!\d)"), "12-digit AWS account id"),
    (re.compile(r"AWSAdministratorAccess-\d{2,}", re.I), "SSO admin profile string"),
    (re.compile(r"sso[_-]account", re.I), "sso_account reference"),
    (re.compile(r"arn:aws[^\s\"']*:\d{12}:"), "ARN with account id"),
]

# Per-line escape, mirroring no_sim_check's `# nosim:ok`. A line carrying `noaws:ok`
# anywhere is skipped, so it works as a `# noaws:ok` comment in Python and as a
# `<!-- noaws:ok -->` comment in Markdown. Needed by anything that must legitimately
# contain account-shaped strings: this gate's own tests, and docs describing it.
# Use it with a reason, and never to wave through a real identifier.
ALLOW_LINE = re.compile(r"noaws:ok")

# Known-safe 12-digit literals that are NOT account info (a real account id is never in this set).
# Extend at the call site rather than editing here: scan(files, allow=ALLOW | {"..."}).
ALLOW = {
    "000000000000",   # canonical AWS placeholder account id (docs/demo)
    "798123456789",   # tracking-number literal in the L56 MCP server fixtures
}


def tracked_md_py() -> list[str]:
    """Every tracked .md/.py in the repo containing the working directory."""
    out = subprocess.run(["git", "ls-files", "*.md", "*.py"],
                         capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if l]


def scan(files: list[str], allow: set[str] | None = None) -> int:
    """Print every hit as file:line and return the count. Paths resolve against cwd."""
    allow = ALLOW if allow is None else allow
    hits = 0
    for rel in files:
        if not (rel.endswith(".md") or rel.endswith(".py")):
            continue
        p = Path(rel)
        if not p.exists():
            continue
        if p.resolve() == SELF_PATH:
            continue
        for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            if ALLOW_LINE.search(line):
                continue
            for rx, label in PATTERNS:
                m = rx.search(line)
                if not m:
                    continue
                ids = re.findall(r"(?<!\d)\d{12}(?!\d)", m.group(0))
                if ids and all(i in allow for i in ids):
                    continue  # every account-id-shaped run in the match is a known-safe literal
                print(f"{rel}:{n}: [{label}] {line.strip()[:100]}")
                hits += 1
                break
    return hits


def main(argv: list[str]) -> int:
    targets = list(argv) or tracked_md_py()
    n = scan(targets)
    if n:
        print(f"\nBLOCKED: {n} AWS-account leak(s) in .md/.py. Redact before committing.")
        return 1
    scanned = len([t for t in targets if t.endswith((".md", ".py"))])
    print(f"check_no_aws_ids: scanned {scanned} file(s), clean.")
    return 0


def cli() -> None:
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    cli()

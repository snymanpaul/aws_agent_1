"""Tripwire: block AWS account info from entering .md / .py files (public repo).

Rule (user directive, 2026-07-18): NEVER include AWS account info in any markdown or python file.
This scans for the ways it leaks and exits non-zero on any hit, naming file:line.

Patterns (scoped to .md/.py, where a bare 12-digit decimal is essentially never legitimate):
  - a 12-digit AWS account id (word-bounded, all-decimal)
  - `AWSAdministratorAccess-<id>` and similar SSO profile strings
  - `sso_account_id` / `sso_account`
  - an ARN carrying a 12-digit account field

Usage:
  uv run python tools/check_no_aws_ids.py <files...>     # explicit files (pre-commit passes staged)
  uv run python tools/check_no_aws_ids.py                # scan all tracked .md/.py

Installed as a git pre-commit hook (see tools/install_hooks.sh) so a leak cannot be committed.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATTERNS = [
    (re.compile(r"(?<!\d)\d{12}(?!\d)"), "12-digit AWS account id"),
    (re.compile(r"AWSAdministratorAccess-\d{2,}", re.I), "SSO admin profile string"),
    (re.compile(r"sso[_-]account", re.I), "sso_account reference"),
    (re.compile(r"arn:aws[^\s\"']*:\d{12}:"), "ARN with account id"),
]

# The tripwire file names the patterns it hunts; ignore its own definitions.
SELF = "tools/check_no_aws_ids.py"

# Known-safe 12-digit literals that are NOT account info (a real account id is never in this set).
ALLOW = {
    "000000000000",   # canonical AWS placeholder account id (docs/demo)
    "798123456789",   # fake FedEx tracking number in the L56 mock MCP servers
}


def tracked_md_py() -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.md", "*.py"],
                         capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if l]


def scan(files: list[str]) -> int:
    hits = 0
    for rel in files:
        if not (rel.endswith(".md") or rel.endswith(".py")):
            continue
        if rel == SELF:
            continue
        p = ROOT / rel
        if not p.exists():
            continue
        for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            for rx, label in PATTERNS:
                m = rx.search(line)
                if not m:
                    continue
                ids = re.findall(r"(?<!\d)\d{12}(?!\d)", m.group(0))
                if ids and all(i in ALLOW for i in ids):
                    continue  # every account-id-shaped run in the match is a known-safe literal
                print(f"{rel}:{n}: [{label}] {line.strip()[:100]}")
                hits += 1
                break
    return hits


if __name__ == "__main__":
    targets = sys.argv[1:] or tracked_md_py()
    n = scan(targets)
    if n:
        print(f"\nBLOCKED: {n} AWS-account leak(s) in .md/.py. Redact before committing.")
        sys.exit(1)
    print(f"check_no_aws_ids: scanned {len([t for t in targets if t.endswith(('.md','.py'))])} file(s), clean.")

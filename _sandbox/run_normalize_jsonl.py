"""
Apply normalization to observations.jsonl.

Usage:
    uv run python _sandbox/run_normalize_jsonl.py --dry-run   # preview only
    uv run python _sandbox/run_normalize_jsonl.py             # apply
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib_normalize_jsonl import normalize_file

TARGET = Path(".claude/learnings/observations.jsonl")
DRY_RUN = "--dry-run" in sys.argv

if not TARGET.exists():
    print(f"ERROR: {TARGET} not found")
    sys.exit(1)

result = normalize_file(TARGET, dry_run=DRY_RUN)

mode = "DRY RUN — no changes written" if DRY_RUN else "APPLIED"
print(f"[{mode}]")
print(f"  total lines  : {result.total_lines}")
print(f"  changed      : {result.changed}")
print(f"  skipped_multi: {result.skipped_multi}")
print()
for cat, count in sorted(result.cat_counts.items()):
    print(f"  cat={cat}: {count}")

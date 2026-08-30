"""Gate: every observation carries an id and a lifecycle, and the log stays append-only.

A1 of the continual-learning recommendations. The log was already the right shape, one
itemized entry per lesson, and was missing the fields that let anything read it back: an id
to cite, a status to move through, and a link for a corrected entry. `_sandbox/backfill_obs_ids.py`
put them on the 994 entries that predate this gate; this keeps them there.

A requirement nothing verifies looks satisfied. That is this repo's own recurring finding:
the mermaid audit found 5 unparseable diagrams and 225 literal `\\n` labels that had been
"required" for months, and the reflection template's ASCII mirror was mandatory in prose and
absent in practice until something rendered it.

Enforced:

    id           obs-NNNN, unique, and strictly increasing down the file, which is what
                 makes "append-only" checkable rather than asserted
    status       one of raw / proposed / promoted / parked / retired
    supersedes   absent, null, or an id that EXISTS in the log, and never itself
    fields       ts, repo, level, cat, topic, obs, ctx, entities present on every entry
    values       obs non-empty, cat from the known set

    LEGACY WINDOW. 18 entries at or below obs-0208 carry a null cat, topic or ctx because
    the capture that produced them had no such field. They were not backfilled with invented
    text. The window is frozen at that id: any entry after it must carry all three.

It does NOT check that a promoted entry cites a report. That is A6, in check_promotions.py,
and it belongs with the promotion path.

    uv run python tools/check_obs_schema.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG = ROOT / ".claude" / "learnings" / "observations.jsonl"

ID = re.compile(r"^obs-\d{4,}$")
STATUSES = {"raw", "proposed", "promoted", "parked", "retired"}
# "gotcha" is one L22 entry from a capture that used its own vocabulary; "rule" is what a
# promotion entry carries. Both are real values in the log, so both are named here.
CATS = {"mistake", "pattern", "insight", "question", "gotcha", "rule"}
REQUIRED = ("id", "status", "ts", "repo", "level", "cat", "topic", "obs", "ctx", "entities")
LEGACY_WINDOW = "obs-0208"


def load(log: pathlib.Path) -> tuple[list[tuple[int, dict]], list[str]]:
    entries, problems = [], []
    for n, line in enumerate(log.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append((n, json.loads(line)))
        except json.JSONDecodeError as exc:
            problems.append(f"line {n}: not valid JSON: {exc}")
    return entries, problems


def main(argv: list[str] | None = None) -> int:
    log = pathlib.Path(argv[0]) if argv else LOG
    entries, problems = load(log)

    for n, e in entries:
        for field in REQUIRED:
            if field not in e:
                problems.append(f"line {n}: missing '{field}'")
        obs_id = str(e.get("id", ""))
        if not ID.match(obs_id):
            problems.append(f"line {n}: id {e.get('id')!r} is not obs-NNNN")
        if e.get("status") not in STATUSES:
            problems.append(f"line {n}: status {e.get('status')!r} not in {sorted(STATUSES)}")
        if e.get("cat") is not None and e["cat"] not in CATS:
            problems.append(f"line {n}: cat {e['cat']!r} not in {sorted(CATS)}")
        if not str(e.get("obs") or "").strip():
            problems.append(f"line {n}: empty 'obs'")
        if obs_id > LEGACY_WINDOW:
            for field in ("cat", "topic", "ctx"):
                if e.get(field) is None:
                    problems.append(
                        f"line {n} ({obs_id}): '{field}' is null outside the legacy window "
                        f"(<= {LEGACY_WINDOW}). Write the value; do not widen the window.")

    ids = [str(e.get("id")) for _, e in entries]
    for dupe in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"duplicate id {dupe}")
    if ids != sorted(ids):
        problems.append("ids are not in increasing order: the log was reordered or inserted into")

    known = set(ids)
    for n, e in entries:
        sup = e.get("supersedes")
        if sup is None:
            continue
        if sup not in known:
            problems.append(f"line {n}: supersedes {sup!r}, which is not in the log")
        if sup == e.get("id"):
            problems.append(f"line {n}: supersedes itself")

    statuses: dict[str, int] = {}
    for _, e in entries:
        key = str(e.get("status"))
        statuses[key] = statuses.get(key, 0) + 1
    legacy = sum(1 for _, e in entries
                 if any(e.get(f) is None for f in ("cat", "topic", "ctx")))

    print(f"check_obs_schema: {len(entries)} observation(s), {len(problems)} problem(s).")
    print("  status: " + "  ".join(f"{k}={v}" for k, v in sorted(statuses.items())))
    print(f"  supersedes links: {sum(1 for _, e in entries if e.get('supersedes'))}")
    print(f"  legacy entries with a null cat/topic/ctx: {legacy} (all <= {LEGACY_WINDOW})")
    for p in problems:
        print(f"  {p}")
    if problems:
        print("\nAppend new entries with a named script in _sandbox/ using tools/obs_log.py,")
        print("which assigns the next id and the required fields.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

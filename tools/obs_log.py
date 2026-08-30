"""Append to the observation log with an id, a status and the required fields.

A1. Every append script in `_sandbox/` writes the same six fields by hand today, which is
how the log accumulated five key shapes over 994 entries. This is the one place that knows
the schema, so a change to it happens once rather than in every future append script.

    from tools.obs_log import append, next_id

    append([
        dict(ts="2026-08-30T12:00:00Z", level=0, cat="insight", topic="short-slug",
             obs="what was observed", ctx="what triggered it", entities=["Thing"]),
    ])

`id`, `status` and `supersedes` are assigned here: ids continue from the end of the log, the
status defaults to `raw`, and supersedes defaults to null. Pass `status=` or `supersedes=`
explicitly to override, and `tools/check_obs_schema.py` will check the result.

A promotion entry (A2/A6) carries more: `cat="rule"`, `status="promoted"`, `rule_title`,
`rule_body`, `derived_from` and `report`. Those extras ride along as ordinary keys and are
checked by `tools/check_promotions.py`.
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG = ROOT / ".claude" / "learnings" / "observations.jsonl"

REPO = "aws_agent_1"
REQUIRED = ("ts", "level", "cat", "topic", "obs", "ctx", "entities")
LEAD = ("id", "status", "supersedes")
CANONICAL = ("ts", "repo", "level", "cat", "topic", "obs", "ctx", "entities")


def read(path: pathlib.Path = LOG) -> list[dict]:
    """Every entry in the log, in file order."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def next_id(path: pathlib.Path = LOG) -> str:
    """The id after the highest one in the log, keeping the existing width."""
    ids = [e["id"] for e in read(path) if "id" in e]
    if not ids:
        return "obs-0001"
    last = max(ids)
    digits = len(last.split("-")[1])
    return f"obs-{int(last.split('-')[1]) + 1:0{digits}d}"


def _shape(entry: dict, obs_id: str) -> dict:
    out = {"id": obs_id,
           "status": entry.get("status", "raw"),
           "supersedes": entry.get("supersedes")}
    for key in CANONICAL:
        out[key] = REPO if key == "repo" else entry.get(key)
    for key in sorted(k for k in entry if k not in CANONICAL and k not in LEAD):
        out[key] = entry[key]
    return out


def append(entries: list[dict], path: pathlib.Path = LOG, dry_run: bool = False) -> list[str]:
    """Append entries, assigning ids. Returns the ids written. Refuses an incomplete entry."""
    missing = [(i, f) for i, e in enumerate(entries) for f in REQUIRED
               if e.get(f) is None and f != "ctx"]
    if missing:
        raise ValueError(f"entries missing required fields: {missing}")

    start = int(next_id(path).split("-")[1])
    digits = len(next_id(path).split("-")[1])
    shaped = [_shape(e, f"obs-{start + i:0{digits}d}") for i, e in enumerate(entries)]
    text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in shaped)
    if not dry_run:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(text)
    return [e["id"] for e in shaped]

"""A1: give every observation an id and a lifecycle, in place, losslessly.

From `docs/recommendations-for-the-experiment-repos.md` in the continual-learning repo. The
log was already the right shape, one itemized entry per lesson. It was missing the three
fields that let anything read it back:

    id          a stable handle a rule, a reflection and a test can all cite
    status      raw / proposed / promoted / parked / retired
    supersedes  how a corrected entry replaces an earlier one without deleting it

This script also unifies the five key shapes the log accumulated over 994 entries. Every
change here is a RENAME or a DEFAULT for an absent field. Nothing is invented:

    timestamp -> ts          observation -> obs        content -> obs
    type      -> cat         tags        -> entities

    repo      filled with "aws_agent_1" where absent. Safe: all 898 entries that carry the
              field already say aws_agent_1, and this is that repo's own log.
    entities  filled with [] where absent, because absent and empty mean the same thing.
    ctx       filled with null, NOT with a sentence. 18 legacy entries never captured it and
              writing one now would be fabricating provenance.
    cat       left null on the 8 entries whose capture had no category field at all.
              Classifying them from their text now would be a judgement recorded as data.
    "gotcha"  kept verbatim on the one L22 entry that used it. Mapping it to mistake or
              insight would be the same judgement in different clothes.

Run:
    uv run python _sandbox/backfill_obs_ids.py            # dry run, prints the plan
    uv run python _sandbox/backfill_obs_ids.py --write    # rewrites the log in place

Refuses to write unless every invariant below holds:
    same number of entries, same multiset of observation texts, same multiset of levels,
    same cat distribution after the rename, and every id unique and in file order.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG = ROOT / ".claude" / "learnings" / "observations.jsonl"
BACKUP = LOG.with_suffix(".jsonl.pre-a1.bak")

RENAMES = {"timestamp": "ts", "observation": "obs", "content": "obs", "type": "cat",
           "tags": "entities"}
# canonical name -> every key that can already be holding that value
SOURCES: dict[str, tuple[str, ...]] = {}
for _legacy, _canon in RENAMES.items():
    SOURCES[_canon] = SOURCES.get(_canon, ()) + (_legacy,)
# Written first so a human reading a raw line sees the handle before the payload.
LEAD = ("id", "status", "supersedes")
CANONICAL = ("ts", "repo", "level", "cat", "topic", "obs", "ctx", "entities")


def canonicalise(entry: dict) -> dict:
    """Rename legacy keys and fill absent fields. Never overwrites a value that exists."""
    out = {}
    for key, value in entry.items():
        out[RENAMES.get(key, key)] = value
    out.setdefault("repo", "aws_agent_1")
    out.setdefault("entities", [])
    out.setdefault("ctx", None)
    out.setdefault("cat", None)
    return out


def ordered(entry: dict, obs_id: str) -> dict:
    """Stable key order: handle, then the canonical fields, then anything else it carried."""
    out = {"id": obs_id, "status": "raw", "supersedes": None}
    for key in CANONICAL:
        out[key] = entry.get(key)
    for key in sorted(k for k in entry if k not in CANONICAL and k not in LEAD):
        out[key] = entry[key]
    return out


def load(path: pathlib.Path) -> list[dict]:
    entries = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"line {n}: not valid JSON: {exc}")
    return entries


def census(entries: list[dict]) -> dict:
    """The properties that must survive the rewrite, read from whichever key holds them."""
    texts, cats, levels = [], {}, []
    for e in entries:
        texts.append(e.get("obs") or e.get("observation") or e.get("content") or "")
        cat = e.get("cat") or e.get("type")
        cats[cat] = cats.get(cat, 0) + 1
        levels.append(e.get("level"))
    return {"n": len(entries), "texts": sorted(texts), "cats": cats, "levels": sorted(
        levels, key=lambda v: (v is None, v))}


def main(argv: list[str]) -> int:
    write = "--write" in argv
    before = load(LOG)
    width = max(4, len(str(len(before))))

    after = [ordered(canonicalise(e), f"obs-{i:0{width}d}")
             for i, e in enumerate(before, 1)]

    a, b = census(before), census(after)
    problems = []
    if a["n"] != b["n"]:
        problems.append(f"entry count changed: {a['n']} -> {b['n']}")
    if a["texts"] != b["texts"]:
        problems.append("observation texts changed")
    if a["levels"] != b["levels"]:
        problems.append("level values changed")
    if a["cats"] != b["cats"]:
        problems.append(f"cat distribution changed: {a['cats']} -> {b['cats']}")
    ids = [e["id"] for e in after]
    if len(set(ids)) != len(ids):
        problems.append("ids are not unique")

    shapes_before = {tuple(sorted(e)) for e in before}
    print(f"backfill_obs_ids: {len(before)} entries, {len(shapes_before)} distinct key shape(s) "
          f"-> 1")
    print(f"  ids {ids[0]} .. {ids[-1]}, all status=raw, all supersedes=null")
    print("  cat distribution: " + "  ".join(
        f"{k}={v}" for k, v in sorted(a["cats"].items(), key=lambda kv: str(kv[0]))))
    filled = {f: sum(1 for e in before
                     if not any(k in e for k in (f, *SOURCES.get(f, ()))))
              for f in ("repo", "entities", "ctx", "cat")}
    print("  filled where absent: " + "  ".join(f"{k}={v}" for k, v in filled.items()))
    for p in problems:
        print(f"  INVARIANT BROKEN: {p}")
    if problems:
        return 1

    if not write:
        print("\n  dry run. Re-run with --write to rewrite the log in place.")
        return 0

    shutil.copy2(LOG, BACKUP)
    LOG.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in after),
                   encoding="utf-8")
    print(f"\n  backup written to {BACKUP.name}")
    print(f"  rewrote {LOG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

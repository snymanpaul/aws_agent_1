"""
Normalize JSONL files to compact JSON (no spaces after separators).

Public API
----------
normalize_line(raw)  -> str          Pure function: normalize one raw line string.
normalize_file(path, dry_run=False)  -> NormalizeResult   Normalize a file in-place.

Design contracts
----------------
- normalize_line is pure and side-effect-free.
- normalize_line is idempotent: normalize_line(normalize_line(x)) == normalize_line(x).
- normalize_line never changes the parsed content of a line, only its formatting.
- Lines that cannot be parsed as exactly one JSON object are returned unchanged.
  This includes: empty lines, whitespace-only lines, invalid JSON, and multi-object
  lines (the known line-263 double-entry defect in observations.jsonl).
- normalize_file verifies that entry count, cat distribution, and topic set are
  identical before and after transformation. It raises ValueError and does NOT write
  if any invariant is violated.
"""

import json
from pathlib import Path
from typing import NamedTuple


class NormalizeResult(NamedTuple):
    total_lines: int
    changed: int
    skipped_multi: int   # lines with >1 JSON object — left untouched
    cat_counts: dict      # {"question": N, "insight": N, ...}
    topic_set: frozenset  # all topic values seen


def normalize_line(raw: str) -> str:
    """
    Return raw as compact JSON + newline, or raw unchanged.

    Unchanged cases:
      - empty / whitespace-only
      - invalid JSON
      - more than one JSON object on the line
    """
    if not raw.strip():
        return raw

    stripped = raw.rstrip("\n\r")
    decoder = json.JSONDecoder()

    try:
        obj, end_pos = decoder.raw_decode(stripped)
    except json.JSONDecodeError:
        return raw  # unparseable — leave as-is

    # Anything after the first object?
    tail = stripped[end_pos:].strip()
    if tail:
        return raw  # multi-object line — leave as-is

    compact = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    return compact + "\n"


def _parse_all_entries(lines: list) -> list:
    """
    Parse every JSON object from every line.
    Multi-object lines contribute multiple entries.
    Invalid or empty lines contribute nothing.
    """
    entries = []
    decoder = json.JSONDecoder()
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        pos = 0
        while pos < len(stripped):
            try:
                obj, new_pos = decoder.raw_decode(stripped, pos)
                entries.append(obj)
                pos = new_pos
                # skip whitespace between objects on the same line
                while pos < len(stripped) and stripped[pos] in " \t":
                    pos += 1
            except json.JSONDecodeError:
                break
    return entries


def normalize_file(path: Path, dry_run: bool = False) -> NormalizeResult:
    """
    Normalize every line in the JSONL file to compact JSON.

    Raises ValueError before writing if:
      - total entry count changes
      - cat distribution changes
      - topic set changes

    When dry_run=True: computes and returns result without writing.
    """
    lines_in = path.read_text().splitlines(keepends=True)

    lines_out = []
    changed = 0
    skipped_multi = 0

    for raw in lines_in:
        normalized = normalize_line(raw)
        if normalized == raw:
            # Check if this was a multi-object skip (not just already-compact)
            stripped = raw.rstrip("\n\r").strip()
            if stripped:
                decoder = json.JSONDecoder()
                try:
                    _, end_pos = decoder.raw_decode(stripped)
                    tail = stripped[end_pos:].strip()
                    if tail:
                        skipped_multi += 1
                except json.JSONDecodeError:
                    pass
        else:
            changed += 1
        lines_out.append(normalized)

    # --- Verification ---
    entries_before = _parse_all_entries(lines_in)
    entries_after = _parse_all_entries(lines_out)

    if len(entries_before) != len(entries_after):
        raise ValueError(
            f"Entry count changed: {len(entries_before)} before → {len(entries_after)} after"
        )

    def cat_counts(entries):
        counts = {}
        for e in entries:
            c = e.get("cat", "?")
            counts[c] = counts.get(c, 0) + 1
        return counts

    cats_before = cat_counts(entries_before)
    cats_after = cat_counts(entries_after)
    if cats_before != cats_after:
        raise ValueError(f"Cat distribution changed:\n  before: {cats_before}\n  after:  {cats_after}")

    topics_before = frozenset(e.get("topic", "") for e in entries_before)
    topics_after = frozenset(e.get("topic", "") for e in entries_after)
    if topics_before != topics_after:
        added = topics_after - topics_before
        removed = topics_before - topics_after
        raise ValueError(f"Topic set changed. Added: {added}  Removed: {removed}")

    if not dry_run:
        path.write_text("".join(lines_out))

    return NormalizeResult(
        total_lines=len(lines_out),
        changed=changed,
        skipped_multi=skipped_multi,
        cat_counts=cats_after,
        topic_set=topics_after,
    )

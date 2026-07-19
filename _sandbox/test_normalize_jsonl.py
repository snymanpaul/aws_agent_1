"""
Tests for lib_normalize_jsonl.

Covers:
  normalize_line — unit tests (positive, negative, edge cases)
  normalize_file — integration tests (positive, negative, idempotency, dry_run)

Run:
  uv run pytest _sandbox/test_normalize_jsonl.py -v
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from lib_normalize_jsonl import NormalizeResult, _parse_all_entries, normalize_file, normalize_line


# ---------------------------------------------------------------------------
# normalize_line — positive tests (SHOULD compact)
# ---------------------------------------------------------------------------


def test_spaced_separators_compacted():
    """Standard json.dumps output with spaces is compacted."""
    raw = '{"cat": "question", "topic": "foo", "obs": "bar"}\n'
    result = normalize_line(raw)
    assert result == '{"cat":"question","topic":"foo","obs":"bar"}\n'
    assert result != raw


def test_spaced_insight_compacted():
    """Insight entries with spaces are compacted."""
    raw = '{"cat": "insight", "ts": "2026-03-19T00:00:00Z", "level": 34}\n'
    result = normalize_line(raw)
    assert '"cat":"insight"' in result
    assert '"cat": "insight"' not in result
    assert json.loads(result) == json.loads(raw)  # content identical


def test_deeply_spaced_compacted():
    """Extra spaces around all separators are removed."""
    raw = '{ "a" : 1 , "b" : 2 }\n'
    result = normalize_line(raw)
    assert result == '{"a":1,"b":2}\n'


# ---------------------------------------------------------------------------
# normalize_line — negative tests (must NOT change)
# ---------------------------------------------------------------------------


def test_already_compact_unchanged():
    """Lines already in compact format are returned unchanged (byte-identical)."""
    raw = '{"cat":"question","topic":"foo","obs":"bar"}\n'
    assert normalize_line(raw) is raw or normalize_line(raw) == raw
    # Idempotency: calling again produces same output
    assert normalize_line(raw) == raw


def test_multi_object_line_unchanged():
    """A line with two concatenated JSON objects is left untouched."""
    obj1 = '{"cat":"insight","topic":"foo","ts":"t1"}'
    obj2 = '{"cat":"pattern","topic":"bar","ts":"t2"}'
    raw = obj1 + obj2 + "\n"
    assert normalize_line(raw) == raw


def test_empty_line_unchanged():
    raw = "\n"
    assert normalize_line(raw) == "\n"


def test_whitespace_only_line_unchanged():
    raw = "   \n"
    assert normalize_line(raw) == "   \n"


def test_invalid_json_unchanged():
    raw = "not valid json at all\n"
    assert normalize_line(raw) == raw


def test_partial_json_unchanged():
    raw = '{"cat": "question"\n'  # missing closing brace
    assert normalize_line(raw) == raw


# ---------------------------------------------------------------------------
# normalize_line — content preservation
# ---------------------------------------------------------------------------


def test_obs_containing_json_syntax_preserved():
    """
    String values that happen to contain 'cat: question' text are not corrupted.
    The outer structure is compacted; the inner string content is preserved exactly.
    """
    inner = 'text with "cat": "question" inside it'
    obj = {"cat": "question", "obs": inner}
    raw = json.dumps(obj, indent=2) + "\n"  # pretty-printed input
    result = normalize_line(raw)
    parsed = json.loads(result)
    assert parsed["cat"] == "question"
    assert parsed["obs"] == inner  # inner string unchanged


def test_unicode_preserved():
    """Unicode characters in values survive the round-trip."""
    raw = '{"cat": "insight", "obs": "café naïve résumé"}\n'
    result = normalize_line(raw)
    parsed = json.loads(result)
    assert parsed["obs"] == "café naïve résumé"


def test_newlines_in_values_preserved():
    """Escaped newlines inside string values survive."""
    obj = {"cat": "pattern", "obs": "line1\nline2\ttabbed"}
    raw = json.dumps(obj) + "\n"
    result = normalize_line(raw)
    assert json.loads(result) == obj


# ---------------------------------------------------------------------------
# normalize_line — idempotency
# ---------------------------------------------------------------------------


def test_idempotent_on_spaced_input():
    raw = '{"cat": "question", "topic": "foo"}\n'
    once = normalize_line(raw)
    twice = normalize_line(once)
    assert once == twice


def test_idempotent_on_compact_input():
    raw = '{"cat":"question","topic":"foo"}\n'
    assert normalize_line(normalize_line(raw)) == raw


# ---------------------------------------------------------------------------
# normalize_file — integration tests
# ---------------------------------------------------------------------------


def _write_tmp(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def test_file_compacts_spaced_lines():
    """normalize_file fixes spaced lines and reports correct changed count."""
    content = (
        '{"cat":"question","topic":"alpha","ts":"t1"}\n'   # compact — no change
        '{"cat": "insight", "topic": "beta", "ts": "t2"}\n'  # spaced — change
        '{"cat":"pattern","topic":"gamma","ts":"t3"}\n'   # compact — no change
    )
    tmp = _write_tmp(content)
    try:
        result = normalize_file(tmp)
        lines = tmp.read_text().splitlines(keepends=True)
        assert result.changed == 1
        assert '"cat":"insight"' in lines[1]
        assert '"cat": "insight"' not in lines[1]
        assert result.cat_counts == {"question": 1, "insight": 1, "pattern": 1}
    finally:
        tmp.unlink()


def test_file_preserves_multi_object_line():
    """Lines with two JSON objects are left unchanged; skipped_multi is counted."""
    obj1 = '{"cat":"insight","topic":"foo","ts":"t1"}'
    obj2 = '{"cat":"pattern","topic":"bar","ts":"t2"}'
    multi_line = obj1 + obj2
    content = (
        '{"cat": "question", "topic": "alpha", "ts": "t3"}\n'
        + multi_line + "\n"
        + '{"cat":"mistake","topic":"gamma","ts":"t4"}\n'
    )
    tmp = _write_tmp(content)
    try:
        result = normalize_file(tmp)
        lines = tmp.read_text().splitlines(keepends=True)
        assert lines[1].rstrip("\n") == multi_line  # byte-identical
        assert result.skipped_multi == 1
    finally:
        tmp.unlink()


def test_file_idempotent():
    """Second run on an already-normalized file reports zero changes."""
    content = (
        '{"cat": "question", "topic": "alpha", "ts": "t1"}\n'
        '{"cat": "insight", "topic": "beta", "ts": "t2"}\n'
    )
    tmp = _write_tmp(content)
    try:
        result1 = normalize_file(tmp)
        result2 = normalize_file(tmp)
        assert result1.changed > 0
        assert result2.changed == 0
    finally:
        tmp.unlink()


def test_file_dry_run_does_not_write():
    """dry_run=True reports what would change without modifying the file."""
    content = '{"cat": "question", "topic": "alpha", "ts": "t1"}\n'
    tmp = _write_tmp(content)
    try:
        result = normalize_file(tmp, dry_run=True)
        assert result.changed == 1
        assert tmp.read_text() == content  # file untouched
    finally:
        tmp.unlink()


def test_file_cat_count_correct():
    """cat_counts in result reflects the actual distribution."""
    content = (
        '{"cat":"question","topic":"a","ts":"t1"}\n'
        '{"cat":"question","topic":"b","ts":"t2"}\n'
        '{"cat":"insight","topic":"c","ts":"t3"}\n'
    )
    tmp = _write_tmp(content)
    try:
        result = normalize_file(tmp)
        assert result.cat_counts["question"] == 2
        assert result.cat_counts["insight"] == 1
    finally:
        tmp.unlink()


def test_file_empty_lines_preserved():
    """Empty lines within the file are kept."""
    content = (
        '{"cat":"question","topic":"a","ts":"t1"}\n'
        "\n"
        '{"cat":"insight","topic":"b","ts":"t2"}\n'
    )
    tmp = _write_tmp(content)
    try:
        normalize_file(tmp)
        result_content = tmp.read_text()
        lines = result_content.splitlines(keepends=True)
        assert lines[1] == "\n"  # empty line preserved
    finally:
        tmp.unlink()


# ---------------------------------------------------------------------------
# normalize_file — invariant-violation tests (must raise, must NOT write)
# ---------------------------------------------------------------------------


def test_file_raises_if_entry_count_would_change(monkeypatch):
    """
    If normalization would somehow change the entry count, ValueError is raised
    and the file is not written.

    We simulate this by monkey-patching _parse_all_entries to return different
    counts for lines_in vs lines_out.
    """
    import lib_normalize_jsonl as lib

    call_count = [0]
    original = lib._parse_all_entries

    def fake_parse(lines):
        call_count[0] += 1
        result = original(lines)
        # Second call (lines_out) returns one fewer entry
        if call_count[0] == 2:
            return result[:-1]
        return result

    content = '{"cat":"question","topic":"a","ts":"t1"}\n'
    tmp = _write_tmp(content)
    try:
        monkeypatch.setattr(lib, "_parse_all_entries", fake_parse)
        with pytest.raises(ValueError, match="Entry count changed"):
            normalize_file(tmp)
        # File must not have been written
        assert tmp.read_text() == content
    finally:
        tmp.unlink()

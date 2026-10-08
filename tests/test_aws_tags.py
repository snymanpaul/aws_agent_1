"""The tag set the Resource Group selects on. If `owner` or `project` drift, the group
silently stops listing this repo's resources, so the selector values are pinned here."""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.aws_tags import lesson_tags, tag_list  # noqa: E402


def test_selector_values_are_pinned():
    tags = lesson_tags("L75", "18_agentcore_config/config_bundles.py finally")
    assert tags == {
        "owner": "paul",
        "project": "aws_agent_1",
        "lesson": "L75",
        "teardown": "18_agentcore_config/config_bundles.py finally",
    }


@pytest.mark.parametrize("lesson, teardown", [("", "x"), ("L1", "")])
def test_missing_lesson_or_teardown_is_rejected(lesson, teardown):
    with pytest.raises(ValueError):
        lesson_tags(lesson, teardown)


def test_tag_list_shapes():
    tags = {"owner": "paul", "lesson": "L1"}
    assert tag_list(tags) == [{"Key": "owner", "Value": "paul"}, {"Key": "lesson", "Value": "L1"}]
    assert tag_list(tags, key="key", value="value") == [
        {"key": "owner", "value": "paul"},
        {"key": "lesson", "value": "L1"},
    ]

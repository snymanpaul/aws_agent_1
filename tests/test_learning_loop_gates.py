"""Controls for the three gates that hold the learning loop together.

A gate nothing tests decays, which is this repo's own recurring finding rather than a
general worry: a required ASCII mirror went missing from reflections nobody rendered, and 5
unparseable mermaid diagrams sat in tracked docs for months under a rule that said they must
parse. These run the gates against fixture logs, so a change that quietly stops them from
catching anything fails here.

Every case is a NEGATIVE control: it feeds the gate a log that must be rejected. The positive
control at the end feeds the real log, which must pass.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import check_obs_schema, check_promotions, render_claude_md  # noqa: E402

REAL_LOG = ROOT / ".claude" / "learnings" / "observations.jsonl"


def write_log(tmp_path: pathlib.Path, entries: list[dict]) -> str:
    path = tmp_path / "observations.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return str(path)


def entry(**over) -> dict:
    base = dict(id="obs-0300", status="raw", supersedes=None, ts="2026-08-30T00:00:00Z",
                repo="aws_agent_1", level=1, cat="mistake", topic="a-slug",
                obs="what happened", ctx="what triggered it", entities=["Thing"])
    base.update(over)
    return base


class TestObservationSchemaGate:
    def test_a_clean_log_passes(self, tmp_path, capsys):
        assert check_obs_schema.main([write_log(tmp_path, [entry()])]) == 0

    def test_a_duplicate_id_fails(self, tmp_path, capsys):
        log = write_log(tmp_path, [entry(), entry()])
        assert check_obs_schema.main([log]) == 1
        assert "duplicate id" in capsys.readouterr().out

    def test_ids_out_of_order_fail(self, tmp_path, capsys):
        # The property that makes "append-only" checkable rather than asserted.
        log = write_log(tmp_path, [entry(id="obs-0301"), entry(id="obs-0300")])
        assert check_obs_schema.main([log]) == 1
        assert "increasing order" in capsys.readouterr().out

    def test_an_unknown_status_fails(self, tmp_path, capsys):
        log = write_log(tmp_path, [entry(status="pending")])
        assert check_obs_schema.main([log]) == 1
        assert "status" in capsys.readouterr().out

    def test_a_dangling_supersedes_fails(self, tmp_path, capsys):
        log = write_log(tmp_path, [entry(supersedes="obs-0099")])
        assert check_obs_schema.main([log]) == 1
        assert "not in the log" in capsys.readouterr().out

    def test_a_missing_field_fails(self, tmp_path, capsys):
        broken = entry()
        del broken["entities"]
        assert check_obs_schema.main([write_log(tmp_path, [broken])]) == 1

    def test_a_null_cat_outside_the_legacy_window_fails(self, tmp_path, capsys):
        # Inside the window it is history; outside it, it would be new decay.
        log = write_log(tmp_path, [entry(id="obs-0900", cat=None)])
        assert check_obs_schema.main([log]) == 1
        assert "legacy window" in capsys.readouterr().out

    def test_a_null_cat_inside_the_legacy_window_passes(self, tmp_path):
        assert check_obs_schema.main([write_log(tmp_path, [entry(id="obs-0100", cat=None)])]) == 0

    def test_the_real_log_passes(self, capsys):
        assert check_obs_schema.main([str(REAL_LOG)]) == 0


def promotion(**over) -> dict:
    base = entry(id="obs-0400", cat="rule", status="promoted", topic="rule-x",
                 obs="Promoted to CLAUDE.md: X.", rule_title="X", rule_body="do X",
                 cites=["obs-0300"], report="incident:obs-0300")
    base.update(over)
    return base


class TestPromotionGate:
    def test_a_promotion_with_a_resolvable_incident_passes(self, tmp_path):
        log = write_log(tmp_path, [entry(), promotion()])
        assert check_promotions.main([log]) == 0

    def test_a_promotion_with_no_report_fails(self, tmp_path, capsys):
        # A6 exists for exactly this line: adoption on judgement alone.
        log = write_log(tmp_path, [entry(), promotion(report=None)])
        assert check_promotions.main([log]) == 1
        assert "no 'report'" in capsys.readouterr().out

    def test_a_parked_rule_with_no_report_fails(self, tmp_path):
        log = write_log(tmp_path, [entry(), promotion(status="parked", report=None)])
        assert check_promotions.main([log]) == 1

    def test_a_run_report_naming_a_missing_file_fails(self, tmp_path, capsys):
        log = write_log(tmp_path, [entry(), promotion(report="run:tests/nope.json")])
        assert check_promotions.main([log]) == 1
        assert "does not exist" in capsys.readouterr().out

    def test_a_run_report_naming_a_real_file_passes(self, tmp_path):
        log = write_log(tmp_path, [entry(), promotion(report="run:CLAUDE.md")])
        assert check_promotions.main([log]) == 0

    def test_an_incident_citing_a_missing_observation_fails(self, tmp_path, capsys):
        log = write_log(tmp_path, [entry(), promotion(report="incident:obs-0777")])
        assert check_promotions.main([log]) == 1
        assert "not in the log" in capsys.readouterr().out

    def test_a_promotion_citing_only_itself_fails(self, tmp_path, capsys):
        log = write_log(tmp_path, [promotion(report="incident:obs-0400")])
        assert check_promotions.main([log]) == 1
        assert "cites itself" in capsys.readouterr().out

    def test_a_rule_with_no_cites_fails(self, tmp_path, capsys):
        log = write_log(tmp_path, [entry(), promotion(cites=[])])
        assert check_promotions.main([log]) == 1
        assert "no 'cites'" in capsys.readouterr().out

    def test_the_real_log_passes(self):
        assert check_promotions.main([str(REAL_LOG)]) == 0


class TestRenderer:
    def test_the_committed_file_matches_a_fresh_render(self):
        assert render_claude_md.main(["--check"]) == 0

    def test_every_rendered_rule_carries_its_ids(self):
        block = render_claude_md.render()
        for rule in render_claude_md.promoted_rules():
            assert rule["rule_title"] in block
            assert rule["cites"][0] in block

    def test_re_promotion_does_not_reorder_the_file(self):
        """A rule re-promoted on new evidence keeps its place.

        Ordering follows the supersedes chain to its root. Without that, the new entry's
        higher id would move the rule to the bottom and the diff would claim a rule changed
        when only its evidence did. obs-1008 supersedes obs-0995 in the real log, so this
        reads the live case rather than a fixture.
        """
        titles = [r["rule_title"] for r in render_claude_md.promoted_rules()]
        assert titles[0] == "Model Provider"

    @pytest.mark.parametrize("marker", [render_claude_md.BEGIN, render_claude_md.END])
    def test_the_markers_are_present(self, marker):
        assert marker in (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

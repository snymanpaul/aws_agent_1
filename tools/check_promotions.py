"""Gate: a rule is promoted or parked only with the evidence that decided it.

A6. Until now a proposed rule was adopted on audit judgement, which is the one step in this
repo's loop that was held to no evidence standard while every AWS finding was held to one.
This turns that around: `status: promoted` and `status: parked` both require a `report`, and
the report must resolve to something a reader can open.

Two report forms, both mechanically checkable, and the difference is visible in the data:

    run:<path>          a measured run. The file must exist.
    incident:<ids>      the failure that produced the rule, already in the log. Every id
                        must resolve to an entry.

`incident:` is what the eight rules adopted before this gate carry: they came out of real
incidents that are in the store, and retro-fitting a paid run to each would be theatre. A
rule proposed from here on gets `run:`, because A3's harness makes that cheap.

    uv run python tools/check_promotions.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG = ROOT / ".claude" / "learnings" / "observations.jsonl"
NEEDS_REPORT = {"promoted", "parked"}


def main(argv: list[str] | None = None) -> int:
    log = pathlib.Path(argv[0]) if argv else LOG
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    known = {e["id"] for e in entries if "id" in e}
    problems: list[str] = []
    forms = {"run": 0, "incident": 0}

    for e in entries:
        status = e.get("status")
        if status not in NEEDS_REPORT:
            continue
        obs_id = e.get("id")
        report = e.get("report")
        if not report:
            problems.append(
                f"{obs_id}: status {status!r} with no 'report'. A rule is promoted or parked "
                f"only with the run or the incident that decided it.")
            continue

        kind, _, rest = str(report).partition(":")
        if kind == "run":
            if not rest.strip():
                problems.append(f"{obs_id}: report 'run:' names no path")
            elif not (ROOT / rest.strip()).exists():
                problems.append(f"{obs_id}: report names {rest.strip()}, which does not exist")
            else:
                forms["run"] += 1
        elif kind == "incident":
            ids = [i.strip() for i in rest.split(",") if i.strip()]
            if not ids:
                problems.append(f"{obs_id}: report 'incident:' names no observation")
            for i in ids:
                if i not in known:
                    problems.append(f"{obs_id}: report cites {i}, which is not in the log")
                if i == obs_id:
                    problems.append(f"{obs_id}: report cites itself, which is not evidence")
            forms["incident"] += 1
        else:
            problems.append(
                f"{obs_id}: report {report!r} is neither run:<path> nor incident:<ids>")

        # A2's done-condition: every rendered rule cites at least one observation.
        if e.get("cat") == "rule":
            cites = e.get("cites") or []
            if not cites:
                problems.append(f"{obs_id}: a promoted rule with no 'cites'")
            for i in cites:
                if i not in known:
                    problems.append(f"{obs_id}: cites {i}, which is not in the log")
            if not str(e.get("rule_title") or "").strip():
                problems.append(f"{obs_id}: a rule entry with no 'rule_title'")
            if not str(e.get("rule_body") or "").strip():
                problems.append(f"{obs_id}: a rule entry with no 'rule_body'")

    counted = sum(1 for e in entries if e.get("status") in NEEDS_REPORT)
    print(f"check_promotions: {counted} promoted/parked entr(ies), {len(problems)} problem(s).")
    print(f"  evidence: run={forms['run']}  incident={forms['incident']}")
    for p in problems:
        print(f"  {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

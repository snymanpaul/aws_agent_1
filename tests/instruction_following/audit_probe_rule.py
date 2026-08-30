"""A3, third rule: was "probe a new AWS service before writing against it" actually followed?

The other two rules in this repo's A3 set are properties of a produced artifact, so they are
measured against fresh model calls. This one is not. It is a rule about the ORDER OF WORK
across files and days, and the recommendations document's own verifier for it reads the
repository: "a `_sandbox/probe_*` file exists and predates the level file". So it is measured
against the repo's own history here, and costs nothing.

WHAT AN OPPORTUNITY IS. The rule fires on a NEW AWS service, not on any AWS call. A level is
an opportunity when it is the first level, in level order, to construct a boto3 client for a
given service. A level that reuses a service an earlier level already probed is not an
opportunity and stays out of the denominator.

TWO MEASUREMENTS, because the history cannot support one of them everywhere:

  1. A probe exists for the level.  Measurable for every level.
  2. The probe PREDATES the level file, by first-commit date. Only measurable after the
     initial commit: 93 levels landed in one squashed import, where every file shares a
     timestamp and the order is simply not in the history. Those levels are reported as
     UNRECOVERABLE rather than counted either way.

    uv run python tests/instruction_following/audit_probe_rule.py
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from agent_build_gates.eval_harness import wilson  # noqa: E402

LEVEL_DOC = re.compile(r"^L(\d+)([a-z]?)-", re.I)
CODE_LINE = re.compile(r"^\*\*Code:\*\*\s*`([^`]+)`", re.M)
BOTO_CLIENT = re.compile(r"""\.(?:client|resource)\(\s*["']([a-z0-9\-]+)["']""")


def first_commit_date(path: str) -> str | None:
    out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%aI", "-1", "--", path],
                         cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return out or None


def main() -> int:
    squash_date = subprocess.run(
        ["git", "log", "--format=%aI", "--reverse"], cwd=ROOT,
        capture_output=True, text=True).stdout.split("\n")[0].strip()

    levels = []
    for doc in sorted((ROOT / "docs" / "levels").glob("L*.md")):
        m = LEVEL_DOC.match(doc.name)
        code = CODE_LINE.search(doc.read_text(encoding="utf-8"))
        if not (m and code):
            continue
        rel = code.group(1).strip()
        path = ROOT / rel
        if not path.exists():
            continue
        # A few levels point at a directory of files rather than one file.
        files = sorted(path.rglob("*.py")) if path.is_dir() else [path]
        text = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in files)
        levels.append({"n": int(m.group(1)), "suffix": m.group(2), "doc": doc.name,
                       "code": rel,
                       "services": sorted(set(BOTO_CLIENT.findall(text)))})
    levels.sort(key=lambda level: (level["n"], level["suffix"]))

    probes = collections.defaultdict(list)
    for probe in sorted((ROOT / "_sandbox").glob("probe_l*.py")):
        m = re.match(r"probe_l(\d+)", probe.name)
        if m:
            probes[int(m.group(1))].append(probe)

    seen: set[str] = set()
    opportunities = []
    for level in levels:
        new = [s for s in level["services"] if s not in seen]
        seen.update(level["services"])
        if new:
            opportunities.append({**level, "new_services": new})

    exists, dated_followed, dated_total, unrecoverable = [], [], 0, 0
    rows = []
    for opp in opportunities:
        has_probe = bool(probes[opp["n"]])
        exists.append(1.0 if has_probe else 0.0)
        level_date = first_commit_date(opp["code"])
        verdict = "no probe"
        if has_probe:
            probe_dates = [first_commit_date(str(p.relative_to(ROOT))) for p in probes[opp["n"]]]
            probe_dates = [d for d in probe_dates if d]
            if level_date == squash_date or all(d == squash_date for d in probe_dates):
                unrecoverable += 1
                verdict = "probe exists, order unrecoverable (squashed import)"
            else:
                dated_total += 1
                ok = any(d <= level_date for d in probe_dates)
                dated_followed.append(1.0 if ok else 0.0)
                verdict = "probe predates the level file" if ok else "probe came AFTER the level file"
        rows.append({"level": opp["n"], "code": opp["code"], "new_services": opp["new_services"],
                     "probes": len(probes[opp["n"]]), "verdict": verdict})

    print(f"A3 probe rule, audited against the repository, not against model calls")
    print(f"  {len(levels)} levels with a code file, {len(opportunities)} of them introduce "
          f"a new AWS service\n")
    for r in rows:
        print(f"  L{r['level']:<4} {r['code'][:44]:<44} {'+'.join(r['new_services'])[:26]:<26} "
              f"{r['verdict']}")

    lo, hi = wilson(exists) if exists else (0.0, 0.0)
    print(f"\n  a probe exists for the level:        {int(sum(exists))}/{len(exists)} "
          f"[{lo:.2f},{hi:.2f}]")
    if dated_followed:
        lo2, hi2 = wilson(dated_followed)
        print(f"  and it predates the level file:      {int(sum(dated_followed))}/{dated_total} "
              f"[{lo2:.2f},{hi2:.2f}]")
    else:
        print("  and it predates the level file:      no datable opportunity")
    print(f"  order unrecoverable (squashed import): {unrecoverable}")

    out = HERE / "probe_rule_audit.json"
    out.write_text(json.dumps({
        "squash_date": squash_date, "levels_with_code": len(levels),
        "opportunities": len(opportunities), "rows": rows,
        "probe_exists": {"followed": int(sum(exists)), "n": len(exists)},
        "probe_predates": {"followed": int(sum(dated_followed)), "n": dated_total},
        "unrecoverable": unrecoverable,
    }, indent=2) + "\n")
    print(f"\n  written to {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

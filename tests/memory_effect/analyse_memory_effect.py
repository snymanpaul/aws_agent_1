"""A5 analysis: recurrence per observation and pooled, recomputed from the raw answers.

Reported per case first, because a pooled number hides three different situations that call
for different work:

    USED        the fork was reached in both arms and recurrence fell with the memory present
    IGNORED     the fork was reached, the memory was in context, and the mistake recurred
                anyway. Storage is not the bottleneck here; use is.
    UNREACHED   the answer never got to the fork, so the case measured nothing this time

    uv run python tests/memory_effect/analyse_memory_effect.py
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agent_build_gates.eval_harness import perm_test, wilson  # noqa: E402
from cases import CASES  # noqa: E402

BY_KEY = {c["key"]: c for c in CASES}


def scores(cells, case_key, arm, prompt=None):
    """1.0 when the mistake recurred, recomputed from the answer. None leaves the denominator."""
    recurs = BY_KEY[case_key]["recurs"]
    out = []
    for c in cells:
        if c["case"] != case_key or c["arm"] != arm:
            continue
        if prompt is not None and c["prompt"] != prompt:
            continue
        for r in c["runs"]:
            v = recurs(r.get("answer", ""))
            if v is not None:
                out.append(1.0 if v else 0.0)
    return out


def fmt(values):
    if not values:
        return "0/0 (fork not reached)"
    lo, hi = wilson(values)
    return f"{int(sum(values))}/{len(values)} [{lo:.2f},{hi:.2f}]"


def main() -> int:
    reports = sorted(HERE.glob("memory_effect_n*.json"))
    if not reports:
        print("no report yet: run run_memory_effect.py")
        return 1
    d = json.loads(reports[-1].read_text())
    if d.get("complete") is False:
        print(f"INCOMPLETE report ({len(d['cells'])}/{d.get('cells_expected')} cells), "
              "refusing to analyse")
        return 1

    keys = [k for k in (c["key"] for c in CASES) if k in d["cases"]]
    print(f"A5: is a captured mistake avoided because it was captured?  model {d['model']}, "
          f"n={d['n_runs']} per cell")
    print("Recurrence rate: LOWER is better. Reported per observation, then pooled.\n")

    pooled_present, pooled_absent = [], []
    verdicts = {}
    for key in keys:
        present = scores(d["cells"], key, "memory_present")
        absent = scores(d["cells"], key, "memory_absent")
        pooled_present += present
        pooled_absent += absent
        obs_id = d["cases"][key]["obs_id"]
        p = perm_test(present, absent) if present and absent else float("nan")
        print(f"  {key} ({obs_id})")
        print(f"    memory in context  recurred {fmt(present)}")
        print(f"    memory absent      recurred {fmt(absent)}")
        print(f"    perm_test p = {p:.4f}")

        if not present and not absent:
            verdicts[key] = "UNREACHED: no run in either arm reached the fork"
        elif not present or not absent:
            verdicts[key] = "UNREACHED IN ONE ARM: the arms are not comparable here"
        else:
            pr = sum(present) / len(present)
            ar = sum(absent) / len(absent)
            if pr == 0 and ar > 0:
                verdicts[key] = "USED: the mistake disappeared with the memory present"
            elif pr < ar:
                verdicts[key] = "USED IN PART: recurrence fell but did not reach zero"
            elif pr > 0 and pr >= ar:
                verdicts[key] = ("IGNORED: the memory was in context and the mistake recurred "
                                 "anyway")
            else:
                verdicts[key] = "NO MISTAKE IN EITHER ARM: the model did not make it unaided"
        print(f"    -> {verdicts[key]}\n")

    p_pooled = perm_test(pooled_present, pooled_absent) if pooled_present and pooled_absent \
        else float("nan")
    print("=" * 78)
    print(f"  POOLED   memory in context  recurred {fmt(pooled_present)}")
    print(f"           memory absent      recurred {fmt(pooled_absent)}")
    print(f"           perm_test p = {p_pooled:.4f}")
    print()
    counts: dict[str, int] = {}
    for v in verdicts.values():
        head = v.split(":")[0]
        counts[head] = counts.get(head, 0) + 1
    for head, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {head:<22} {n} case(s)")
    print("\nThe pooled figure is the inference. The per-case split is what says whether the")
    print("next unit of work belongs in capturing more or in using what is already captured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

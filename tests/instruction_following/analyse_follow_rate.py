"""A3 analysis: per-rule follow rate, recomputed from the raw answers.

Reads nothing but the stored answer text. Every rate and every p is derived here with the
same verifiers the run used, so fixing a verifier re-derives every number rather than leaving
a stale one on disk.

    uv run python tests/instruction_following/analyse_follow_rate.py
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agent_build_gates.eval_harness import perm_test, wilson  # noqa: E402
from verifiers import RULES  # noqa: E402

ALPHA = 0.05
N_TESTS = len(RULES)


def rate(cells, rule, arm, prompt=None):
    """Recompute from the ANSWER, over opportunities. None leaves the denominator."""
    verifier = RULES[rule]["verifier"]
    out = []
    for c in cells:
        if c["rule"] != rule or c["arm"] != arm:
            continue
        if prompt is not None and c["prompt"] != prompt:
            continue
        for r in c["runs"]:
            v = verifier(r.get("answer", ""))
            if v is not None:
                out.append(1.0 if v else 0.0)
    return out


def fmt(values):
    if not values:
        return "0/0 (no opportunities)"
    lo, hi = wilson(values)
    return f"{int(sum(values))}/{len(values)} [{lo:.2f},{hi:.2f}]"


def main() -> int:
    reports = sorted(HERE.glob("follow_rate_n*.json"))
    if not reports:
        print("no report yet: run run_follow_rate.py")
        return 1
    d = json.loads(reports[-1].read_text())
    if d.get("complete") is False:
        print(f"INCOMPLETE report ({len(d['cells'])}/{d.get('cells_expected')} cells), "
              "refusing to analyse")
        return 1

    corrected = ALPHA / N_TESTS
    print(f"A3: do this repo's own rules get followed?  model {d['model']}, "
          f"n={d['n_runs']} per cell")
    print(f"Bonferroni threshold {corrected:.4f} over {N_TESTS} rules\n")

    verdicts = {}
    for rule in RULES:
        present = rate(d["cells"], rule, "rules_present")
        absent = rate(d["cells"], rule, "rules_absent")
        p = perm_test(absent, present) if present and absent else float("nan")
        print(f"  {rule}: {RULES[rule]['statement'][:66]}...")
        print(f"    rule in context   {fmt(present)}")
        print(f"    rule absent       {fmt(absent)}")
        print(f"    perm_test p = {p:.4f}")
        for pi in sorted({c["prompt"] for c in d["cells"] if c["rule"] == rule}):
            pp = rate(d["cells"], rule, "rules_present", pi)
            pa = rate(d["cells"], rule, "rules_absent", pi)
            print(f"      prompt {pi}: present {fmt(pp):<22} absent {fmt(pa)}")
        if not present or not absent:
            verdicts[rule] = "NO OPPORTUNITIES: the tasks did not create one"
        elif p < corrected and sum(present) / len(present) > sum(absent) / len(absent):
            verdicts[rule] = "the rule RAISES adherence"
        elif sum(absent) / len(absent) >= 0.9:
            verdicts[rule] = "already followed without the rule at this n"
        else:
            verdicts[rule] = "not separated at this n"
        print(f"    -> {verdicts[rule]}\n")

    print("=" * 74)
    for rule, v in verdicts.items():
        print(f"  {rule:<12} {v}")
    print("\n'not separated at this n' is not 'the rule does nothing'. 5 runs per cell is")
    print("small, and this design cannot tell those apart.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

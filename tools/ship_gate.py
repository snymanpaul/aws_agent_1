"""
Level 92: Agentic ship-gate — one auditable GO/NO-GO verdict (the synthesis)
==========================================================================
Composes the whole build-out into the deliverable the original review-gate question wanted:
a paid, AUDIT-REPRODUCIBLE gate. For a candidate agent it runs the eval harness (quality +
cost + permutation-significance vs a frozen baseline) over N real runs and emits a single
GO/NO-GO verdict + a JSON audit artifact.

Anti-simulation design (no fakes/stubs):
  - Real agent runs scored deterministically; tokens from real usage; significance from real
    repeated runs. Demonstrated on a GOOD agent (GO) and a regressed agent (NO-GO) — both real.

Run:
  podman start litellm-proxy
  uv run python tools/ship_gate.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent
from strands.models.openai import OpenAIModel

from tools.eval_harness import Case, run_suite, gate, quality


def _model():
    return OpenAIModel(model_id="gemini-2.5-flash",
                       client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
                       params={"temperature": 0.0})


def _tokens(r):
    u = getattr(getattr(r, "metrics", None), "accumulated_usage", None)
    return (u.get("totalTokens", 0) if isinstance(u, dict) else getattr(u, "totalTokens", 0)) if u else 0


def runner(system_prompt):
    def run(inp):
        r = Agent(model=_model(), callback_handler=None, system_prompt=system_prompt)(inp)
        return str(r), _tokens(r)
    return run


def ship_gate(system_prompt, cases, evaluators, baseline=None,
              min_quality=0.8, max_tokens_factor=3.0, n=4, label="candidate", audit_dir="/tmp"):
    """Run the candidate N times; return an auditable GO/NO-GO verdict."""
    result = run_suite(cases, runner(system_prompt), evaluators, n=n)
    from statistics import mean
    max_tokens = (mean(baseline["tokens"]) * max_tokens_factor) if baseline else None
    passed, reasons = gate(result, baseline=baseline, min_quality=min_quality,
                           max_mean_tokens=max_tokens, metric="correct")
    verdict = {"label": label, "decision": "GO" if passed else "NO-GO", "reasons": reasons,
               "quality": round(quality(result, "correct"), 3),
               "mean_tokens": round(mean(result["tokens"]), 1) if result["tokens"] else 0,
               "n": n}
    path = os.path.join(audit_dir, f"ship_verdict_{label}.json")
    json.dump({**verdict, "result": result}, open(path, "w"))
    verdict["audit_file"] = path
    return verdict, result


CASES = [Case("I love it, fantastic!", "positive"), Case("Terrible, broke instantly.", "negative"),
         Case("Best purchase this year.", "positive"), Case("Awful, never again.", "negative")]
CORRECT = lambda out, c: 1.0 if c.expected in out.lower() else 0.0
GOOD = "Classify sentiment as exactly 'positive' or 'negative'. One word."
REGRESSED = "Respond with an unrelated emoji only."


def verify():
    base_v, base_r = ship_gate(GOOD, CASES, {"correct": CORRECT}, label="baseline")
    print(f"[L92] baseline: {base_v['decision']} quality={base_v['quality']} tok={base_v['mean_tokens']} -> {base_v['audit_file']}")

    good_v, _ = ship_gate(GOOD, CASES, {"correct": CORRECT}, baseline=base_r, label="good_candidate")
    print(f"[L92] good candidate:      {good_v['decision']}  reasons={good_v['reasons']}")

    bad_v, _ = ship_gate(REGRESSED, CASES, {"correct": CORRECT}, baseline=base_r, label="regressed_candidate")
    print(f"[L92] regressed candidate: {bad_v['decision']}  reasons={bad_v['reasons']}")

    checks = {
        "baseline ships (GO)": base_v["decision"] == "GO",
        "good candidate ships (GO)": good_v["decision"] == "GO",
        "regressed candidate is BLOCKED (NO-GO)": bad_v["decision"] == "NO-GO",
        "block cites a concrete reason (quality/significance/cost)": len(bad_v["reasons"]) > 0,
        "verdict is a persisted audit artifact": os.path.exists(bad_v["audit_file"]),
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    assert all(checks.values()), "L92 FAILED"
    print("[L92] PASS — one reproducible, auditable GO/NO-GO ship-gate over real agent runs")


if __name__ == "__main__":
    verify()

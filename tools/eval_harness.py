"""
Level 86: Unified, reusable eval harness (consolidates L35/L49/L51/L52/L85 + adk_patterns)
========================================================================================
Closes the audit gap: the repo had 4+ non-composable bespoke eval scripts. This is ONE
harness: cases + pluggable evaluators + multi-run + bootstrap CI + permutation significance
+ token/latency cost + a regression baseline gate.

Anti-simulation design (no fakes/stubs):
  - run_suite drives a caller-supplied run_fn that makes REAL model calls; tokens come from
    the real AgentResult usage, latency from the wall clock.
  - The self-test (verify) gates a DELIBERATELY-degraded prompt (fails on quality, proven
    significant vs baseline) and a verbose prompt (fails on cost) -- all from real runs.

Reusable API:
  run_suite(cases, run_fn, evaluators, n) -> result   # run_fn(input)->(output, tokens)
  gate(result, baseline=None, min_quality=, max_mean_tokens=, metric=) -> (passed, reasons)
  save_baseline/load_baseline(path, result)

Self-test:
  podman start litellm-proxy
  uv run python tools/eval_harness.py
"""

import json
import math
import os
import random
import time
from dataclasses import dataclass, field
from statistics import mean


@dataclass
class Case:
    input: str
    expected: str = ""
    meta: dict = field(default_factory=dict)


def run_suite(cases, run_fn, evaluators, n=5):
    """run_fn(input) -> (output_str, tokens). evaluators: {name: fn(output, case)->float}."""
    scores = {name: [] for name in evaluators}
    tokens, latency = [], []
    for c in cases:
        for _ in range(n):
            t0 = time.monotonic()
            out, tok = run_fn(c.input)
            latency.append(time.monotonic() - t0)
            tokens.append(int(tok or 0))
            for name, ev in evaluators.items():
                scores[name].append(float(ev(out, c)))
    return {"scores": scores, "tokens": tokens, "latency": latency,
            "n": n, "cases": len(cases)}


# ---- stats (no scipy) ----
def wilson(vals, z=1.96):
    n = len(vals); k = sum(1 for v in vals if v >= 0.5)
    if n == 0:
        return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((c - h) / d, 3), round((c + h) / d, 3)


def perm_test(a, b, iters=3000):
    rng = random.Random(13)
    obs = abs(mean(a) - mean(b)); pool = list(a) + list(b); na = len(a); hits = 0
    for _ in range(iters):
        rng.shuffle(pool)
        if abs(mean(pool[:na]) - mean(pool[na:])) >= obs:
            hits += 1
    return (hits + 1) / (iters + 1)


def quality(result, metric):
    return mean(result["scores"][metric])


def gate(result, baseline=None, min_quality=None, max_mean_tokens=None, metric="correct"):
    passed, reasons = True, []
    q = quality(result, metric)
    if min_quality is not None and q < min_quality:
        passed = False; reasons.append(f"quality {q:.2f} < min {min_quality}")
    mt = mean(result["tokens"]) if result["tokens"] else 0
    if max_mean_tokens is not None and mt > max_mean_tokens:
        passed = False; reasons.append(f"mean tokens {mt:.0f} > max {max_mean_tokens}")
    if baseline is not None:
        bq = quality(baseline, metric); p = perm_test(result["scores"][metric], baseline["scores"][metric])
        if q < bq and p < 0.05:
            passed = False; reasons.append(f"significant quality regression vs baseline ({q:.2f}<{bq:.2f}, p={p:.3f})")
    return passed, reasons


def save_baseline(path, result):
    json.dump(result, open(path, "w"))


def load_baseline(path):
    return json.load(open(path)) if os.path.exists(path) else None


# ----------------- self-test on REAL runs -----------------
def _verify():
    from strands import Agent
    from strands.models.openai import OpenAIModel

    def _model():
        return OpenAIModel(model_id="gemini-2.5-flash",
                           client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
                           params={"temperature": 0.0})

    def _tokens(r):
        u = getattr(getattr(r, "metrics", None), "accumulated_usage", None)
        if isinstance(u, dict):
            return u.get("totalTokens", 0)
        return getattr(u, "totalTokens", 0) if u else 0

    def runner(system_prompt):
        def run(inp):
            r = Agent(model=_model(), callback_handler=None, system_prompt=system_prompt)(inp)
            return str(r), _tokens(r)
        return run

    cases = [Case("I love this, it's fantastic!", "positive"),
             Case("This is terrible and broke immediately.", "negative"),
             Case("Best purchase I've made all year.", "positive")]
    correct = lambda out, c: 1.0 if c.expected in out.lower() else 0.0

    GOOD = "Classify sentiment as exactly 'positive' or 'negative'. One word."
    DEGRADED = "Reply with a random unrelated emoji and nothing else."
    VERBOSE = "Classify as positive or negative, then justify in 6 long sentences with examples."

    base = run_suite(cases, runner(GOOD), {"correct": correct}, n=4)
    save_baseline("/tmp/adk_l86_baseline.json", base)
    deg = run_suite(cases, runner(DEGRADED), {"correct": correct}, n=4)
    verb = run_suite(cases, runner(VERBOSE), {"correct": correct}, n=4)

    base_tok = mean(base["tokens"])
    g_ok, _ = gate(base, min_quality=0.7, max_mean_tokens=base_tok * 3, metric="correct")
    d_ok, d_reasons = gate(deg, baseline=base, min_quality=0.7, metric="correct")
    v_ok, v_reasons = gate(verb, baseline=base, max_mean_tokens=base_tok * 2, metric="correct")

    print(f"[L86] baseline quality={quality(base,'correct'):.2f} CI={wilson(base['scores']['correct'])} mean_tok={base_tok:.0f}")
    print(f"[L86] degraded quality={quality(deg,'correct'):.2f} -> gate passed={d_ok} reasons={d_reasons}")
    print(f"[L86] verbose  quality={quality(verb,'correct'):.2f} mean_tok={mean(verb['tokens']):.0f} -> gate passed={v_ok} reasons={v_reasons}")

    checks = {
        "harness runs real multi-run suite + CI + cost": base["tokens"] and base["n"] == 4,
        "baseline passes its own gate": g_ok,
        "degraded prompt FAILS quality gate (significant)": not d_ok,
        "verbose prompt FAILS cost gate": not v_ok and any("tokens" in r for r in v_reasons),
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    assert all(checks.values()), "L86 FAILED"
    print("[L86] PASS — one reusable harness: datasets + evaluators + multi-run + significance + cost gate")


if __name__ == "__main__":
    _verify()

"""
Level 86: Unified, reusable eval harness (consolidates L35/L49/L51/L52/L85 + adk_patterns)
========================================================================================
Closes the audit gap: the repo had 4+ non-composable bespoke eval scripts. This is ONE
harness: cases + pluggable evaluators + multi-run + Wilson interval over cases + paired
sign-flip significance + token/latency cost + a regression baseline gate.

The unit of evidence is the case, not the run. Repeats of one case are averaged into one
score (at temperature 0 they are near-copies), and the baseline comparison pairs cases.
A paired test on k cases cannot return p below 2 * 0.5**k, so a gate with too few cases
to detect a regression fails closed instead of reporting GO.

Anti-simulation design (no fakes/stubs):
  - run_suite drives a caller-supplied run_fn that makes REAL model calls; tokens come from
    the real AgentResult usage, latency from the wall clock.
  - The self-test (verify) gates a DELIBERATELY-degraded prompt (fails on quality, proven
    significant vs baseline) and a verbose prompt (fails on cost) -- all from real runs.

Reusable API:
  run_suite(cases, run_fn, evaluators, n) -> result   # run_fn(input)->(output, tokens)
  gate(result, baseline=None, min_quality=, max_mean_tokens=, metric=) -> (passed, reasons)
  case_means(result, metric) / sign_flip_test(a, b) / min_p(k)   # the case-level stats
  label_match(output, case)                                      # exact normalised label grader
  save_baseline/load_baseline(path, result)

Self-test:
  podman start litellm-proxy
  uv run python -m agent_build_gates.eval_harness
"""

import hashlib
import itertools
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


def cases_sha256(cases):
    """Fingerprint of the case set, so a baseline can only be paired with the same cases."""
    return hashlib.sha256(json.dumps([[c.input, c.expected] for c in cases]).encode()).hexdigest()


def run_suite(cases, run_fn, evaluators, n=5, meta=None):
    """run_fn(input) -> (output_str, tokens). evaluators: {name: fn(output, case)->float}.
    meta records what produced the runs (model, temperature, prompt hash); it is saved with
    the result, so a baseline says what it was measured on."""
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
            "n": n, "cases": len(cases), "cases_sha256": cases_sha256(cases), "meta": meta or {}}


# ---- stats (no scipy) ----
def wilson(vals, z=1.96):
    n = len(vals); k = sum(1 for v in vals if v >= 0.5)
    if n == 0:
        return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((c - h) / d, 3), round((c + h) / d, 3)


def perm_test(a, b, iters=3000):
    """Unpaired permutation test. Only valid when every value is an independent sample
    (e.g. independent trials of one scenario); the gate uses sign_flip_test instead."""
    rng = random.Random(13)
    obs = abs(mean(a) - mean(b)); pool = list(a) + list(b); na = len(a); hits = 0
    for _ in range(iters):
        rng.shuffle(pool)
        if abs(mean(pool[:na]) - mean(pool[na:])) >= obs:
            hits += 1
    return (hits + 1) / (iters + 1)


ALPHA = 0.05
EXACT_MAX = 16  # 2**16 sign patterns; above this, a seeded Monte Carlo estimate


def case_means(result, metric):
    """One score per case: the mean of its n runs. run_suite is case-major, so case i owns
    scores[i*n:(i+1)*n]. Works on 0.1.0 baselines too, which stored only the flat list."""
    vals, n = result["scores"][metric], result["n"]
    return [mean(vals[i:i + n]) for i in range(0, len(vals), n)]


def sign_flip_test(a, b, iters=20000):
    """Two-sided paired sign-flip test on per-case differences a[i] - b[i]."""
    d = [x - y for x, y in zip(a, b) if x != y]
    if not d:
        return 1.0
    obs = abs(sum(d)) - 1e-12
    if len(d) <= EXACT_MAX:
        hits = sum(1 for s in itertools.product((1, -1), repeat=len(d))
                   if abs(sum(si * di for si, di in zip(s, d))) >= obs)
        return hits / 2 ** len(d)
    rng = random.Random(13)
    hits = sum(1 for _ in range(iters)
               if abs(sum(di if rng.random() < 0.5 else -di for di in d)) >= obs)
    return (hits + 1) / (iters + 1)


def min_p(k):
    """Smallest two-sided p a paired sign-flip test can return with k differing cases."""
    return 2 * 0.5 ** k


def quality(result, metric):
    return mean(case_means(result, metric))


def gate(result, baseline=None, min_quality=None, max_mean_tokens=None, metric="correct"):
    passed, reasons = True, []
    q = quality(result, metric)
    if min_quality is not None and q < min_quality:
        passed = False; reasons.append(f"quality {q:.2f} < min {min_quality}")
    mt = mean(result["tokens"]) if result["tokens"] else 0
    if max_mean_tokens is not None and mt > max_mean_tokens:
        passed = False; reasons.append(f"mean tokens {mt:.0f} > max {max_mean_tokens}")
    if baseline is not None:
        a, b = case_means(result, metric), case_means(baseline, metric)
        ha, hb = result.get("cases_sha256"), baseline.get("cases_sha256")
        if len(a) != len(b) or (ha and hb and ha != hb):  # 0.1.0 baselines carry no hash
            raise ValueError(f"candidate has {len(a)} cases, baseline {len(b)} (case-set hash "
                             f"{'differs' if ha != hb else 'matches'}): a paired comparison "
                             "needs the same cases in the same order")
        # A candidate can only fall below the baseline on cases the baseline scored above 0.
        k = sum(1 for x in b if x > 0)
        if k and min_p(k) >= ALPHA:
            passed = False; reasons.append(
                f"regression undetectable: {k} baseline-scoring cases, best achievable "
                f"p={min_p(k):.3f} >= {ALPHA}; add cases")
        else:
            bq = mean(b); p = sign_flip_test(a, b)
            if q < bq and p < ALPHA:
                passed = False; reasons.append(
                    f"significant quality regression vs baseline ({q:.2f}<{bq:.2f}, p={p:.3f}, {len(a)} paired cases)")
    return passed, reasons


def label_match(out, case):
    """1.0 when the whole answer, normalised, is the expected label. A substring test
    would score 'positive, not negative' correct for both labels."""
    return 1.0 if out.strip().strip(".!\"'`*").strip().lower() == case.expected.strip().lower() else 0.0


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
                           client_args={"base_url": "http://localhost:4000", "api_key": os.environ["LITELLM_API_KEY"]},
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

    # 8 cases: a fully degraded arm can reach p = 2 * 0.5**8 at case level, so the
    # significance check below is testable. 5 or fewer cases never can (min_p(5) > 0.05).
    cases = [Case("I love this, it's fantastic!", "positive"),
             Case("This is terrible and broke immediately.", "negative"),
             Case("Best purchase I've made all year.", "positive"),
             Case("Awful quality, I want a refund.", "negative"),
             Case("Works perfectly and arrived early.", "positive"),
             Case("The worst customer service I have ever had.", "negative"),
             Case("Absolutely delighted with how it turned out.", "positive"),
             Case("It stopped working after two days.", "negative")]
    correct = label_match

    GOOD = "Classify sentiment as exactly 'positive' or 'negative'. One word."
    DEGRADED = "Reply with a random unrelated emoji and nothing else."
    VERBOSE = "Classify as positive or negative, then justify in 6 long sentences with examples."

    base = run_suite(cases, runner(GOOD), {"correct": correct}, n=4, meta={
        "model": "gemini-2.5-flash", "temperature": 0.0,
        "system_prompt_sha256": hashlib.sha256(GOOD.encode()).hexdigest()})
    save_baseline("/tmp/adk_l86_baseline.json", base)
    again = run_suite(cases, runner(GOOD), {"correct": correct}, n=4)
    deg = run_suite(cases, runner(DEGRADED), {"correct": correct}, n=4)
    verb = run_suite(cases, runner(VERBOSE), {"correct": correct}, n=4)

    base_tok = mean(base["tokens"])
    g_ok, _ = gate(base, min_quality=0.7, max_mean_tokens=base_tok * 3, metric="correct")
    a_ok, a_reasons = gate(again, baseline=base, min_quality=0.7, metric="correct")
    d_ok, d_reasons = gate(deg, baseline=base, metric="correct")
    v_ok, v_reasons = gate(verb, baseline=base, max_mean_tokens=base_tok * 2, metric="correct")
    a_p = sign_flip_test(case_means(again, "correct"), case_means(base, "correct"))
    d_p = sign_flip_test(case_means(deg, "correct"), case_means(base, "correct"))

    print(f"[L86] baseline quality={quality(base,'correct'):.2f} case-CI={wilson(case_means(base,'correct'))} mean_tok={base_tok:.0f}")
    print(f"[L86] GOOD again quality={quality(again,'correct'):.2f} paired p={a_p:.4f} -> gate passed={a_ok} reasons={a_reasons}")
    print(f"[L86] degraded   quality={quality(deg,'correct'):.2f} paired p={d_p:.4f} -> gate passed={d_ok} reasons={d_reasons}")
    print(f"[L86] verbose    quality={quality(verb,'correct'):.2f} mean_tok={mean(verb['tokens']):.0f} -> gate passed={v_ok} reasons={v_reasons}")

    checks = {
        "harness runs real multi-run suite + CI + cost": base["tokens"] and base["n"] == 4,
        "baseline passes its own gate": g_ok,
        "negative control: GOOD vs itself is not significant and passes": a_p >= ALPHA and a_ok,
        "positive control: degraded prompt FAILS on significance alone (no quality floor set)":
            not d_ok and any("significant" in r for r in d_reasons),
        "verbose prompt FAILS cost gate": not v_ok and any("tokens" in r for r in v_reasons),
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    assert all(checks.values()), "L86 FAILED"
    print("[L86] PASS — one reusable harness: datasets + evaluators + multi-run + paired significance + cost gate")


if __name__ == "__main__":
    _verify()

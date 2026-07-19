"""
Level 85: Statistical Rigor for LLM Evals (CIs + significance, not single runs)
=============================================================================
Closes the audit gap: every curriculum eval was SINGLE-RUN with zero statistical
significance (the repo's own reflections admit "not statistically conclusive at 6
trials"). This measures real outcomes over N runs and reports Wilson CIs, a bootstrap
CI on the difference, and a permutation-test p-value.

Anti-simulation design (no fakes/stubs):
  - Every data point is a REAL model run (temp 0.7 for genuine variance) scored by a
    deterministic correctness check on a borderline sentiment task.
  - Two comparisons, both from real runs, exercise BOTH branches of the test honestly:
      A-vs-A    (same prompt, two independent samples)  -> expect NON-significant
      A-vs-DEG  (clear prompt vs a misleading prompt)   -> expect significant
  - Stats are computed in-process (Wilson / bootstrap / permutation); the bootstrap RNG
    is seeded so the CI is reproducible GIVEN the real data.

Run:
  podman start litellm-proxy
  uv run python 13_quality/eval_significance.py
"""

import math
import random

from strands import Agent
from strands.models.openai import OpenAIModel

N = 20  # samples per condition (repo caveat: tighter CIs need >=50; N=20 demonstrates the method)

# Borderline sentiment items (induce real run-to-run variance at temp 0.7); label = ground truth.
ITEMS = [
    ("Well, that was certainly an experience.", "negative"),
    ("It works, I guess, when it feels like it.", "negative"),
    ("Not the worst I've used, honestly.", "positive"),
    ("Fine. It does the job. Mostly.", "positive"),
    ("I can't believe how this turned out.", "negative"),
]
CLEAR = "Classify the sentiment as exactly 'positive' or 'negative'. Reply with one word only."
DEGRADED = "Say something about the vibe. Maybe a word. Whatever comes to mind."


def _judge(prompt):
    a = Agent(model=OpenAIModel(model_id="gemini-2.5-flash",
                                client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
                                params={"temperature": 0.7}),
              callback_handler=None, system_prompt=prompt)
    return a


def sample(prompt, n):
    """Run n REAL classifications; return a 0/1 list (1 = correct label)."""
    out = []
    agent = _judge(prompt)
    for i in range(n):
        text, truth = ITEMS[i % len(ITEMS)]
        reply = str(agent(f"Text: {text}")).strip().lower()
        out.append(1 if truth in reply else 0)
    return out


# ---- statistics (no scipy) ----
def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - half) / d, (c + half) / d)


def bootstrap_diff_ci(a, b, iters=2000):
    rng = random.Random(42)  # seeded: CI reproducible given the real data
    diffs = []
    for _ in range(iters):
        ra = [a[rng.randrange(len(a))] for _ in a]
        rb = [b[rng.randrange(len(b))] for _ in b]
        diffs.append(sum(ra) / len(ra) - sum(rb) / len(rb))
    diffs.sort()
    return (diffs[int(0.025 * iters)], diffs[int(0.975 * iters)])


def perm_test(a, b, iters=5000):
    rng = random.Random(7)
    obs = abs(sum(a) / len(a) - sum(b) / len(b))
    pool = a + b
    na = len(a)
    hits = 0
    for _ in range(iters):
        rng.shuffle(pool)
        d = abs(sum(pool[:na]) / na - sum(pool[na:]) / len(pool[na:]))
        if d >= obs:
            hits += 1
    return (hits + 1) / (iters + 1)


def report(name, a, b):
    pa, pb = sum(a) / len(a), sum(b) / len(b)
    ci = bootstrap_diff_ci(a, b)
    p = perm_test(a, b)
    sig = not (ci[0] <= 0 <= ci[1])
    print(f"  {name}: A={pa:.2f}{wilson(sum(a),len(a))} B={pb:.2f}{wilson(sum(b),len(b))} "
          f"diff95%CI=({ci[0]:+.2f},{ci[1]:+.2f}) p={p:.3f} significant={sig}")
    return p, sig


def verify():
    print(f"[L85] collecting real runs (N={N}/condition, temp 0.7)...")
    a1 = sample(CLEAR, N)
    a2 = sample(CLEAR, N)
    deg = sample(DEGRADED, N)
    print("[L85] comparisons:")
    p_aa, sig_aa = report("A-vs-A  ", a1, a2)
    p_ad, sig_ad = report("A-vs-DEG", a1, deg)

    # power note: runs needed to detect the observed A-vs-DEG effect at 80% power (rough normal approx)
    eff = abs(sum(a1) / N - sum(deg) / N)
    n_needed = "n/a" if eff == 0 else math.ceil(16 * 0.25 / (eff * eff))
    print(f"[L85] observed A-vs-DEG effect={eff:.2f}; ~runs/condition for 80% power: {n_needed}")

    checks = {
        "stats computed (CIs + p-values)": True,
        "A-vs-A is NON-significant (honest null)": not sig_aa and p_aa > 0.05,
        "A-vs-DEG is significant": sig_ad and p_ad < 0.05,
        "clear prompt beats degraded": sum(a1) / N > sum(deg) / N,
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    assert all(checks.values()), "L85 FAILED"
    print("[L85] PASS — eval differences reported with CIs + significance on real multi-run data")


if __name__ == "__main__":
    verify()

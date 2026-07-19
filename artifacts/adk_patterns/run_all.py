"""Audit all 8 ADK-pattern prototypes: multi-run reproducibility + token cost.

Each pattern runs N times; we report pass-rate, whether the run is reproducible (identical signal
across runs), and mean token cost. Needs the proxy up: podman start litellm-proxy.

    uv run python run_all.py
"""

import os
import sys

from _harness import audit
from _model import provider, GEMINI_MODEL, BEDROCK_MODEL
import p1_sequential, p2_coordinator, p3_parallel, p4_hierarchical
import p5_generator_critic, p6_iterative_refinement, p7_human_in_the_loop, p8_composite

PATTERNS = [
    ("P1 Sequential Pipeline", p1_sequential.trial, 3),
    ("P2 Coordinator/Dispatcher", p2_coordinator.trial, 3),
    ("P3 Parallel Fan-Out/Gather", p3_parallel.trial, 3),
    ("P4 Hierarchical Decomposition", p4_hierarchical.trial, 3),
    ("P5 Generator & Critic", p5_generator_critic.trial, 3),
    ("P6 Iterative Refinement", p6_iterative_refinement.trial, 3),
    ("P7 Human-in-the-Loop", p7_human_in_the_loop.trial, 3),
    ("P8 Composite", p8_composite.trial, 2),
]


def main():
    override = int(os.environ.get("ADK_RUNS", 0))   # cost control: e.g. ADK_RUNS=2
    results = [audit(label, trial, override or n) for label, trial, n in PATTERNS]
    mdl = f"Bedrock ({BEDROCK_MODEL})" if provider() == "bedrock" else f"proxy->{GEMINI_MODEL}"
    print("\n" + "=" * 78)
    print(f"  SUMMARY — ADK patterns on Strands + {mdl}")
    print("=" * 78)
    print(f"  {'pattern':<34} {'pass':>6} {'reproducible':>13} {'mean tok':>9}")
    print("  " + "-" * 70)
    total_tok = 0
    for r in results:
        total_tok += r["mean_tokens"]
        passed = "ALL" if r["all_pass"] else "FAIL"
        print(f"  {r['label']:<34} {passed:>6} {str(r['reproducible']):>13} {r['mean_tokens']:>9}")
    print("  " + "-" * 70)
    n_pass = sum(1 for r in results if r["all_pass"])
    n_repro = sum(1 for r in results if r["reproducible"])
    print(f"  {n_pass}/{len(results)} patterns pass all runs | {n_repro}/{len(results)} reproducible | "
          f"~{total_tok} tok/full-pass")
    sys.exit(0 if n_pass == len(results) else 1)


if __name__ == "__main__":
    main()

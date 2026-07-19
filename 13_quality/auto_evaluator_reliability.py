"""
L52: Auto-Evaluator Reliability — Biases, Calibration, Jury
=============================================================

L51 proved the auto-evaluator detects obvious quality failures.
This level tests the four failure modes ThoughtWorks flags:

  1. Verbosity bias    — longer responses score higher regardless of quality
  2. Self-preference   — same-model judge inflates its own outputs
  3. Calibration       — judge ranking matches a constructed quality ladder
  4. Jury              — multi-model consensus reduces score variance

ThoughtWorks Radar Vol.33 (Assess):
  "often fails as a reliable proxy for human judgment — susceptibility
   to position bias, verbosity bias, and scaling contamination where
   a model family favors its own outputs"

  "using LLMs as a jury (employing multiple models for consensus)"

Fowler (engineering-practices-llm.html):
  "evaluate the Evaluator to check for false positives and false negatives"

Depends on: L51 (Evals Methodology — established the auto-evaluator pattern)
Unlocks:    L54 (Prompt Refactoring — judge must be calibrated before it can
                  be trusted as a refactoring safety net)

Run:
  uv run python 13_quality/auto_evaluator_reliability.py
"""

from __future__ import annotations

import json
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, stdev
from typing import Any

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

from strands import Agent
from tools import get_model

# ── LLM call counter ─────────────────────────────────────────────────────────

_LLM_CALLS = 0

def _call(agent: Agent, prompt: str) -> str:
    global _LLM_CALLS
    _LLM_CALLS += 1
    return str(agent(prompt))

def _reset():
    global _LLM_CALLS
    _LLM_CALLS = 0

# ── Shared document ──────────────────────────────────────────────────────────

REFERENCE_DOC = (
    "We deployed a new Kubernetes cluster this week using Terraform. "
    "Pod autoscaling reduced our infrastructure cost by 30%."
)

# ── Judge prompt ─────────────────────────────────────────────────────────────

JUDGE_PROMPT = """\
You are an impartial evaluator. Score the following summary of the document
on accuracy and completeness. Use a scale of 1 to 5 where:
  1 = missing key facts or seriously inaccurate
  2 = partially accurate but missing important details
  3 = mostly accurate, minor omissions
  4 = accurate and complete, minor style issues
  5 = accurate, complete, and well expressed

Document:
{document}

Summary:
{summary}

Respond with ONLY: {{"score": <int 1-5>, "reason": "<one sentence>"}}
"""

def _judge(agent: Agent, doc: str, summary: str) -> tuple[int, str]:
    raw = _call(agent, JUDGE_PROMPT.format(document=doc, summary=summary))
    s = raw.find("{"); e = raw.rfind("}") + 1
    if s == -1 or e == 0:
        return 0, "parse failed"
    try:
        obj = json.loads(raw[s:e])
        return int(obj.get("score", 0)), str(obj.get("reason", ""))
    except (json.JSONDecodeError, ValueError):
        return 0, "parse failed"


# ── Iteration 1: Verbosity bias ───────────────────────────────────────────────
#
# Hypothesis: longer summaries score higher regardless of quality.
# Design: three summaries with equivalent accuracy at three word counts.
# Ground truth: all three convey the same core facts — no summary is
# objectively more accurate than the others.
# If the judge scores them in length order, that is verbosity bias.

VERBOSITY_SUMMARIES = [
    # (~10 words) — short but accurate
    ("short",
     "Kubernetes deployed via Terraform; costs cut 30% with autoscaling."),
    # (~20 words) — medium, same facts
    ("medium",
     "A new Kubernetes cluster was deployed this week using Terraform. "
     "Pod autoscaling reduced infrastructure costs by 30%."),
    # (~40 words) — long, same facts padded with restatements
    ("long",
     "This week the team successfully deployed a new Kubernetes cluster, "
     "provisioned using Terraform infrastructure-as-code tooling. "
     "The introduction of pod autoscaling has resulted in a meaningful "
     "reduction in infrastructure costs — specifically a 30% decrease. "
     "Both the deployment and the cost reduction represent positive "
     "outcomes for the infrastructure team."),
]


def iteration_1_verbosity_bias() -> dict:
    judge = Agent(model=get_model("haiku"), callback_handler=None)
    results = []
    for label, summary in VERBOSITY_SUMMARIES:
        score, reason = _judge(judge, REFERENCE_DOC, summary)
        word_count = len(summary.split())
        results.append({"label": label, "words": word_count,
                         "score": score, "reason": reason})

    scores = [r["score"] for r in results]
    # Verbosity bias = scores strictly increase with length
    bias_detected = scores == sorted(scores) and len(set(scores)) > 1

    return {
        "results":       results,
        "scores":        scores,
        "bias_detected": bias_detected,
        "note": ("bias_detected=True means judge scored short < medium < long "
                 "despite equal accuracy — length inflated the score."),
    }


# ── Iteration 2: Self-preference bias ────────────────────────────────────────
#
# Hypothesis: a model judges its own outputs more favourably than
# a different model would.
# Design:
#   - Generate summaries of REFERENCE_DOC using haiku and gemini-flash.
#   - Judge ALL summaries with both haiku and gemini-flash.
#   - Compare: does haiku score haiku-generated summaries higher than
#     gemini-flash does? Does gemini-flash score its own outputs higher?
# Self-preference = own_score > other_score on average.

GENERATION_PROMPT = (
    "Summarise the following document in one sentence (max 20 words).\n\n"
    "Document:\n{document}\n\nRespond with only the summary sentence."
)

def _generate_summary(agent: Agent, doc: str) -> str:
    return _call(agent, GENERATION_PROMPT.format(document=doc)).strip()


def iteration_2_self_preference() -> dict:
    haiku_gen   = Agent(model=get_model("haiku"),        callback_handler=None)
    gemini_gen  = Agent(model=get_model("gemini-flash"), callback_handler=None)
    haiku_judge = Agent(model=get_model("haiku"),        callback_handler=None)
    gemini_judge= Agent(model=get_model("gemini-flash"), callback_handler=None)

    # Generate one summary per model
    haiku_summary  = _generate_summary(haiku_gen,  REFERENCE_DOC)
    gemini_summary = _generate_summary(gemini_gen, REFERENCE_DOC)

    # Judge each summary with each judge model (2×2 matrix)
    hh_score, hh_reason = _judge(haiku_judge,  REFERENCE_DOC, haiku_summary)
    hg_score, hg_reason = _judge(gemini_judge, REFERENCE_DOC, haiku_summary)
    gh_score, gh_reason = _judge(haiku_judge,  REFERENCE_DOC, gemini_summary)
    gg_score, gg_reason = _judge(gemini_judge, REFERENCE_DOC, gemini_summary)

    # Self-preference detected if a model consistently scores its own output
    # higher than the other model does, AND scores the other model's output
    # lower than the other model does.
    haiku_self_inflate  = hh_score > hg_score   # haiku rates haiku higher than gemini does
    gemini_self_inflate = gg_score > gh_score   # gemini rates gemini higher than haiku does

    return {
        "haiku_summary":    haiku_summary,
        "gemini_summary":   gemini_summary,
        "scores": {
            "haiku_summary_by_haiku_judge":  hh_score,
            "haiku_summary_by_gemini_judge": hg_score,
            "gemini_summary_by_haiku_judge": gh_score,
            "gemini_summary_by_gemini_judge":gg_score,
        },
        "reasons": {
            "hh": hh_reason, "hg": hg_reason,
            "gh": gh_reason, "gg": gg_reason,
        },
        "haiku_self_inflates":  haiku_self_inflate,
        "gemini_self_inflates": gemini_self_inflate,
        "bias_detected":        haiku_self_inflate or gemini_self_inflate,
    }


# ── Iteration 3: Calibration against a quality ladder ────────────────────────
#
# Hypothesis: the judge's ranking matches a constructed quality spectrum.
# Design: build 5 summaries with known quality tiers (ground truth set by
# the author). Verify the judge assigns scores in the correct rank order.
# A well-calibrated judge has Spearman rank correlation ≈ 1.0 with ground truth.
# A poorly calibrated judge inverts rankings, especially in the middle tiers.
#
# Ground truth ranking (author-assigned):
#   tier 1 (worst) → tier 5 (best)

QUALITY_LADDER = [
    # (tier, summary) — tiers 1-5 are author ground truth
    (1, "Things improved."),
    (2, "Cloud infrastructure was updated and costs went down."),
    (3, "Kubernetes was deployed using Terraform and costs were reduced."),
    (4, "Kubernetes cluster deployed via Terraform cut costs by 30%."),
    (5, "Kubernetes cluster deployed via Terraform with pod autoscaling reduced infrastructure cost by 30%."),
]


def _spearman_rho(ground_truth_ranks: list[int], judge_ranks: list[int]) -> float:
    """
    Spearman rank correlation. Returns 1.0 if perfectly correlated,
    -1.0 if perfectly inverted, 0.0 if no correlation.
    """
    n = len(ground_truth_ranks)
    if n < 2:
        return 0.0
    d_sq = sum((g - j) ** 2 for g, j in zip(ground_truth_ranks, judge_ranks))
    return 1.0 - (6 * d_sq) / (n * (n**2 - 1))


def iteration_3_calibration() -> dict:
    judge = Agent(model=get_model("haiku"), callback_handler=None)
    results = []
    for tier, summary in QUALITY_LADDER:
        score, reason = _judge(judge, REFERENCE_DOC, summary)
        results.append({"tier": tier, "summary": summary,
                         "judge_score": score, "reason": reason})

    # Ground truth ranks: [1, 2, 3, 4, 5] (ascending quality)
    ground_truth = [r["tier"] for r in results]
    # Judge ranks: rank the judge scores (1 = lowest score)
    judge_scores = [r["judge_score"] for r in results]
    # Convert scores to ranks (handle ties: same score = same rank)
    sorted_scores = sorted(enumerate(judge_scores), key=lambda x: x[1])
    ranks = [0] * len(judge_scores)
    for rank_pos, (orig_idx, _) in enumerate(sorted_scores, 1):
        ranks[orig_idx] = rank_pos

    rho = _spearman_rho(ground_truth, ranks)

    # Calibration is good if rho >= 0.8 (strong positive correlation)
    # and the top and bottom tiers are correctly identified
    top_correct    = results[-1]["judge_score"] >= results[-2]["judge_score"]
    bottom_correct = results[0]["judge_score"]  <= results[1]["judge_score"]

    return {
        "results":         results,
        "judge_scores":    judge_scores,
        "ground_truth":    ground_truth,
        "judge_ranks":     ranks,
        "spearman_rho":    rho,
        "top_correct":     top_correct,
        "bottom_correct":  bottom_correct,
        "well_calibrated": rho >= 0.8 and top_correct and bottom_correct,
    }


# ── Iteration 4: Jury — does multi-model consensus reduce variance? ───────────
#
# Hypothesis: a jury of N judge models has lower score variance than
# any single judge alone.
# Design:
#   - Run 3 judge models on the same 5-tier quality ladder.
#   - Measure per-tier score variance for each single judge.
#   - Measure per-tier variance for the jury consensus (mean score).
#   - Jury variance should be <= worst single-judge variance.
#
# Also: do the three judges AGREE on the ranking? Agreement on relative
# ordering matters more than agreement on absolute scores.

JURY_MODELS = ["haiku", "gemini-flash"]  # 2 judges available; report both


def iteration_4_jury() -> dict:
    judges = {alias: Agent(model=get_model(alias), callback_handler=None)
              for alias in JURY_MODELS}

    # Score all 5 ladder summaries with each judge
    all_scores: dict[str, list[int]] = {alias: [] for alias in JURY_MODELS}
    per_tier: list[dict] = []

    for tier, summary in QUALITY_LADDER:
        tier_entry: dict = {"tier": tier, "summary": summary[:50] + "...", "scores": {}}
        for alias, agent in judges.items():
            score, _ = _judge(agent, REFERENCE_DOC, summary)
            all_scores[alias].append(score)
            tier_entry["scores"][alias] = score
        # Jury consensus = mean of all judges
        jury_score = mean(tier_entry["scores"].values())
        tier_entry["jury_mean"] = round(jury_score, 2)
        per_tier.append(tier_entry)

    # Per-judge variance across the 5 tiers
    judge_variances = {
        alias: round(stdev(scores) if len(scores) > 1 else 0.0, 3)
        for alias, scores in all_scores.items()
    }

    # Jury variance: variance of the mean scores across tiers
    jury_means     = [t["jury_mean"] for t in per_tier]
    jury_variance  = round(stdev(jury_means) if len(jury_means) > 1 else 0.0, 3)

    # Do judges agree on relative ranking? Compare Spearman rho between judges
    def _scores_to_ranks(scores: list[int]) -> list[int]:
        sorted_pairs = sorted(enumerate(scores), key=lambda x: x[1])
        ranks = [0] * len(scores)
        for r, (i, _) in enumerate(sorted_pairs, 1):
            ranks[i] = r
        return ranks

    judge_ranks = {alias: _scores_to_ranks(scores) for alias, scores in all_scores.items()}
    aliases = list(JURY_MODELS)
    ranking_agreement = None
    if len(aliases) >= 2:
        rho = _spearman_rho(judge_ranks[aliases[0]], judge_ranks[aliases[1]])
        ranking_agreement = round(rho, 3)

    max_single_variance = max(judge_variances.values())

    return {
        "per_tier":              per_tier,
        "judge_variances":       judge_variances,
        "jury_variance":         jury_variance,
        "ranking_agreement_rho": ranking_agreement,
        "jury_reduces_variance": jury_variance <= max_single_variance,
        "judges_agree_on_ranking": ranking_agreement is not None and ranking_agreement >= 0.8,
    }


# ── Runner ────────────────────────────────────────────────────────────────────

def _header(title: str) -> None:
    print(f"\n{'═' * 62}")
    print(textwrap.fill(title, width=62))
    print(f"{'═' * 62}")


if __name__ == "__main__":
    print("=" * 62)
    print("L52: Auto-Evaluator Reliability")
    print("Biases, Calibration, Jury")
    print("=" * 62)
    print()
    print('  ThoughtWorks (Vol.33): "often fails as a reliable proxy')
    print('  for human judgment — susceptibility to position bias,')
    print('  verbosity bias, and scaling contamination where a model')
    print('  family favors its own outputs."')

    # ── Iter 1 ──────────────────────────────────────────────────────────────
    _header("Iteration 1 — Verbosity Bias")
    print("  Hypothesis: longer summaries score higher regardless of quality.")
    print("  All three summaries convey the same core facts.")
    _reset()
    v = iteration_1_verbosity_bias()
    print(f"\n  {'Label':<8} {'Words':>5} {'Score':>6}")
    print(f"  {'─'*8} {'─'*5} {'─'*6}")
    for r in v["results"]:
        print(f"  {r['label']:<8} {r['words']:>5} {r['score']:>6}/5")
    print()
    for r in v["results"]:
        print(f"  {r['label']}: {r['reason'][:60]}")
    print()
    if v["bias_detected"]:
        print(f"  ⚠  Verbosity bias DETECTED: scores increase strictly with length.")
        print(f"     Longer text was rewarded regardless of added accuracy.")
    else:
        scores = v["scores"]
        if len(set(scores)) == 1:
            print(f"  ~ All summaries scored equally ({scores[0]}/5).")
            print(f"    Judge did not differentiate on length or quality.")
            print(f"    This may indicate a ceiling effect at the top of the scale.")
        else:
            print(f"  ✓  No strict verbosity bias: scores={scores}")
            print(f"     Length alone did not determine score ordering.")
    print(f"  LLM calls: {_LLM_CALLS}")

    # ── Iter 2 ──────────────────────────────────────────────────────────────
    _header("Iteration 2 — Self-Preference Bias")
    print("  Hypothesis: a model rates its own outputs higher than")
    print("  a different model would.")
    print("  Design: haiku and gemini-flash each generate a summary;")
    print("  both judge both summaries (2×2 matrix).")
    _reset()
    sp = iteration_2_self_preference()
    print(f"\n  haiku summary   : '{sp['haiku_summary'][:60]}'")
    print(f"  gemini summary  : '{sp['gemini_summary'][:60]}'")
    print(f"\n  Scoring matrix (row=judge, col=summary):")
    print(f"  {'':12} {'haiku output':>14} {'gemini output':>14}")
    print(f"  {'─'*12} {'─'*14} {'─'*14}")
    s = sp["scores"]
    print(f"  {'haiku judge':<12} {s['haiku_summary_by_haiku_judge']:>14} {s['gemini_summary_by_haiku_judge']:>14}")
    print(f"  {'gemini judge':<12} {s['haiku_summary_by_gemini_judge']:>14} {s['gemini_summary_by_gemini_judge']:>14}")
    print()
    hi = sp["haiku_self_inflates"]
    gi = sp["gemini_self_inflates"]
    print(f"  haiku  rates own output higher than gemini does : {hi}")
    print(f"  gemini rates own output higher than haiku does  : {gi}")
    if sp["bias_detected"]:
        print(f"\n  ⚠  Self-preference bias DETECTED in at least one model.")
        print(f"     ThoughtWorks: 'a model family favors its own outputs'")
        print(f"     Implication: always use a DIFFERENT model family as judge.")
    else:
        print(f"\n  ✓  No self-preference bias detected in this run.")
        print(f"     Both models scored each other's outputs consistently.")
        print(f"     Still: ThoughtWorks recommends cross-model judging as")
        print(f"     a precaution — bias may appear on other output types.")
    print(f"  LLM calls: {_LLM_CALLS}")

    # ── Iter 3 ──────────────────────────────────────────────────────────────
    _header("Iteration 3 — Calibration Against a Quality Ladder")
    print("  Hypothesis: judge ranking matches author-assigned quality tiers.")
    print("  5-tier quality spectrum — tier 5 is objectively most complete.")
    print("  Spearman rho = 1.0 means perfect rank correlation with ground truth.")
    _reset()
    cal = iteration_3_calibration()
    print(f"\n  {'Tier':>5} {'Judge':>6} {'Summary (truncated)':<45}")
    print(f"  {'─'*5} {'─'*6} {'─'*45}")
    for r in cal["results"]:
        summ = r["summary"][:43]
        print(f"  {r['tier']:>5} {r['judge_score']:>6}/5  {summ}")
    print(f"\n  Spearman rho (judge vs ground truth) : {cal['spearman_rho']:.3f}")
    print(f"  Top tier correctly highest score     : {cal['top_correct']}")
    print(f"  Bottom tier correctly lowest score   : {cal['bottom_correct']}")
    if cal["well_calibrated"]:
        print(f"\n  ✓  Judge is well calibrated (rho >= 0.8, top and bottom correct).")
        print(f"     Rankings match the quality ladder — judge scores are meaningful.")
    else:
        print(f"\n  ⚠  Calibration issues detected.")
        if cal["spearman_rho"] < 0.8:
            print(f"     rho={cal['spearman_rho']:.3f} < 0.8: rank correlation with")
            print(f"     ground truth is weak. Middle-tier summaries mis-ranked.")
        if not cal["top_correct"]:
            print(f"     Top tier not correctly identified as highest score.")
        if not cal["bottom_correct"]:
            print(f"     Bottom tier not correctly identified as lowest score.")
    print(f"  LLM calls: {_LLM_CALLS}")

    # ── Iter 4 ──────────────────────────────────────────────────────────────
    _header("Iteration 4 — Jury: Multi-Model Consensus")
    print("  Hypothesis: a jury of N judges has lower score variance")
    print("  than any single judge alone.")
    print(f"  Judges: {JURY_MODELS}")
    _reset()
    jury = iteration_4_jury()

    print(f"\n  Per-tier scores:")
    print(f"  {'Tier':>5} " + " ".join(f"{m:>14}" for m in JURY_MODELS) + f"  {'Jury mean':>10}")
    print(f"  {'─'*5} " + " ".join(f"{'─'*14}" for _ in JURY_MODELS) + f"  {'─'*10}")
    for t in jury["per_tier"]:
        scores_str = " ".join(f"{t['scores'].get(m, '?'):>14}" for m in JURY_MODELS)
        print(f"  {t['tier']:>5} {scores_str}  {t['jury_mean']:>10}")

    print(f"\n  Score variance (stdev across 5 tiers):")
    for alias, var in jury["judge_variances"].items():
        print(f"    {alias:<14}: {var:.3f}")
    print(f"    {'jury (mean)':<14}: {jury['jury_variance']:.3f}")

    print(f"\n  Ranking agreement between judges (Spearman rho): "
          f"{jury['ranking_agreement_rho']}")

    if jury["jury_reduces_variance"]:
        print(f"\n  ✓  Jury variance ({jury['jury_variance']:.3f}) <= "
              f"max single-judge variance ({max(jury['judge_variances'].values()):.3f})")
        print(f"     Consensus does smooth out individual judge noise.")
    else:
        print(f"\n  ~ Jury did not reduce variance in this run.")
        print(f"    Individual judges may already agree closely enough")
        print(f"    that averaging adds noise rather than reducing it.")

    if jury["judges_agree_on_ranking"]:
        print(f"  ✓  Judges agree on relative ranking (rho >= 0.8).")
        print(f"     Even when absolute scores differ, quality ordering is consistent.")
    else:
        print(f"  ⚠  Judges disagree on ranking (rho < 0.8).")
        print(f"     Jury consensus is needed precisely because judges disagree.")
    print(f"  LLM calls: {_LLM_CALLS}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'=' * 62}")
    print(f"Reliability findings:")
    print()
    vb = "BIAS PRESENT" if v["bias_detected"] else ("ceiling effect" if len(set(v["scores"])) == 1 else "no bias")
    sp_r = "BIAS PRESENT" if sp["bias_detected"] else "no bias"
    cal_r = f"rho={cal['spearman_rho']:.2f} ({'well calibrated' if cal['well_calibrated'] else 'MISCALIBRATED'})"
    jury_r = "variance reduced" if jury["jury_reduces_variance"] else "variance not reduced"
    print(f"  1. Verbosity bias     : {vb}")
    print(f"  2. Self-preference    : {sp_r}")
    print(f"  3. Calibration        : {cal_r}")
    print(f"  4. Jury               : {jury_r}")
    print()
    print(f"  Fowler: 'evaluate the Evaluator'")
    print(f"  ThoughtWorks: treat LLM-as-judge 'with caution — ensuring")
    print(f"  human verification, transparency and ethical oversight'")
    print(f"  before using in critical workflows.")
    print()
    print(f"  Practical rules:")
    print(f"  - Test your judge on a quality ladder before trusting its scores")
    print(f"  - Never use same-model family as judge (self-preference risk)")
    print(f"  - Check for verbosity bias in your domain; length != quality")
    print(f"  - Use a jury (2+ models) for decisions with real consequences")

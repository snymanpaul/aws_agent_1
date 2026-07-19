"""
Level 49: Evals Harness — CI/CD for LLM Systems

Builds an automated test harness that detects regression in the LLM judgment layer.
A model update, prompt change, or config drift should not silently degrade production
behaviour — this harness catches it.

Fowler principle (engineering-practices-llm.html):
  "You should decouple inference and testing, so that you can run inference,
   which is time-consuming, once and run multiple property-based tests on the results."
  Every additional test type costs zero additional LLM calls.

The gap vs L35 (Strands Evals SDK):
  L35 tests agent output quality. L49 tests boundary contracts in a hybrid system:
  - Does the LLM still return parseable JSON?          (parse rate)
  - Is confidence calibration stable?                   (ECE)
  - Do hard gates fire at expected frequency?           (override rate)
  - Does plan repair still cover the output range?      (repair rate)

5 iterations:
  1. Inference-testing decoupling (Fowler pattern demonstrated)
  2. Parse rate gate               (L46b: classify_document returns valid Classification)
  3. Confidence calibration gate   (L46b: ECE — confidence alignment with accuracy)
  4. Override rate gate            (L46d: hard gates fire at expected frequency)
  5. Plan repair rate + CI gate    (L46c: plan quality + baseline capture/regression)
"""
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

from hybrid_llm_in_deterministic import classify_document
from hybrid_trust_boundaries import process_request, PipelineState, REQUESTS as L46D_REQUESTS
from hybrid_plan_execute import generate_plan, parse_and_repair_plan, SCHEMA_FIELDS as L46C_SCHEMA


# ══════════════════════════════════════════════════════════════════════════════
# Eval corpus — 10 documents with ground truth labels
# Categories match L46b schema: technical | business | legal | personal | unknown
# ══════════════════════════════════════════════════════════════════════════════

EVAL_CORPUS: list[tuple[str, str, str]] = [  # (doc_id, true_label, text)
    ("eval-01", "technical",
     "HNSW graph index enables sub-millisecond ANN search over 100M vectors. "
     "Key params: M=16 (connectivity), ef_construction=200 (build quality), ef=50 (recall). "
     "Memory: ~80 bytes per vector at d=128. Target: 95%+ recall at p99 < 10ms."),

    ("eval-02", "business",
     "Q4 revenue projections: 23% YoY growth driven by enterprise renewals. "
     "APAC contributed $4.2M incremental ARR. Churn improved 8.3% → 6.1% after "
     "onboarding redesign. Pipeline coverage 3.1x. Board presentation March 15."),

    ("eval-03", "legal",
     "Force majeure clause 12.4(b) exempts performance obligations arising from "
     "circumstances beyond reasonable control. Liability cap under section 18 limited to "
     "fees paid in prior 12 months. Governing law: Delaware. Arbitration: AAA rules."),

    ("eval-04", "technical",
     "Rate limiter: token bucket, 1000 req/s refill, 5000 burst capacity. "
     "Sliding window log in Redis, TTL=60s. Adaptive throttling at 80% fill. "
     "DDoS mitigation enabled. P99 latency under load: 12ms."),

    ("eval-05", "business",
     "Sales cycle compressed 12 days after SDR onboarding redesign. "
     "CAC down 18% YoY. Pipeline 3.1x Q1. Revenue per rep +$180K, headcount flat at 24 AEs."),

    ("eval-06", "personal",
     "Annual review: exceeded targets Q3 and Q4. Leadership positive on collaboration. "
     "Development goal: public speaking. Salary: +8% merit increase from March 1. "
     "Stock refresh: 400 RSUs vesting over 4 years."),

    ("eval-07", "legal",
     "GDPR Article 28 DPA requires processor to implement appropriate technical and "
     "organizational measures. Sub-processor list updated within 14 days of changes. "
     "Data subject rights requests fulfilled within 30 days."),

    ("eval-08", "technical",
     "K8s scheduling: anti-affinity on zone, preferred t3.xlarge. "
     "Requests: 500m CPU / 1Gi RAM. Limits: 2 CPU / 4Gi. "
     "HPA target 70% CPU, min=2, max=10 replicas. PDB: maxUnavailable=1."),

    ("eval-09", "business",
     "Attribution model updated from last-click to data-driven. "
     "Reallocation: +$200K paid search, -$150K display. CAC target -12%. "
     "ROI target 4x by end Q2. Budget approved by CFO March 8."),

    ("eval-10", "personal",
     "1:1 notes: promotion timeline discussed, Q1 performance reviewed. "
     "Agreed: tech lead responsibilities for Project X starting April. "
     "Dev budget: $2000 approved. Next formal review in 6 months."),
]


# ══════════════════════════════════════════════════════════════════════════════
# Plan eval requests — tests LLM plan quality against L46c op vocabulary
# Schema fields: ['id', 'name', 'email', 'company', 'status', 'revenue']
# ══════════════════════════════════════════════════════════════════════════════

PLAN_EVAL_REQUESTS: list[tuple[str, str]] = [
    (
        "quarterly data prep",
        "Normalize names to title case, validate email addresses (drop invalid), "
        "filter out inactive accounts, flag records with missing revenue.",
    ),
    (
        "enrichment pipeline",
        "Add a one-sentence customer_summary per record using name and company, "
        "normalize email to lowercase, validate revenue is a positive number.",
    ),
    (
        "churn risk filter",
        "Keep only active and churned customers, normalize company names to title case, "
        "validate that revenue is not empty.",
    ),
    (
        "contact list build",
        "Filter to active customers only, normalize name to title case, "
        "validate email format (drop invalid), add outreach_note per record.",
    ),
]


# ══════════════════════════════════════════════════════════════════════════════
# Cached inference result types
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ClassificationRecord:
    """Result of one classify_document call, stored for zero-cost test evaluation."""
    doc_id: str
    true_label: str
    category: str
    confidence: float
    reason: str

    @property
    def is_fallback(self) -> bool:
        return "fallback" in self.reason

    @property
    def is_correct(self) -> bool:
        return self.category == self.true_label


@dataclass
class PlanRecord:
    """Result of one generate_plan + parse_and_repair_plan call."""
    request_label: str
    raw_ops: int
    repairs: int
    removals: int

    @property
    def was_repaired(self) -> bool:
        return self.repairs > 0 or self.removals > 0


# ══════════════════════════════════════════════════════════════════════════════
# Metric functions — pure functions on cached results. Zero LLM calls.
# ══════════════════════════════════════════════════════════════════════════════

def compute_parse_rate(cache: list[ClassificationRecord]) -> float:
    """Fraction of classifications that returned valid JSON (not the fallback path)."""
    if not cache:
        return 0.0
    return sum(1 for r in cache if not r.is_fallback) / len(cache)


def compute_ece(cache: list[ClassificationRecord], bins: int = 3) -> float:
    """
    Simplified Expected Calibration Error over `bins` equal-width confidence buckets.
    ECE = sum_b |fraction_correct(b) - mean_confidence(b)| * |b|/N

    Perfect calibration = ECE 0.0 (when model says 80% confident, it's right 80% of the time).
    """
    n = len(cache)
    if n == 0:
        return 0.0
    buckets: list[dict] = [{"correct": 0, "total": 0, "conf_sum": 0.0} for _ in range(bins)]
    for r in cache:
        b = min(int(r.confidence * bins), bins - 1)
        buckets[b]["total"] += 1
        buckets[b]["conf_sum"] += r.confidence
        if r.is_correct:
            buckets[b]["correct"] += 1
    ece = 0.0
    for bk in buckets:
        if bk["total"] == 0:
            continue
        frac_correct = bk["correct"] / bk["total"]
        mean_conf    = bk["conf_sum"] / bk["total"]
        ece += abs(frac_correct - mean_conf) * bk["total"] / n
    return ece


def compute_override_rate(records: list[Any]) -> float:
    """Fraction of requests where system final_action != LLM recommendation."""
    if not records:
        return 0.0
    return sum(1 for r in records if r.overridden) / len(records)


def compute_repair_rate(plans: list[PlanRecord]) -> float:
    """Fraction of generated plans that required any repair or removal."""
    if not plans:
        return 0.0
    return sum(1 for p in plans if p.was_repaired) / len(plans)


# ══════════════════════════════════════════════════════════════════════════════
# Thresholds — design intent. Update from your own baseline, not theory.
# ══════════════════════════════════════════════════════════════════════════════

THRESHOLDS = {
    "parse_rate_min":    0.90,   # ≥90% of classify_document calls must return valid JSON
    "ece_max":           0.25,   # calibration error < 25%
    "override_rate_min": 0.10,   # hard gates must fire on ≥10% of requests (gates are working)
    "override_rate_max": 0.70,   # hard gates must not fire on >70% (LLM is doing useful work)
    "repair_rate_max":   0.50,   # ≤50% of LLM plans may need repair
}

# Max allowed change from baseline before a regression is flagged
REGRESSION = {
    "parse_rate":    0.10,   # parse rate can't drop >10 points
    "ece":           0.15,   # ECE can't rise >15 points
    "override_rate": 0.25,   # override rate can't drift >25 points
    "repair_rate":   0.20,   # repair rate can't rise >20 points
}

BASELINE_PATH = _HERE / "eval_baseline.json"


# ══════════════════════════════════════════════════════════════════════════════
# Inference runners — LLM calls live here. Results returned as cache objects.
# ══════════════════════════════════════════════════════════════════════════════

def run_l46b_inference() -> list[ClassificationRecord]:
    """Phase 1 for Iters 1–3: classify_document on EVAL_CORPUS. Returns cache."""
    cache: list[ClassificationRecord] = []
    for doc_id, true_label, text in EVAL_CORPUS:
        clf = classify_document(text)
        rec = ClassificationRecord(
            doc_id=doc_id, true_label=true_label,
            category=clf.category, confidence=clf.confidence, reason=clf.reason,
        )
        cache.append(rec)
        marker = "✓" if rec.is_correct else "✗"
        print(f"    {marker} {doc_id}: true={true_label:<10} pred={clf.category:<10} conf={clf.confidence:.2f}")
    return cache


def run_l46d_inference() -> tuple[list[Any], PipelineState]:
    """Phase 1 for Iter 4: full trust-boundary pipeline on L46D_REQUESTS."""
    state   = PipelineState()
    records = []
    for req in L46D_REQUESTS:
        rec = process_request(req, state)
        records.append(rec)
        marker = "⚠ OVERRIDE" if rec.overridden else "  aligned "
        print(f"    {marker}  [{req['id']}] {req['title'][:28]:<28} "
              f"LLM={rec.llm_recommendation:<8} → final={rec.final_action}")
    return records, state


def run_l46c_inference() -> list[PlanRecord]:
    """Phase 1 for Iter 5: generate_plan + repair on PLAN_EVAL_REQUESTS."""
    plans = []
    for label, request in PLAN_EVAL_REQUESTS:
        try:
            raw_ops = generate_plan(L46C_SCHEMA, request)
            _, log  = parse_and_repair_plan(raw_ops, L46C_SCHEMA)
            plan    = PlanRecord(
                request_label=label, raw_ops=len(raw_ops),
                repairs=len(log.repairs), removals=len(log.removals),
            )
        except ValueError as e:
            plan = PlanRecord(request_label=label, raw_ops=0, repairs=1, removals=0)
            print(f"    [warn] plan generation failed for {label!r}: {e}")
        marker = "⚠ repaired" if plan.was_repaired else "  clean   "
        print(f"    {marker}  {label!r}: {plan.raw_ops} ops, "
              f"{plan.repairs} repairs, {plan.removals} removals")
        plans.append(plan)
    return plans


# ══════════════════════════════════════════════════════════════════════════════
# Output helpers
# ══════════════════════════════════════════════════════════════════════════════

def _gate_line(name: str, value: float, description: str, passed: bool) -> None:
    print(f"  {'✓' if passed else '✗'} {name:<16} = {value:.3f}  ({description})")


def _regression_check(current: dict, baseline: dict) -> None:
    print("  Regression check vs baseline:")
    any_regression = False
    for metric, delta_max in REGRESSION.items():
        c = current.get(metric, 0.0)
        b = baseline.get(metric, 0.0)
        delta     = c - b
        regressed = (delta < -delta_max) if metric == "parse_rate" else (delta > delta_max)
        marker    = " ⚠ REGRESSION" if regressed else ""
        print(f"    {metric:<16}: {b:.3f} → {c:.3f} ({delta:+.3f}){marker}")
        if regressed:
            any_regression = True
    if any_regression:
        print("  ⚠ REGRESSION DETECTED — investigate before deploying")
    else:
        print("  All metrics within regression thresholds ✓")


# ══════════════════════════════════════════════════════════════════════════════
# Iteration 1 — Inference-testing decoupling (Fowler)
# ══════════════════════════════════════════════════════════════════════════════

def iteration_1_decoupling() -> list[ClassificationRecord]:
    print(f"\n{'═'*62}")
    print("Iteration 1 — Inference-testing decoupling (Fowler)")
    print("  Run LLM once, apply multiple test types to the cached result.")
    print(f"{'═'*62}")

    print(f"\n  Phase 1 — Inference ({len(EVAL_CORPUS)} LLM calls)")
    t0    = time.perf_counter()
    cache = run_l46b_inference()
    ms    = (time.perf_counter() - t0) * 1000

    print(f"\n  Phase 2 — Tests applied to cache (0 additional LLM calls)")

    # Three independent test types — same cache, zero extra cost each
    print(f"    Test A parse rate:    {compute_parse_rate(cache):.0%}")
    cat_dist = dict(sorted(Counter(r.category for r in cache).items()))
    print(f"    Test B category dist: {cat_dist}")
    confs = sorted(r.confidence for r in cache)
    n = len(confs)
    print(f"    Test C confidence:    p25={confs[n//4]:.2f}  p50={confs[n//2]:.2f}  p75={confs[3*n//4]:.2f}")

    print(f"\n  Fowler: {len(EVAL_CORPUS)} inference calls → 3 test types, 0 extra calls. "
          f"Inference: {ms:.0f}ms")
    return cache


# ══════════════════════════════════════════════════════════════════════════════
# Iteration 2 — Parse rate gate (L46b boundary contract 1)
# ══════════════════════════════════════════════════════════════════════════════

def iteration_2_parse_rate(cache: list[ClassificationRecord]) -> dict:
    print(f"\n{'═'*62}")
    print("Iteration 2 — Parse rate gate (L46b)")
    print("  Contract: classify_document returns valid Classification (not fallback)")
    print(f"{'═'*62}")
    print("  Using cached inference from Iter 1 — 0 LLM calls")

    parse_rate = compute_parse_rate(cache)
    threshold  = THRESHOLDS["parse_rate_min"]
    passed     = parse_rate >= threshold

    for r in (r for r in cache if r.is_fallback):
        print(f"    [fallback] {r.doc_id}: {r.reason[:70]}")

    print(f"\n  parse_rate = {parse_rate:.3f}  [≥ {threshold:.2f}]  {'✓ PASS' if passed else '✗ FAIL'}")
    return {"parse_rate": parse_rate, "parse_rate_pass": passed}


# ══════════════════════════════════════════════════════════════════════════════
# Iteration 3 — Confidence calibration gate (L46b boundary contract 2)
# ══════════════════════════════════════════════════════════════════════════════

def iteration_3_calibration(cache: list[ClassificationRecord]) -> dict:
    print(f"\n{'═'*62}")
    print("Iteration 3 — Confidence calibration gate (L46b)")
    print("  Contract: ECE < threshold (confidence correlates with accuracy)")
    print(f"{'═'*62}")
    print("  Using cached inference from Iter 1 — 0 LLM calls")

    ece       = compute_ece(cache)
    accuracy  = sum(1 for r in cache if r.is_correct) / len(cache)
    threshold = THRESHOLDS["ece_max"]
    passed    = ece < threshold

    for r in (r for r in cache if not r.is_correct):
        print(f"    [wrong] {r.doc_id}: true={r.true_label} pred={r.category} conf={r.confidence:.2f}")

    print(f"\n  accuracy = {accuracy:.3f}")
    print(f"  ece      = {ece:.3f}  [< {threshold:.2f}]  {'✓ PASS' if passed else '✗ FAIL'}")
    return {"ece": ece, "ece_pass": passed, "accuracy": accuracy}


# ══════════════════════════════════════════════════════════════════════════════
# Iteration 4 — Override rate gate (L46d boundary contract 3)
# ══════════════════════════════════════════════════════════════════════════════

def iteration_4_override_rate() -> dict:
    print(f"\n{'═'*62}")
    print("Iteration 4 — Override rate gate (L46d)")
    print("  Contract: hard gates (Zone 2) fire at expected frequency")
    print(f"{'═'*62}")
    n_calls = len(L46D_REQUESTS) * 2  # assess_risk + recommend_action per request
    print(f"\n  Phase 1 — Inference ({n_calls} LLM calls: risk + recommendation per request)")

    records, state = run_l46d_inference()
    override_rate  = compute_override_rate(records)
    lo, hi         = THRESHOLDS["override_rate_min"], THRESHOLDS["override_rate_max"]
    passed         = lo <= override_rate <= hi

    print(f"\n  Phase 2 — Evaluation (0 additional LLM calls)")
    print(f"  overrides:     {state.overrides}/{len(records)}")
    print(f"  override_rate: {override_rate:.3f}  [{lo:.2f}–{hi:.2f}]  {'✓ PASS' if passed else '✗ FAIL'}")
    return {"override_rate": override_rate, "override_rate_pass": passed}


# ══════════════════════════════════════════════════════════════════════════════
# Iteration 5 — Plan repair rate + Full CI Gate (L46c boundary contract 4)
# ══════════════════════════════════════════════════════════════════════════════

def iteration_5_repair_and_ci_gate(metrics: dict) -> dict:
    print(f"\n{'═'*62}")
    print("Iteration 5 — Plan repair rate + Full CI Gate (L46c)")
    print("  Contract: LLM plan quality + baseline capture / regression detection")
    print(f"{'═'*62}")
    print(f"\n  Phase 1 — Plan inference ({len(PLAN_EVAL_REQUESTS)} LLM calls)")

    plans       = run_l46c_inference()
    repair_rate = compute_repair_rate(plans)
    threshold   = THRESHOLDS["repair_rate_max"]
    passed      = repair_rate < threshold

    print(f"\n  Phase 2 — Evaluation (0 additional LLM calls)")
    print(f"  repair_rate: {repair_rate:.3f}  [< {threshold:.2f}]  {'✓ PASS' if passed else '✗ FAIL'}")

    # ── Full CI Gate ──────────────────────────────────────────────────────────
    all_pass = all([
        metrics.get("parse_rate_pass",    False),
        metrics.get("ece_pass",           False),
        metrics.get("override_rate_pass", False),
        passed,
    ])

    print(f"\n{'─'*62}")
    print("  Full CI Gate")
    print(f"{'─'*62}")
    _gate_line("parse_rate",    metrics["parse_rate"],
               f"≥ {THRESHOLDS['parse_rate_min']:.2f}",
               metrics["parse_rate_pass"])
    _gate_line("ece",           metrics.get("ece", 0.0),
               f"< {THRESHOLDS['ece_max']:.2f}",
               metrics.get("ece_pass", False))
    _gate_line("override_rate", metrics["override_rate"],
               f"in [{THRESHOLDS['override_rate_min']:.2f}–{THRESHOLDS['override_rate_max']:.2f}]",
               metrics["override_rate_pass"])
    _gate_line("repair_rate",   repair_rate,
               f"< {THRESHOLDS['repair_rate_max']:.2f}",
               passed)

    # ── Baseline capture / regression check ──────────────────────────────────
    snapshot = {
        "parse_rate":    metrics["parse_rate"],
        "ece":           metrics.get("ece", 0.0),
        "override_rate": metrics["override_rate"],
        "repair_rate":   repair_rate,
    }

    print(f"\n{'─'*62}")
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text())
        print(f"  Baseline loaded: {BASELINE_PATH.name}")
        _regression_check(snapshot, baseline)
    else:
        BASELINE_PATH.write_text(json.dumps(snapshot, indent=2))
        print(f"  Baseline captured → {BASELINE_PATH.name}")
        print("  Re-run after a model/prompt/config change to detect regression.")

    print(f"\n{'═'*62}")
    print(f"  {'ALL GATES PASS — deploy ✓' if all_pass else 'GATE FAILURE — block ✗'}")
    print(f"{'═'*62}")
    return {"repair_rate": repair_rate, "repair_rate_pass": passed, "all_pass": all_pass}


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 62)
    print("L49: Evals Harness — CI/CD for LLM Systems")
    print("parse rate | calibration | override rate | plan repair")
    print("=" * 62)

    # Iter 1: Run inference, build cache for Iters 2 + 3
    clf_cache = iteration_1_decoupling()           # 10 LLM calls

    # Iters 2 + 3: reuse clf_cache — 0 additional LLM calls (Fowler pattern)
    m2 = iteration_2_parse_rate(clf_cache)         # 0 LLM calls
    m3 = iteration_3_calibration(clf_cache)        # 0 LLM calls

    # Iter 4: trust boundary pipeline (new inference)
    m4 = iteration_4_override_rate()               # 12 LLM calls

    # Iter 5: plan repair + full CI gate + baseline (new inference)
    m5 = iteration_5_repair_and_ci_gate({**m2, **m3, **m4})  # 4 LLM calls

    print(f"""
{'='*62}
Key concepts demonstrated:

  Inference-testing decoupling (Fowler):
    {len(EVAL_CORPUS)} classify calls → cache → Iters 2 + 3 use same cache.
    Adding a new test type costs zero additional LLM calls.

  Four boundary contracts from L46:
    parse_rate    (L46b): classify_document returns valid JSON
    ece           (L46b): confidence ≈ accuracy frequency
    override_rate (L46d): Zone 2 hard gates fire at expected frequency
    repair_rate   (L46c): LLM plans fall within op vocabulary bounds

  CI gate pattern:
    First run:  baseline captured → {BASELINE_PATH.name}
    Subsequent: regression check — metric outside threshold → BLOCK

  L35 vs L49:
    L35 (Strands Evals SDK): tests agent output quality, TRACE_LEVEL pipeline
    L49 (this file):         tests boundary contracts in hybrid LLM/deterministic
    Different layers, different failure modes. Both needed in production.
""")

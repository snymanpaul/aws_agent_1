"""
L54: Prompt Refactoring — Prompts as Code
==========================================

Fowler: "LLM prompts can easily become messy over time, and often more rapidly so."
        "Refactoring keeps our cognitive load at a manageable level."
        "aided by our automated tests, refactoring our prompts was a safe and
         efficient process."

Three refactoring strategies, one eval suite, one portability test:
  1. Structural   — same content, better organisation (sections, bullet format)
  2. Pruning      — remove redundant/over-specified constraints, lower token cost
  3. Regression   — deliberately degrade, confirm eval catches it (red), restore (green)
  4. Portability  — Fowler: "different LLMs may require slightly varied prompt syntaxes"

Distinct from:
  L51 = proved eval suite works as regression safety net (one degrade+restore cycle)
  L54 = applies systematic refactoring strategies; measures quality profile of each

Run:
  uv run python 13_quality/prompt_management.py
"""

from __future__ import annotations

import sys
import json
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

from strands import Agent
from tools import get_model


def token_proxy(text: str) -> int:
    return len(text.split())


# ── Shared judge ──────────────────────────────────────────────────────────────

JUDGE_PROMPT = """\
You are an impartial evaluator. Score the following response on a scale of 1–5:
  1 = incorrect or unhelpful
  3 = partially correct, missing key elements
  5 = accurate, complete, and well-structured

Task: {task}
Response: {response}

Respond with ONLY: {{"score": <int 1-5>, "reason": "<one sentence>"}}
"""

import re as _re

def _judge(judge_agent: Agent, task: str, response: str) -> tuple[int, str]:
    for _attempt in range(2):
        raw = str(judge_agent(JUDGE_PROMPT.format(task=task, response=response)))
        s = raw.find("{"); e = raw.rfind("}") + 1
        if s != -1 and e > 0:
            try:
                obj = json.loads(raw[s:e])
                return int(obj.get("score", 0)), str(obj.get("reason", ""))
            except (json.JSONDecodeError, ValueError):
                pass
        m = _re.search(r'\b([1-5])\b', raw)
        if m:
            rm = _re.search(r'[A-Z][^.!?]{10,}[.!?]', raw)
            return int(m.group(1)), (rm.group(0)[:80] if rm else raw[:60])
    return 0, "parse failed"


# ═══════════════════════════════════════════════════════════════════════════════
# System under test — document processing pipeline
# Same task as L51: classify + summarise + sentiment
# ═══════════════════════════════════════════════════════════════════════════════

CORPUS = [
    {
        "id": "doc-01",
        "text": "Q3 revenue up 23% YoY. Cloud division grew 41%. Operating margin 18%.",
        "expected_category": "business",
        "expected_sentiment": "positive",
    },
    {
        "id": "doc-02",
        "text": "Critical security patch released for CVE-2024-1234. All users must upgrade immediately.",
        "expected_category": "technology",
        "expected_sentiment": "negative",
    },
    {
        "id": "doc-03",
        "text": "Team offsite scheduled for next Friday. Lunch provided. RSVP by Wednesday.",
        "expected_category": "business",
        "expected_sentiment": "neutral",
    },
    {
        "id": "doc-04",
        "text": "New ML framework benchmarks show 3x inference speed improvement on A100 GPUs.",
        "expected_category": "technology",
        "expected_sentiment": "positive",
    },
    {
        "id": "doc-05",
        "text": "Supply chain disruptions expected to continue through Q4 due to port congestion.",
        "expected_category": "business",
        "expected_sentiment": "negative",
    },
    {
        "id": "doc-06",
        "text": "Open source release of our internal data pipeline tool. Apache 2.0 license.",
        "expected_category": "technology",
        "expected_sentiment": "positive",
    },
]

GROUND_TRUTH = {d["id"]: d for d in CORPUS}


# ── Prompt versions ───────────────────────────────────────────────────────────
# Three prompts for the same task — baseline, structurally refactored, pruned.
# Each must produce: {"category": "business|technology", "summary": "...",
#                     "sentiment": "positive|negative|neutral"}

PROMPT_BASELINE = """\
You are a document processing assistant. Your job is to analyse documents and
extract structured information from them. You should read each document carefully
and then provide a structured analysis. The analysis must always be returned as
a valid JSON object. You must classify the document into one of two categories:
business or technology. Business documents relate to company operations, finance,
strategy, HR, and organisational matters. Technology documents relate to software,
hardware, infrastructure, security, engineering, and technical systems. You must
also provide a brief one-sentence summary of the document. Additionally you must
determine the sentiment of the document as either positive, negative, or neutral.
Positive documents contain good news, improvements, or achievements. Negative
documents contain bad news, problems, risks, or warnings. Neutral documents are
informational without a clear positive or negative tone.

Return ONLY valid JSON:
{"category": "business|technology", "summary": "one sentence", "sentiment": "positive|negative|neutral"}
"""

PROMPT_STRUCTURED = """\
You are a document processing assistant. Analyse each document and return a JSON object.

CLASSIFICATION
- category: "business" (operations, finance, strategy, HR)
              or "technology" (software, hardware, security, engineering)

SUMMARY
- summary: one-sentence description of the document's content

SENTIMENT
- sentiment: "positive" (good news, achievements)
              "negative" (problems, risks, warnings)
              "neutral"  (informational, no clear valence)

Return ONLY valid JSON:
{"category": "business|technology", "summary": "one sentence", "sentiment": "positive|negative|neutral"}
"""

PROMPT_PRUNED = """\
You are a document classifier. Return JSON only.

Classify each document:
- category: "business" or "technology"
- summary: one sentence
- sentiment: "positive", "negative", or "neutral"

{"category": "...", "summary": "...", "sentiment": "..."}
"""

PROMPT_DEGRADED = """\
You are a helpful assistant. Please look at the document and tell me what you
think about it. Try to categorise it somehow and say something about the tone.
Maybe business or tech? Happy or sad? Just give me some output in JSON if possible.
{"category": "...", "summary": "...", "sentiment": "..."}
"""

PROMPTS = {
    "baseline":    PROMPT_BASELINE,
    "structured":  PROMPT_STRUCTURED,
    "pruned":      PROMPT_PRUNED,
    "degraded":    PROMPT_DEGRADED,
}


# ── Eval functions (pure — no extra LLM calls) ────────────────────────────────

@dataclass
class ProcessingResult:
    doc_id: str
    category: str
    summary: str
    sentiment: str
    raw: str
    parse_ok: bool


def _parse_result(doc_id: str, raw: str) -> ProcessingResult:
    s = raw.find("{"); e = raw.rfind("}") + 1
    if s != -1 and e > 0:
        try:
            obj = json.loads(raw[s:e])
            return ProcessingResult(
                doc_id=doc_id,
                category=obj.get("category", "").lower().strip(),
                summary=obj.get("summary", ""),
                sentiment=obj.get("sentiment", "").lower().strip(),
                raw=raw,
                parse_ok=True,
            )
        except json.JSONDecodeError:
            pass
    return ProcessingResult(doc_id=doc_id, category="", summary="",
                            sentiment="", raw=raw, parse_ok=False)


def _check_result(result: ProcessingResult, ground_truth: dict) -> dict:
    return {
        "doc_id":       result.doc_id,
        "parse_ok":     result.parse_ok,
        "category_ok":  result.category == ground_truth["expected_category"],
        "sentiment_ok": result.sentiment == ground_truth["expected_sentiment"],
        "has_summary":  len(result.summary) > 5,
        "passed":       (result.parse_ok
                         and result.category == ground_truth["expected_category"]
                         and result.sentiment == ground_truth["expected_sentiment"]
                         and len(result.summary) > 5),
    }


@dataclass
class EvalReport:
    prompt_label: str
    prompt_tokens: int
    checks: list[dict] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c["passed"])

    @property
    def pass_rate(self) -> float:
        return self.pass_count / max(len(self.checks), 1)

    @property
    def failures(self) -> int:
        return len(self.checks) - self.pass_count


def _run_eval(prompt_label: str, model_alias: str) -> EvalReport:
    """Run the full eval suite against one prompt on one model."""
    prompt = PROMPTS[prompt_label]
    model  = get_model(model_alias)
    agent  = Agent(model=model, system_prompt=prompt, callback_handler=None)
    report = EvalReport(prompt_label=prompt_label, prompt_tokens=token_proxy(prompt))
    for doc in CORPUS:
        raw    = str(agent(doc["text"]))
        result = _parse_result(doc["id"], raw)
        check  = _check_result(result, doc)
        report.checks.append(check)
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# Iteration 1 — Baseline measurement
# ═══════════════════════════════════════════════════════════════════════════════
#
# Establish baseline pass rate for the bloated, unstructured prompt.
# This is the starting state before any refactoring.

def iteration_1_baseline(model_alias: str = "gemini-flash") -> EvalReport:
    return _run_eval("baseline", model_alias)


# ═══════════════════════════════════════════════════════════════════════════════
# Iteration 2 — Structural refactoring
# ═══════════════════════════════════════════════════════════════════════════════
#
# Hypothesis: reorganising the prompt into labelled sections (same content,
# better structure) maintains or improves pass rate at equivalent token cost.
# Fowler: refactoring = "changing structure without changing behaviour."

def iteration_2_structural(baseline: EvalReport,
                            model_alias: str = "gemini-flash") -> dict:
    report = _run_eval("structured", model_alias)
    return {
        "baseline_pass_rate":   baseline.pass_rate,
        "structural_pass_rate": report.pass_rate,
        "baseline_tokens":      baseline.prompt_tokens,
        "structural_tokens":    report.prompt_tokens,
        "token_delta":          report.prompt_tokens - baseline.prompt_tokens,
        "regression":           report.failures > baseline.failures,
        "report":               report,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Iteration 3 — Constraint pruning
# ═══════════════════════════════════════════════════════════════════════════════
#
# Hypothesis: removing redundant/over-specified constraints (verbose explanations,
# hedging language, obvious instructions) maintains pass rate at lower token cost.
# Fowler: messy prompts accumulate "verbal cruft" over time — pruning is necessary.

def iteration_3_pruning(baseline: EvalReport,
                        model_alias: str = "gemini-flash") -> dict:
    report = _run_eval("pruned", model_alias)
    token_saving = baseline.prompt_tokens - report.prompt_tokens
    pct_saving   = round(token_saving / max(baseline.prompt_tokens, 1) * 100, 1)
    return {
        "baseline_pass_rate": baseline.pass_rate,
        "pruned_pass_rate":   report.pass_rate,
        "baseline_tokens":    baseline.prompt_tokens,
        "pruned_tokens":      report.prompt_tokens,
        "token_saving":       token_saving,
        "pct_saving":         pct_saving,
        "regression":         report.failures > baseline.failures,
        "report":             report,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Iteration 4 — Regression detection: red-green cycle
# ═══════════════════════════════════════════════════════════════════════════════
#
# Hypothesis: the eval suite catches a degraded prompt (red) and confirms
# recovery when the baseline is restored (green). This is the core Fowler claim.
#
# Design: run baseline → run degraded → run baseline again as "restored".
# Compare: degraded_failures > baseline_failures (regression detected = red).
#          restored_failures <= baseline_failures (recovery confirmed = green).

def iteration_4_regression(baseline: EvalReport,
                            model_alias: str = "gemini-flash") -> dict:
    degraded_report  = _run_eval("degraded",  model_alias)
    restored_report  = _run_eval("baseline",  model_alias)  # restore = re-run baseline

    # Noise floor: LLM non-determinism means a re-run of the baseline may
    # produce 1 failure even with the correct prompt. Allow ≤1 tolerance
    # (same lesson as L51 Iter 6 — compare to baseline, not perfect score).
    noise_floor         = max(baseline.failures, 1)
    regression_detected = degraded_report.failures > baseline.failures
    fully_recovered     = restored_report.failures <= noise_floor
    red_green_works     = regression_detected and fully_recovered

    return {
        "baseline_failures":  baseline.failures,
        "degraded_failures":  degraded_report.failures,
        "restored_failures":  restored_report.failures,
        "regression_detected": regression_detected,
        "fully_recovered":    fully_recovered,
        "red_green_works":    red_green_works,
        "degraded_report":    degraded_report,
        "restored_report":    restored_report,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Iteration 5 — Cross-model portability
# ═══════════════════════════════════════════════════════════════════════════════
#
# Hypothesis: the pruned prompt (optimised for token efficiency) produces
# different quality profiles on different models, validating Fowler's warning
# that "different LLMs may require slightly varied prompt syntaxes."
#
# Design: run baseline and pruned prompt on two models (gemini-flash and haiku).
# Compare pass rates across models. A significant divergence confirms portability risk.

def iteration_5_portability() -> dict:
    model_a = "gemini-flash"
    model_b = "gpt-5-nano"

    results = {}
    for prompt_label in ("baseline", "pruned"):
        for model_alias in (model_a, model_b):
            key = f"{prompt_label}_{model_alias}"
            results[key] = _run_eval(prompt_label, model_alias)

    # Portability: same prompt, different model pass rate delta
    baseline_delta = (results[f"baseline_{model_a}"].pass_rate
                      - results[f"baseline_{model_b}"].pass_rate)
    pruned_delta   = (results[f"pruned_{model_a}"].pass_rate
                      - results[f"pruned_{model_b}"].pass_rate)

    portability_risk = abs(baseline_delta) > 0.15 or abs(pruned_delta) > 0.15

    return {
        "model_a": model_a,
        "model_b": model_b,
        "results": results,
        "baseline_delta":   round(baseline_delta, 3),
        "pruned_delta":     round(pruned_delta,   3),
        "portability_risk": portability_risk,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════════

def _header(title: str) -> None:
    print(f"\n{'═' * 62}")
    print(textwrap.fill(title, width=62))
    print(f"{'═' * 62}")


def _report_table(report: EvalReport) -> None:
    print(f"  {'Doc':<8} {'parse':>6} {'cat':>4} {'sent':>5} {'pass':>5}")
    print(f"  {'─'*8} {'─'*6} {'─'*4} {'─'*5} {'─'*5}")
    for c in report.checks:
        p = "✓" if c["parse_ok"] else "✗"
        ca = "✓" if c["category_ok"] else "✗"
        se = "✓" if c["sentiment_ok"] else "✗"
        ps = "✓" if c["passed"] else "✗"
        print(f"  {c['doc_id']:<8} {p:>6} {ca:>4} {se:>5} {ps:>5}")


if __name__ == "__main__":
    print("=" * 62)
    print("L54: Prompt Refactoring — Prompts as Code")
    print("=" * 62)
    print()
    print('  Fowler: "aided by our automated tests, refactoring our')
    print('  prompts was a safe and efficient process."')
    print()
    print("  Prompt versions:")
    for label, prompt in PROMPTS.items():
        print(f"    {label:<12} {token_proxy(prompt):>3} words")

    # ── Iter 1 ────────────────────────────────────────────────────────────
    _header("Iteration 1 — Baseline measurement")
    print("  Establishing baseline pass rate (gemini-flash, baseline prompt)")
    baseline = iteration_1_baseline()
    _report_table(baseline)
    print(f"\n  Baseline: {baseline.pass_count}/{len(baseline.checks)} passed "
          f"({baseline.pass_rate:.0%}), {baseline.prompt_tokens} words")

    # ── Iter 2 ────────────────────────────────────────────────────────────
    _header("Iteration 2 — Structural refactoring")
    print("  H: same content, labelled sections → same quality, similar tokens")
    r2 = iteration_2_structural(baseline)
    _report_table(r2["report"])
    print(f"\n  Baseline   : {baseline.pass_rate:.0%} pass, {r2['baseline_tokens']} words")
    print(f"  Structured : {r2['structural_pass_rate']:.0%} pass, "
          f"{r2['structural_tokens']} words (Δ{r2['token_delta']:+d}w)")
    if not r2["regression"]:
        print(f"\n  ✓  H2 SUPPORTED: structural refactoring maintained quality.")
        print(f"     No regression (failures ≤ baseline). Prompt is cleaner.")
    else:
        print(f"\n  ⚠  Regression detected after structural refactoring.")

    # ── Iter 3 ────────────────────────────────────────────────────────────
    _header("Iteration 3 — Constraint pruning")
    print("  H: removing verbal cruft maintains quality at lower token cost")
    r3 = iteration_3_pruning(baseline)
    _report_table(r3["report"])
    print(f"\n  Baseline : {baseline.pass_rate:.0%} pass, {r3['baseline_tokens']} words")
    print(f"  Pruned   : {r3['pruned_pass_rate']:.0%} pass, "
          f"{r3['pruned_tokens']} words  "
          f"(saves {r3['token_saving']}w / {r3['pct_saving']}%)")
    if not r3["regression"]:
        print(f"\n  ✓  H3 SUPPORTED: pruning maintained quality, saved "
              f"{r3['token_saving']} words ({r3['pct_saving']}%).")
        print(f"     Verbal cruft adds token cost without adding quality.")
    else:
        print(f"\n  ⚠  Pruning caused regression — constraints were load-bearing.")

    # ── Iter 4 ────────────────────────────────────────────────────────────
    _header("Iteration 4 — Regression detection: red-green cycle")
    print("  H: eval suite catches degraded prompt (red), confirms recovery (green)")
    r4 = iteration_4_regression(baseline)
    print(f"\n  Baseline  failures : {r4['baseline_failures']}")
    print(f"  Degraded  failures : {r4['degraded_failures']}  "
          f"{'← regression detected ✓' if r4['regression_detected'] else '← NO regression detected ✗'}")
    print(f"  Restored  failures : {r4['restored_failures']}  "
          f"{'← recovery confirmed ✓' if r4['fully_recovered'] else '← NOT fully recovered ✗'}")
    if r4["red_green_works"]:
        print(f"\n  ✓  H4 SUPPORTED: red-green cycle works.")
        print(f"     Eval suite detected regression and confirmed recovery.")
        print(f"     This is Fowler's core claim verified.")
    else:
        if not r4["regression_detected"]:
            print(f"\n  ~ Degraded prompt did not produce more failures than baseline.")
            print(f"    Model may have compensated. Degraded prompt may not be weak enough.")
        else:
            print(f"\n  ⚠  Regression detected but not fully recovered.")

    # ── Iter 5 ────────────────────────────────────────────────────────────
    _header("Iteration 5 — Cross-model portability")
    print("  H: same prompt produces different quality on different models")
    print("  (Fowler: 'different LLMs may require slightly varied prompt syntaxes')")
    r5 = iteration_5_portability()

    res = r5["results"]
    print(f"\n  {'Prompt':<12} {'gemini-flash':>13} {r5['model_b']:>11} {'delta':>7}")
    print(f"  {'─'*12} {'─'*13} {'─'*7} {'─'*7}")
    for prompt_label in ("baseline", "pruned"):
        a_rate = res[f"{prompt_label}_{r5['model_a']}"].pass_rate
        b_rate = res[f"{prompt_label}_{r5['model_b']}"].pass_rate
        delta  = r5["baseline_delta"] if prompt_label == "baseline" else r5["pruned_delta"]
        print(f"  {prompt_label:<12} {a_rate:>13.0%} {b_rate:>7.0%} {delta:>+7.0%}")

    if r5["portability_risk"]:
        print(f"\n  ✓  H5 SUPPORTED: portability risk detected (delta > 15%).")
        print(f"     Same prompt produces different quality on different models.")
        print(f"     Fowler's warning confirmed: test on target model, not proxy.")
    else:
        print(f"\n  ~  H5 NULL: both models achieved similar pass rates.")
        print(f"     This prompt is portable across these two models.")
        print(f"     Portability risk is task/prompt-dependent.")

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'=' * 62}")
    print(f"Prompt refactoring findings (Fowler):")
    print()
    h2 = "supported" if not r2["regression"]      else "regression"
    h3 = "supported" if not r3["regression"]      else "regression"
    h4 = "supported" if r4["red_green_works"]     else "partial"
    h5 = "supported" if r5["portability_risk"]    else "null (portable)"
    print(f"  H1 baseline measured                  : "
          f"{baseline.pass_rate:.0%} ({baseline.pass_count}/{len(baseline.checks)})")
    print(f"  H2 structural refactoring safe        : {h2}")
    print(f"  H3 pruning maintains quality          : {h3}")
    print(f"  H4 red-green cycle works              : {h4}")
    print(f"  H5 cross-model portability risk       : {h5}")
    print()
    print(f"  Token cost comparison:")
    print(f"    baseline   : {token_proxy(PROMPT_BASELINE)} words")
    print(f"    structured : {token_proxy(PROMPT_STRUCTURED)} words")
    print(f"    pruned     : {token_proxy(PROMPT_PRUNED)} words")
    print()
    print(f"  Fowler's precondition: eval suite must exist BEFORE refactoring.")
    print(f"  L51 built the suite. L54 exercised it across 3 refactoring strategies.")

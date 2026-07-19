"""
L55: Small Language Model Routing
==================================

ThoughtWorks Technology Radar Vol.33 (Assess, 2026):
  "consider SLMs as the default choice for agentic workflows"
  Qualifying condition: "narrow, repetitive tasks that don't require
  advanced reasoning"
  "when set up correctly, SLMs can perform as well as or even outperform LLMs"

Architecture:
  SLM tier (fast, cheap) = default
  Frontier LLM           = exception (complex reasoning only)
  Router                 = SLM call that decides which tier to use

SLM tier candidates (local via Ollama):
  llama3.2:3b         — baseline, already installed
  phi4-mini           — Microsoft Phi-4-mini 3.8B (official Ollama library)
  alibayram/smollm3   — HuggingFace SmolLM3 3B (community upload, 85K pulls)

Run:
  uv run python 13_quality/slm_routing.py
"""

from __future__ import annotations

import sys
import json
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

from strands import Agent
from tools import get_model

# ── Model tiers ───────────────────────────────────────────────────────────────
# True SLM: local models via Ollama (OpenAI-compatible API at localhost:11434/v1)
from strands.models.openai import OpenAIModel as _OpenAIModel

def _ollama_model(tag: str) -> _OpenAIModel:
    """Create an OpenAIModel for any local Ollama model tag."""
    return _OpenAIModel(
        model_id=tag,
        client_args={"base_url": "http://localhost:11434/v1", "api_key": "ollama"},
    )

def _slm_model() -> _OpenAIModel:
    return _ollama_model("llama3.2:3b")

SLM_ALIAS      = "llama3.2:3b (Ollama)"
FRONTIER_ALIAS = "gemini-2.5-pro"  # capable, expensive — frontier

# ── SLM candidates for Iter 5/6 model comparison ──────────────────────────────
CANDIDATE_SLMS = [
    ("llama3.2:3b",       "LLaMA 3.2 3B"),
    ("phi4-mini",         "Phi-4-mini 3.8B"),
    ("alibayram/smollm3", "SmolLM3 3B"),
]

# ── Token proxy ───────────────────────────────────────────────────────────────
def token_proxy(text: str) -> int:
    return len(text.split())

# ── Judge ─────────────────────────────────────────────────────────────────────
JUDGE_PROMPT = """\
Score the following response on a scale of 1-5:
  1 = incorrect or unhelpful
  3 = partially correct, missing key elements
  5 = accurate, complete, and well-structured

Task: {task}
Response: {response}

Respond ONLY: {{"score": <int 1-5>, "reason": "<one sentence>"}}
"""

def _judge(judge_agent: Agent, task: str, response: str) -> tuple[int, str]:
    for _ in range(2):
        raw = str(judge_agent(JUDGE_PROMPT.format(task=task, response=response)))
        s = raw.find("{"); e = raw.rfind("}") + 1
        if s != -1 and e > 0:
            try:
                obj = json.loads(raw[s:e])
                return int(obj.get("score", 0)), str(obj.get("reason", ""))
            except (json.JSONDecodeError, ValueError):
                pass
        m = re.search(r'\b([1-5])\b', raw)
        if m:
            rm = re.search(r'[A-Z][^.!?]{10,}[.!?]', raw)
            return int(m.group(1)), (rm.group(0)[:80] if rm else raw[:60])
    return 0, "parse failed"


# ═══════════════════════════════════════════════════════════════════════════════
# Task taxonomy
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Task:
    id: str
    tier: str           # "slm" or "frontier"
    prompt: str
    task_desc: str      # for judge

TASKS = [
    # ── Narrow / repetitive (SLM-appropriate) ─────────────────────────────────
    Task(
        id="narrow-01",
        tier="slm",
        prompt="Classify the sentiment of this tweet as positive, negative, or neutral. "
               "Reply with ONE word only.\n\n"
               "Tweet: 'Just got my order 3 days early — absolutely love this service!'",
        task_desc="One-word sentiment classification of a tweet",
    ),
    Task(
        id="narrow-02",
        tier="slm",
        prompt="Extract the following fields from the text below and return JSON only:\n"
               '{"name": "...", "date": "...", "amount": "..."}\n\n'
               "Text: Invoice #INV-2024-0891 issued to Acme Corp on 2024-11-15 "
               "for the amount of $4,250.00.",
        task_desc="JSON extraction of name, date, and amount from invoice text",
    ),
    Task(
        id="narrow-03",
        tier="slm",
        prompt="Route this support ticket to one of: billing, technical, account, general. "
               "Reply with ONE word only.\n\n"
               "Ticket: 'My API key stopped working after I regenerated it yesterday.'",
        task_desc="Single-word support ticket routing",
    ),
    # ── Complex / reasoning (frontier-appropriate) ─────────────────────────────
    Task(
        id="complex-01",
        tier="frontier",
        prompt="A SaaS company has 800 enterprise customers, 23% YoY revenue growth, "
               "but 18% annual churn and a Net Promoter Score of 12. A competitor just "
               "launched at 40% lower price point. Provide a 3-part strategic response: "
               "(1) root cause of churn, (2) competitive positioning, (3) 90-day action plan.",
        task_desc="Multi-part strategic analysis with root cause, positioning, and action plan",
    ),
    Task(
        id="complex-02",
        prompt="Two internal reports conflict: Report A says the new ML pipeline reduced "
               "inference latency by 34% in staging. Report B says production latency "
               "increased 12% after the same deployment. Identify 3 plausible explanations "
               "for the discrepancy, rank them by likelihood, and recommend what data to "
               "collect to resolve it.",
        tier="frontier",
        task_desc="Conflicting evidence synthesis: 3 ranked hypotheses with investigation plan",
    ),
    Task(
        id="complex-03",
        tier="frontier",
        prompt="Your company must choose between: (A) lay off 15% of staff to extend runway "
               "18 months, (B) raise a down-round at 60% valuation cut to preserve headcount, "
               "or (C) sell a non-core product line that generates 20% of revenue. Evaluate "
               "each option across: employee impact, investor relations, long-term strategy. "
               "Recommend one with explicit trade-off acknowledgment.",
        task_desc="Multi-stakeholder ethical trade-off with explicit recommendation and trade-offs",
    ),
]


# ═══════════════════════════════════════════════════════════════════════════════
# Iteration 1 — Benchmark: SLM vs frontier on narrow tasks
# ═══════════════════════════════════════════════════════════════════════════════
#
# H1: SLM-tier produces equivalent quality to frontier on narrow/repetitive tasks.
# ThoughtWorks: "SLMs can perform as well as or even outperform LLMs" on
# "narrow, repetitive tasks that don't require advanced reasoning."

def iteration_1_narrow_tasks() -> dict:
    judge      = Agent(model=get_model("gemini-flash"), callback_handler=None)
    slm_agent  = Agent(model=_slm_model(),               callback_handler=None)
    llm_agent  = Agent(model=get_model(FRONTIER_ALIAS), callback_handler=None)

    narrow_tasks = [t for t in TASKS if t.tier == "slm"]
    results = []

    for task in narrow_tasks:
        slm_answer = str(slm_agent(task.prompt))
        llm_answer = str(llm_agent(task.prompt))
        slm_score, slm_reason = _judge(judge, task.task_desc, slm_answer)
        llm_score, llm_reason = _judge(judge, task.task_desc, llm_answer)
        results.append({
            "task_id":    task.id,
            "slm_score":  slm_score,
            "llm_score":  llm_score,
            "slm_reason": slm_reason[:70],
            "llm_reason": llm_reason[:70],
            "slm_wins":   slm_score >= llm_score,
            "equivalent": abs(slm_score - llm_score) <= 1,
        })

    avg_slm = sum(r["slm_score"] for r in results) / len(results)
    avg_llm = sum(r["llm_score"] for r in results) / len(results)
    all_equivalent = all(r["equivalent"] for r in results)

    return {
        "results":       results,
        "avg_slm_score": round(avg_slm, 2),
        "avg_llm_score": round(avg_llm, 2),
        "score_delta":   round(avg_slm - avg_llm, 2),
        "h1_supported":  all_equivalent,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Iteration 2 — Benchmark: SLM vs frontier on complex tasks
# ═══════════════════════════════════════════════════════════════════════════════
#
# H2: Frontier model outperforms SLM on complex reasoning tasks.
# This is the complementary test to H1 — confirms the tier distinction is real.

def iteration_2_complex_tasks() -> dict:
    judge      = Agent(model=get_model("gemini-flash"), callback_handler=None)
    slm_agent  = Agent(model=_slm_model(),               callback_handler=None)
    llm_agent  = Agent(model=get_model(FRONTIER_ALIAS), callback_handler=None)

    complex_tasks = [t for t in TASKS if t.tier == "frontier"]
    results = []

    for task in complex_tasks:
        slm_answer = str(slm_agent(task.prompt))
        llm_answer = str(llm_agent(task.prompt))
        slm_score, slm_reason = _judge(judge, task.task_desc, slm_answer)
        llm_score, llm_reason = _judge(judge, task.task_desc, llm_answer)
        results.append({
            "task_id":        task.id,
            "slm_score":      slm_score,
            "llm_score":      llm_score,
            "slm_reason":     slm_reason[:70],
            "llm_reason":     llm_reason[:70],
            "frontier_wins":  llm_score > slm_score,
        })

    avg_slm = sum(r["slm_score"] for r in results) / len(results)
    avg_llm = sum(r["llm_score"] for r in results) / len(results)

    return {
        "results":       results,
        "avg_slm_score": round(avg_slm, 2),
        "avg_llm_score": round(avg_llm, 2),
        "score_delta":   round(avg_llm - avg_slm, 2),
        "h2_supported":  avg_llm > avg_slm,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Iteration 3 — SLM router: complexity classifier
# ═══════════════════════════════════════════════════════════════════════════════
#
# H3: An SLM-based router correctly classifies task complexity (narrow vs complex)
# at lower cost than always using the frontier for routing decisions.
# ThoughtWorks: the routing decision itself is a narrow/repetitive task — SLM fits.

ROUTER_PROMPT = """\
Classify this task as "slm" (narrow, repetitive, no advanced reasoning needed)
or "frontier" (complex reasoning, multi-step analysis, nuanced judgment required).

"slm" tasks: classification, extraction, formatting, single-step lookup
"frontier" tasks: strategic analysis, conflicting evidence, ethical trade-offs,
                  multi-stakeholder decisions, synthesis across multiple sources

Task: {task}

Respond ONLY: {{"tier": "slm"}} or {{"tier": "frontier"}}
"""

def _route(router_agent: Agent, task_prompt: str) -> str:
    raw = str(router_agent(ROUTER_PROMPT.format(task=task_prompt[:300])))
    s = raw.find("{"); e = raw.rfind("}") + 1
    if s != -1 and e > 0:
        try:
            obj = json.loads(raw[s:e])
            tier = obj.get("tier", "").lower().strip()
            if tier in ("slm", "frontier"):
                return tier
        except (json.JSONDecodeError, ValueError):
            pass
    return "frontier"  # safe default: escalate on parse failure


def iteration_3_router() -> dict:
    router = Agent(model=_slm_model(), callback_handler=None)  # true SLM routes

    results = []
    for task in TASKS:
        predicted = _route(router, task.prompt)
        correct   = predicted == task.tier
        results.append({
            "task_id":   task.id,
            "expected":  task.tier,
            "predicted": predicted,
            "correct":   correct,
        })

    accuracy = sum(1 for r in results if r["correct"]) / len(results)
    slm_correct      = sum(1 for r in results if r["expected"] == "slm"      and r["correct"])
    frontier_correct = sum(1 for r in results if r["expected"] == "frontier" and r["correct"])
    slm_total        = sum(1 for r in results if r["expected"] == "slm")
    frontier_total   = sum(1 for r in results if r["expected"] == "frontier")

    return {
        "results":          results,
        "accuracy":         round(accuracy, 3),
        "slm_recall":       round(slm_correct / max(slm_total, 1), 3),
        "frontier_recall":  round(frontier_correct / max(frontier_total, 1), 3),
        "h3_supported":     accuracy >= 0.80,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Iteration 4 — End-to-end: SLM-first vs always-frontier
# ═══════════════════════════════════════════════════════════════════════════════
#
# H4: SLM-first routing achieves measurable cost savings vs always-frontier
# on a mixed workload (3 narrow + 3 complex tasks), at equivalent quality.
#
# Cost proxy: LLM calls * model_weight
#   SLM call weight    = 1
#   Frontier call weight = 5  (typical cost ratio in production)
# Router call: 1 SLM call per task (routing decision)

SLM_WEIGHT      = 1
FRONTIER_WEIGHT = 5

def iteration_4_end_to_end() -> dict:
    router         = Agent(model=_slm_model(),               callback_handler=None)
    slm_agent      = Agent(model=_slm_model(),               callback_handler=None)
    frontier_agent = Agent(model=get_model(FRONTIER_ALIAS),  callback_handler=None)
    judge          = Agent(model=get_model("gemini-flash"),   callback_handler=None)

    routed_results   = []
    frontier_results = []

    for task in TASKS:
        # Always-frontier baseline
        fa = str(frontier_agent(task.prompt))
        fs, _ = _judge(judge, task.task_desc, fa)
        frontier_results.append({"task_id": task.id, "score": fs,
                                  "cost": FRONTIER_WEIGHT})

        # SLM-first: route then execute
        tier = _route(router, task.prompt)
        if tier == "slm":
            ra = str(slm_agent(task.prompt))
            cost = SLM_WEIGHT + SLM_WEIGHT   # router + slm execution
        else:
            ra = str(frontier_agent(task.prompt))
            cost = SLM_WEIGHT + FRONTIER_WEIGHT  # router + frontier execution

        rs, _ = _judge(judge, task.task_desc, ra)
        routed_results.append({"task_id": task.id, "tier_used": tier,
                                "score": rs, "cost": cost})

    always_cost   = sum(r["cost"] for r in frontier_results)
    routed_cost   = sum(r["cost"] for r in routed_results)
    cost_saving   = always_cost - routed_cost
    pct_saving    = round(cost_saving / max(always_cost, 1) * 100, 1)

    avg_frontier_score = sum(r["score"] for r in frontier_results) / len(frontier_results)
    avg_routed_score   = sum(r["score"] for r in routed_results)   / len(routed_results)

    return {
        "frontier_results": frontier_results,
        "routed_results":   routed_results,
        "always_cost":      always_cost,
        "routed_cost":      routed_cost,
        "cost_saving":      cost_saving,
        "pct_saving":       pct_saving,
        "avg_frontier_score": round(avg_frontier_score, 2),
        "avg_routed_score":   round(avg_routed_score,   2),
        "quality_maintained": abs(avg_routed_score - avg_frontier_score) <= 0.5,
        "h4_supported":       cost_saving > 0 and abs(avg_routed_score - avg_frontier_score) <= 0.5,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Iteration 5 — Model comparison: LLaMA 3.2 3B vs Phi-4-mini vs SmolLM3
# ═══════════════════════════════════════════════════════════════════════════════
#
# Compare the three SLM candidates across all four dimensions:
#   narrow_avg   — avg score on 3 narrow tasks (quality parity with frontier)
#   complex_avg  — avg score on 3 complex tasks (capability gap from frontier)
#   h1_ok        — narrow parity: all tasks within 1 point of frontier
#   cap_gap      — complex gap: frontier_avg - slm_avg (higher = more gap)
#   router_acc   — routing accuracy when used as the router
#
# Frontier baseline is run once and reused across all candidates.

def _benchmark_one_slm(tag: str, alias: str, frontier_agent: Agent,
                       judge: Agent) -> dict:
    """Run H1/H2/H3 benchmarks for a single SLM candidate."""
    slm_agent = Agent(model=_ollama_model(tag), callback_handler=None)

    # ── Narrow tasks (H1) ──────────────────────────────────────────────────
    narrow_tasks = [t for t in TASKS if t.tier == "slm"]
    narrow_results = []
    for task in narrow_tasks:
        slm_ans = str(slm_agent(task.prompt))
        slm_score, _ = _judge(judge, task.task_desc, slm_ans)
        fr_ans = str(frontier_agent(task.prompt))
        fr_score, _  = _judge(judge, task.task_desc, fr_ans)
        narrow_results.append({
            "task_id":    task.id,
            "slm_score":  slm_score,
            "fr_score":   fr_score,
            "equivalent": abs(slm_score - fr_score) <= 1,
        })

    narrow_slm_avg = sum(r["slm_score"] for r in narrow_results) / len(narrow_results)
    narrow_fr_avg  = sum(r["fr_score"]  for r in narrow_results) / len(narrow_results)
    h1_ok = all(r["equivalent"] for r in narrow_results)

    # ── Complex tasks (H2) ────────────────────────────────────────────────
    complex_tasks = [t for t in TASKS if t.tier == "frontier"]
    complex_results = []
    for task in complex_tasks:
        slm_ans = str(slm_agent(task.prompt))
        slm_score, _ = _judge(judge, task.task_desc, slm_ans)
        fr_ans = str(frontier_agent(task.prompt))
        fr_score, _  = _judge(judge, task.task_desc, fr_ans)
        complex_results.append({
            "task_id":   task.id,
            "slm_score": slm_score,
            "fr_score":  fr_score,
        })

    complex_slm_avg = sum(r["slm_score"] for r in complex_results) / len(complex_results)
    complex_fr_avg  = sum(r["fr_score"]  for r in complex_results) / len(complex_results)
    cap_gap = round(complex_fr_avg - complex_slm_avg, 2)

    # ── Router accuracy (H3) ──────────────────────────────────────────────
    router = Agent(model=_ollama_model(tag), callback_handler=None)
    correct = sum(1 for t in TASKS if _route(router, t.prompt) == t.tier)
    router_acc = correct / len(TASKS)

    return {
        "tag":             tag,
        "alias":           alias,
        "narrow_slm_avg":  round(narrow_slm_avg, 2),
        "narrow_fr_avg":   round(narrow_fr_avg, 2),
        "h1_ok":           h1_ok,
        "complex_slm_avg": round(complex_slm_avg, 2),
        "complex_fr_avg":  round(complex_fr_avg, 2),
        "cap_gap":         cap_gap,
        "router_acc":      round(router_acc, 3),
        "h2_ok":           complex_fr_avg > complex_slm_avg,
        "h3_ok":           router_acc >= 0.80,
    }


def iteration_5_model_comparison() -> list[dict]:
    judge    = Agent(model=get_model("gemini-flash"), callback_handler=None)
    frontier = Agent(model=get_model(FRONTIER_ALIAS), callback_handler=None)

    results = []
    for tag, alias in CANDIDATE_SLMS:
        print(f"\n  Benchmarking {alias} ({tag}) …")
        try:
            r = _benchmark_one_slm(tag, alias, frontier, judge)
            results.append(r)
            print(f"    narrow {r['narrow_slm_avg']}/5  "
                  f"complex {r['complex_slm_avg']}/5  "
                  f"cap_gap {r['cap_gap']:+.2f}  "
                  f"router {r['router_acc']:.0%}")
        except Exception as exc:
            print(f"    ERROR: {exc}")
            results.append({"tag": tag, "alias": alias, "error": str(exc)})
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Iteration 6 — H4 for the winning SLM model
# ═══════════════════════════════════════════════════════════════════════════════
#
# Pick the winner from Iter 5 (best narrow_avg, tie-break: smallest cap_gap).
# Re-run the full end-to-end cost/quality test from Iter 4 with the winner.
# Compare side-by-side with LLaMA 3.2 3B (Iter 4 baseline).

def iteration_6_winner_end_to_end(tag: str, alias: str) -> dict:
    router         = Agent(model=_ollama_model(tag),         callback_handler=None)
    slm_agent      = Agent(model=_ollama_model(tag),         callback_handler=None)
    frontier_agent = Agent(model=get_model(FRONTIER_ALIAS),  callback_handler=None)
    judge          = Agent(model=get_model("gemini-flash"),  callback_handler=None)

    routed_results   = []
    frontier_results = []

    for task in TASKS:
        fa = str(frontier_agent(task.prompt))
        fs, _ = _judge(judge, task.task_desc, fa)
        frontier_results.append({"task_id": task.id, "score": fs,
                                  "cost": FRONTIER_WEIGHT})

        tier = _route(router, task.prompt)
        if tier == "slm":
            ra   = str(slm_agent(task.prompt))
            cost = SLM_WEIGHT * 2
        else:
            ra   = str(frontier_agent(task.prompt))
            cost = SLM_WEIGHT + FRONTIER_WEIGHT

        rs, _ = _judge(judge, task.task_desc, ra)
        routed_results.append({"task_id": task.id, "tier_used": tier,
                                "score": rs, "cost": cost})

    always_cost = sum(r["cost"] for r in frontier_results)
    routed_cost = sum(r["cost"] for r in routed_results)
    pct_saving  = round((always_cost - routed_cost) / max(always_cost, 1) * 100, 1)
    avg_fr      = sum(r["score"] for r in frontier_results) / len(frontier_results)
    avg_rt      = sum(r["score"] for r in routed_results)   / len(routed_results)
    quality_ok  = abs(avg_rt - avg_fr) <= 0.5

    return {
        "tag":              tag,
        "alias":            alias,
        "always_cost":      always_cost,
        "routed_cost":      routed_cost,
        "pct_saving":       pct_saving,
        "avg_frontier":     round(avg_fr, 2),
        "avg_routed":       round(avg_rt, 2),
        "quality_ok":       quality_ok,
        "h4_supported":     (always_cost - routed_cost) > 0 and quality_ok,
        "routed_results":   routed_results,
        "frontier_results": frontier_results,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════════

def _header(title: str) -> None:
    print(f"\n{'═' * 62}")
    print(textwrap.fill(title, width=62))
    print(f"{'═' * 62}")


if __name__ == "__main__":
    print("=" * 62)
    print("L55: Small Language Model Routing")
    print("=" * 62)
    print()
    print("  ThoughtWorks (Assess): 'consider SLMs as the default")
    print("  choice for agentic workflows'")
    print()
    print(f"  SLM tier  : {SLM_ALIAS}")
    print(f"  Frontier  : {FRONTIER_ALIAS}")
    print()
    print("  Task taxonomy:")
    for t in TASKS:
        print(f"    [{t.tier:>8}]  {t.id}  {t.prompt[:50]}...")

    # ── Iter 1 ───────────────────────────────────────────────────────────────
    _header("Iteration 1 — SLM vs frontier on narrow/repetitive tasks")
    print("  H1: SLM performs equivalently to frontier on narrow tasks")
    r1 = iteration_1_narrow_tasks()

    print(f"\n  {'Task':<12} {'SLM':>5} {'LLM':>5} {'Equiv':>6}")
    print(f"  {'─'*12} {'─'*5} {'─'*5} {'─'*6}")
    for r in r1["results"]:
        eq = "✓" if r["equivalent"] else "✗"
        print(f"  {r['task_id']:<12} {r['slm_score']:>5}/5 {r['llm_score']:>5}/5 {eq:>6}")
    print(f"\n  Avg SLM: {r1['avg_slm_score']}/5  |  Avg frontier: {r1['avg_llm_score']}/5  "
          f"|  Delta: {r1['score_delta']:+.2f}")
    if r1["h1_supported"]:
        print(f"\n  ✓  H1 SUPPORTED: SLM equivalent to frontier on narrow tasks (all delta ≤ 1).")
        print(f"     ThoughtWorks 'perform as well as' claim confirmed for these task types.")
    else:
        print(f"\n  ~  H1 PARTIAL: not all narrow tasks were equivalent (delta > 1 on some).")

    # ── Iter 2 ───────────────────────────────────────────────────────────────
    _header("Iteration 2 — SLM vs frontier on complex reasoning tasks")
    print("  H2: Frontier outperforms SLM on complex reasoning")
    r2 = iteration_2_complex_tasks()

    print(f"\n  {'Task':<12} {'SLM':>5} {'Frontier':>9} {'F>S':>4}")
    print(f"  {'─'*12} {'─'*5} {'─'*9} {'─'*4}")
    for r in r2["results"]:
        fw = "✓" if r["frontier_wins"] else "✗"
        print(f"  {r['task_id']:<12} {r['slm_score']:>5}/5 {r['llm_score']:>9}/5 {fw:>4}")
    print(f"\n  Avg SLM: {r2['avg_slm_score']}/5  |  Avg frontier: {r2['avg_llm_score']}/5  "
          f"|  Frontier advantage: {r2['score_delta']:+.2f}")
    if r2["h2_supported"]:
        print(f"\n  ✓  H2 SUPPORTED: frontier outperforms SLM on complex reasoning.")
        print(f"     Tier distinction is real — escalation to frontier is justified.")
    else:
        print(f"\n  ~  H2 NULL: SLM matched frontier on complex tasks in this run.")
        print(f"     Task complexity may not be sufficient to expose capability gap.")

    # ── Iter 3 ───────────────────────────────────────────────────────────────
    _header("Iteration 3 — SLM router: complexity classification accuracy")
    print("  H3: SLM router correctly routes tasks at ≥80% accuracy")
    r3 = iteration_3_router()

    print(f"\n  {'Task':<12} {'expected':>9} {'predicted':>10} {'ok':>4}")
    print(f"  {'─'*12} {'─'*9} {'─'*10} {'─'*4}")
    for r in r3["results"]:
        ok = "✓" if r["correct"] else "✗"
        print(f"  {r['task_id']:<12} {r['expected']:>9} {r['predicted']:>10} {ok:>4}")
    print(f"\n  Overall accuracy  : {r3['accuracy']:.0%}")
    print(f"  SLM task recall   : {r3['slm_recall']:.0%}")
    print(f"  Frontier recall   : {r3['frontier_recall']:.0%}")
    if r3["h3_supported"]:
        print(f"\n  ✓  H3 SUPPORTED: router accuracy ≥ 80%.")
        print(f"     An SLM can reliably classify task complexity at low cost.")
    else:
        print(f"\n  ~  H3 NOT MET: router accuracy < 80%.")
        print(f"     Routing errors may negate cost savings (missed frontier tasks).")

    # ── Iter 4 ───────────────────────────────────────────────────────────────
    _header("Iteration 4 — End-to-end: SLM-first vs always-frontier cost")
    print("  H4: SLM-first routing saves cost at equivalent quality")
    print(f"  Cost weights: SLM={SLM_WEIGHT}x, Frontier={FRONTIER_WEIGHT}x, Router=SLM call")
    r4 = iteration_4_end_to_end()

    print(f"\n  {'Task':<12} {'tier used':>10} {'routed cost':>12} {'frontier cost':>14}")
    print(f"  {'─'*12} {'─'*10} {'─'*12} {'─'*14}")
    for ro, fr in zip(r4["routed_results"], r4["frontier_results"]):
        print(f"  {ro['task_id']:<12} {ro['tier_used']:>10} {ro['cost']:>12} {fr['cost']:>14}")
    print(f"\n  Total cost — always-frontier : {r4['always_cost']} units")
    print(f"  Total cost — SLM-first routed: {r4['routed_cost']} units")
    print(f"  Saving                       : {r4['cost_saving']} units ({r4['pct_saving']}%)")
    print(f"\n  Quality:")
    print(f"  Avg always-frontier score : {r4['avg_frontier_score']}/5")
    print(f"  Avg SLM-first score       : {r4['avg_routed_score']}/5")
    if r4["h4_supported"]:
        print(f"\n  ✓  H4 SUPPORTED: SLM-first saves {r4['pct_saving']}% cost")
        print(f"     at equivalent quality (avg delta ≤ 0.5).")
        print(f"     ThoughtWorks: SLM as default, frontier as exception.")
    else:
        if r4["cost_saving"] <= 0:
            print(f"\n  ~  H4: No cost saving — router routed all tasks to frontier.")
        else:
            print(f"\n  ⚠  H4: Cost saved but quality degraded (avg delta > 0.5).")

    # ── Iter 5 ───────────────────────────────────────────────────────────────
    _header("Iteration 5 — SLM model comparison: LLaMA vs Phi-4-mini vs SmolLM3")
    print("  Benchmark all three candidates: narrow quality, complex gap, router accuracy")
    r5_list = iteration_5_model_comparison()

    valid5 = [r for r in r5_list if "error" not in r]
    errors5 = [r for r in r5_list if "error" in r]

    print(f"\n  {'Model':<22} {'Narrow':>7} {'Complex':>8} {'Cap Gap':>8} {'Router':>7} {'H1':>4} {'H3':>4}")
    print(f"  {'─'*22} {'─'*7} {'─'*8} {'─'*8} {'─'*7} {'─'*4} {'─'*4}")
    for r in valid5:
        h1 = "✓" if r["h1_ok"] else "✗"
        h3 = "✓" if r["h3_ok"] else "✗"
        print(f"  {r['alias']:<22} {r['narrow_slm_avg']:>5.2f}/5 "
              f"{r['complex_slm_avg']:>6.2f}/5 "
              f"{r['cap_gap']:>+8.2f} "
              f"{r['router_acc']:>6.0%} "
              f"{h1:>4} {h3:>4}")
    for r in errors5:
        print(f"  {r['alias']:<22}  ERROR: {r['error'][:40]}")

    # Pick winner: best narrow_avg, tie-break by smallest cap_gap (closer to frontier)
    winner5 = max(valid5, key=lambda r: (r["narrow_slm_avg"], -r["cap_gap"])) if valid5 else None

    if winner5:
        print(f"\n  Winner: {winner5['alias']} "
              f"(narrow {winner5['narrow_slm_avg']}/5, cap_gap {winner5['cap_gap']:+.2f})")

    # Frontier reference row
    if valid5:
        fr_narrow  = valid5[0]["narrow_fr_avg"]
        fr_complex = valid5[0]["complex_fr_avg"]
        print(f"\n  Frontier ref ({FRONTIER_ALIAS}): "
              f"narrow {fr_narrow}/5  complex {fr_complex}/5")

    # ── Iter 6 ───────────────────────────────────────────────────────────────
    if winner5 and winner5["tag"] != "llama3.2:3b":
        _header(f"Iteration 6 — End-to-end H4 with winner: {winner5['alias']}")
        print(f"  Re-run full cost/quality pipeline with {winner5['alias']}")
        r6 = iteration_6_winner_end_to_end(winner5["tag"], winner5["alias"])

        print(f"\n  {'Task':<12} {'tier used':>10} {'routed cost':>12} {'frontier cost':>14}")
        print(f"  {'─'*12} {'─'*10} {'─'*12} {'─'*14}")
        for ro, fr in zip(r6["routed_results"], r6["frontier_results"]):
            print(f"  {ro['task_id']:<12} {ro['tier_used']:>10} {ro['cost']:>12} {fr['cost']:>14}")
        print(f"\n  Total cost — always-frontier : {r6['always_cost']} units")
        print(f"  Total cost — SLM-first routed: {r6['routed_cost']} units")
        print(f"  Saving                       : {r6['pct_saving']}%")
        print(f"\n  Quality — frontier avg: {r6['avg_frontier']}/5  "
              f"routed avg: {r6['avg_routed']}/5")
        status6 = "✓ SUPPORTED" if r6["h4_supported"] else ("⚠ MIXED" if r6["pct_saving"] > 0 else "✗ NO SAVING")
        print(f"  H4: {status6}")
        r6_for_summary = r6
    else:
        if winner5 and winner5["tag"] == "llama3.2:3b":
            print(f"\n  Winner is LLaMA 3.2 3B — Iter 4 already covers H4 for this model.")
        r6_for_summary = None

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'=' * 62}")
    print(f"SLM routing findings (ThoughtWorks Assess):")
    print()
    print(f"  Iters 1-4 ({SLM_ALIAS}):")
    print(f"  H1 SLM ≡ frontier on narrow tasks  : "
          f"{'supported' if r1['h1_supported'] else 'partial'}")
    print(f"  H2 frontier > SLM on complex tasks  : "
          f"{'supported' if r2['h2_supported'] else 'null'}")
    print(f"  H3 SLM router accuracy ≥ 80%        : "
          f"{'supported' if r3['h3_supported'] else 'not met'} ({r3['accuracy']:.0%})")
    print(f"  H4 SLM-first saves cost             : "
          f"{'supported' if r4['h4_supported'] else 'mixed'} ({r4['pct_saving']}% saving)")
    print()
    if valid5:
        print(f"  Iter 5 — Model comparison:")
        print(f"  {'Model':<22} {'Narrow':>6} {'Complex':>7} {'Gap':>6} {'Router':>7}")
        for r in valid5:
            print(f"  {r['alias']:<22} {r['narrow_slm_avg']:>4.2f}/5 "
                  f"{r['complex_slm_avg']:>5.2f}/5 "
                  f"{r['cap_gap']:>+6.2f} "
                  f"{r['router_acc']:>6.0%}")
        if winner5:
            print(f"  → Winner: {winner5['alias']}")
    if r6_for_summary:
        print()
        print(f"  Iter 6 — H4 with {r6_for_summary['alias']}:")
        print(f"  Cost saving: {r6_for_summary['pct_saving']}%  "
              f"quality: {r6_for_summary['avg_routed']}/5 vs {r6_for_summary['avg_frontier']}/5  "
              f"H4: {'✓' if r6_for_summary['h4_supported'] else '⚠ mixed'}")
    print()
    print(f"  ThoughtWorks ring: Assess — evaluate for your situation.")
    print(f"  Qualifying condition: narrow, repetitive tasks,")
    print(f"  no advanced reasoning needed.")
    print(f"  SLM tier (local, Ollama): {SLM_ALIAS}")
    print(f"  Frontier: {FRONTIER_ALIAS}")

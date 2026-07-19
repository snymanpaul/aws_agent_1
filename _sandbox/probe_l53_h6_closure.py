"""
Probe: L53 H6 closure — calibrated combined stack using gemini-flash.

Three-way comparison:
  naive:          verbose prompt + raw history + always-load catalog
  over-compressed: minimal prompt + 120-char notes + JIT
  calibrated:     minimal prompt + 400-char notes + JIT   <-- H9 target

All models: gemini-flash (no Anthropic credits needed).
"""

from __future__ import annotations
import sys, json, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from strands import Agent
from tools import get_model

MODEL = "gemini-flash"

# ── Shared data (copied from context_engineering.py) ──────────────────────────

ANALYSIS_PRODUCT = """\
Product: CloudSync Pro — enterprise file synchronisation platform
Features: real-time sync, version history (90 days), SSO, audit logs, 25GB/user
Pricing: $12/user/month (min 10 users)
Recent issues: 3 reported sync conflicts in last 30 days
Customer count: 847 enterprise accounts
"""

ANALYSIS_STEPS = [
    ("strengths",       "List 2-3 key strengths for enterprise customers. Be concise."),
    ("risks",           "Identify 2 key risks or weaknesses."),
    ("competitive",     "Name 2 likely competitors and one differentiator vs each. One sentence each."),
    ("recommendation",  "Give a one-sentence go/no-go recommendation for a 50-person company."),
    ("executive_summary", "Write a 3-sentence executive summary covering strengths, risks, and recommendation."),
]

PRODUCT_CATALOG = """\
PRODUCT CATALOG:
- CloudSync Pro: $12/user/month, file sync, SSO, 90-day history
- DataVault: $8/user/month, encrypted storage, compliance reports
- BuildPipeline: $20/user/month, CI/CD, 50 build minutes/day
- MonitorGrid: $5/user/month, uptime monitoring, alerting
"""

NAIVE_SYSTEM_PROMPT = """\
You are an experienced senior product analyst with 15 years of experience
evaluating enterprise software products. Your analysis must be comprehensive,
evidence-based, and structured for executive consumption. You always:
1. Provide context before conclusions
2. Cite specific product features in your analysis
3. Use quantitative data wherever available
4. Distinguish between facts and inferences
5. Consider competitive landscape
6. Include risk-adjusted recommendations
Reply in a professional, polished tone suitable for C-suite presentation.
"""

OPTIMISED_SYSTEM_PROMPT = "You are a product analyst. Be concise and factual."

JUDGE_PROMPT = """\
You are an impartial evaluator. Score the following response on a scale of 1-5:
  1 = incorrect or unhelpful
  3 = partially correct, missing key elements
  5 = accurate, complete, and well-structured

Task description: {task}
Response: {response}

Respond with ONLY: {{"score": <int 1-5>, "reason": "<one sentence>"}}
"""

def token_proxy(text: str) -> int:
    return len(text.split())

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
        m = re.search(r'\b([1-5])\b', raw)
        if m:
            reason_match = re.search(r'[A-Z][^.!?]{10,}[.!?]', raw)
            reason = reason_match.group(0)[:80] if reason_match else raw[:60]
            return int(m.group(1)), reason
    return 0, "parse failed"

# ── Three pipeline implementations ────────────────────────────────────────────

def run_naive() -> tuple[str, int]:
    system = NAIVE_SYSTEM_PROMPT + f"\n\nProduct catalog for reference:\n{PRODUCT_CATALOG}"
    agent  = Agent(model=get_model(MODEL), system_prompt=system, callback_handler=None)
    history = f"Product information:\n{ANALYSIS_PRODUCT}\n\n"
    final_output = ""
    for step_name, question in ANALYSIS_STEPS:
        prompt = f"{history}Question: {question}"
        answer = str(agent(prompt))
        history += f"Step {step_name}:\n{answer}\n\n"
        final_output = answer
    return final_output, token_proxy(system + history)


def run_pipeline_notes(note_length: int) -> tuple[str, int]:
    agent = Agent(model=get_model(MODEL), system_prompt=OPTIMISED_SYSTEM_PROMPT,
                  callback_handler=None)
    notes: dict[str, str] = {}
    final_output = ""
    for step_name, question in ANALYSIS_STEPS:
        notes_text = "\n".join(f"- {k}: {v[:note_length]}" for k, v in notes.items())
        needs_catalog = any(kw in question.lower()
                            for kw in ["competitor", "price", "cost", "catalog"])
        catalog_block = f"\nCatalog:\n{PRODUCT_CATALOG}" if needs_catalog else ""
        context = (f"Product:\n{ANALYSIS_PRODUCT}\n"
                   f"Notes:\n{notes_text or '(none yet)'}"
                   f"{catalog_block}")
        answer = str(agent(f"{context}\nQuestion: {question}"))
        notes[step_name] = answer.strip()[:note_length]
        final_output = answer
    final_ctx = (OPTIMISED_SYSTEM_PROMPT
                 + f"\nProduct:\n{ANALYSIS_PRODUCT}\n"
                 + "\n".join(f"- {k}: {v}" for k, v in notes.items()))
    return final_output, token_proxy(final_ctx)


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 62)
    print("L53 H6 Closure — calibrated combined stack (gemini-flash)")
    print("=" * 62)

    judge = Agent(model=get_model(MODEL), callback_handler=None)
    task  = "Executive summary of a product analysis covering strengths, risks, and recommendation"

    print("\n  Running naive pipeline...")
    naive_out,   naive_tok   = run_naive()

    print("  Running over-compressed pipeline (120-char notes)...")
    overcomp_out, overcomp_tok = run_pipeline_notes(120)

    print("  Running calibrated pipeline (400-char notes)...")
    cal_out,     cal_tok     = run_pipeline_notes(400)

    print("\n  Judging outputs...")
    naive_score,    naive_reason    = _judge(judge, task, naive_out)
    overcomp_score, overcomp_reason = _judge(judge, task, overcomp_out)
    cal_score,      cal_reason      = _judge(judge, task, cal_out)

    oc_save  = naive_tok - overcomp_tok
    oc_pct   = round(oc_save / max(naive_tok, 1) * 100, 1)
    cal_save = naive_tok - cal_tok
    cal_pct  = round(cal_save / max(naive_tok, 1) * 100, 1)

    print(f"\n  {'Config':<22} {'Tokens':>7} {'Saving':>7} {'Pct':>6} {'Score':>6}")
    print(f"  {'─'*22} {'─'*7} {'─'*7} {'─'*6} {'─'*6}")
    print(f"  {'naive (baseline)':<22} {naive_tok:>7}       —      —  {naive_score:>5}/5")
    print(f"  {'over-compressed (120w)':<22} {overcomp_tok:>7} {oc_save:>7} {oc_pct:>5}% {overcomp_score:>5}/5")
    print(f"  {'calibrated (400w)':<22} {cal_tok:>7} {cal_save:>7} {cal_pct:>5}% {cal_score:>5}/5")

    print(f"\n  Reasons:")
    print(f"    naive      : {naive_reason}")
    print(f"    over-comp  : {overcomp_reason}")
    print(f"    calibrated : {cal_reason}")

    calibrated_ok = cal_score >= naive_score - 1
    h6_closed     = calibrated_ok and cal_tok < naive_tok

    print()
    if h6_closed:
        print(f"  ✓  H6 CLOSED: calibrated stack saves {cal_save}w ({cal_pct}%)")
        print(f"     quality {cal_score}/5 within 1 point of naive {naive_score}/5.")
        print(f"     Over-compressed: {overcomp_score}/5 — confirms 120-char truncation was the failure.")
        print(f"     Lesson: combined stack works when note length is calibrated.")
    else:
        diff = naive_score - cal_score
        print(f"  ⚠  H6 remains open: calibrated stack quality {cal_score}/5 vs naive {naive_score}/5 (Δ={diff}).")

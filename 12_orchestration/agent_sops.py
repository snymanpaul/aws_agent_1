"""
Level 43: Agent SOPs — Natural Language Workflow Specs

strands-agents-sops==1.1.1 ships five built-in SOPs:
  code_assist, pdd, codebase_summary, code_task_generator, eval

What they are:
  SOP = markdown string used as system_prompt. RFC 2119 keywords
  (MUST / SHOULD / MAY) constrain what the agent always does, prefers,
  and optionally does — without touching a line of agent code.

  _with_input(user_input) wraps the SOP in an XML envelope:
    <agent-sop name="...">
      <content>...markdown...</content>
      <user-input>...task...</user-input>
    </agent-sop>

What makes SOPs different from plain system prompts:
  Plain prompt:  "You are a code reviewer."        → free-form output, no guarantees
  SOP:           MUST produce [SECURITY] label       → enforced structure
                 MUST end with PASS/FAIL verdict     → auditable outcome
                 SHOULD note performance issues      → preferred but skippable
                 MAY comment on style               → optional

Demo structure:
  1. Inspect built-in SOPs — size, structure, _with_input() envelope
  2. Author a custom Code Review SOP with MUST/SHOULD/MAY steps
  3. Run 3 agents on the same buggy function: no SOP, plain prompt, SOP
  4. Automated compliance check: did the SOP agent follow MUST steps?
  5. Side-by-side comparison table
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import strands_agents_sops as sops
from pydantic import BaseModel
from strands import Agent
from tools import get_model

model      = get_model("claude-sonnet-4")
fast_model = get_model("haiku")


# ── 1. Built-in SOP inventory ─────────────────────────────────────────────────

def show_builtin_sops():
    print("=" * 60)
    print("BUILT-IN SOPS (strands-agents-sops 1.1.1)")
    print("=" * 60)
    names = ["code_assist", "pdd", "codebase_summary", "code_task_generator", "eval"]
    for name in names:
        content = getattr(sops, name)
        lines   = content.splitlines()
        # count MUST/SHOULD/MAY
        musts   = sum(1 for l in lines if "MUST"  in l)
        shoulds = sum(1 for l in lines if "SHOULD" in l)
        mays    = sum(1 for l in lines if " MAY "  in l)
        print(f"  {name:<22} {len(content):6} chars  {len(lines):4} lines  "
              f"MUST={musts} SHOULD={shoulds} MAY={mays}")

    print(f"\n  _with_input() envelope:")
    sample = sops.pdd_with_input("build a todo CLI")
    # Show just the wrapper structure
    lines = sample.splitlines()
    print(f"    {lines[0]}")         # <agent-sop name="pdd">
    print(f"    {lines[1]}")         # <content>
    print(f"    ...{len(lines)-6} content lines...")
    print(f"    {lines[-4]}")        # </content>
    print(f"    {lines[-3]}")        # <user-input>
    print(f"    {lines[-2]}")        # build a todo CLI
    print(f"    {lines[-1]}")        # </agent-sop>


# ── 2. Custom Code Review SOP ─────────────────────────────────────────────────

CODE_REVIEW_SOP = """# Code Review SOP

## Overview
You are a security-first code reviewer. This SOP ensures every review
covers security, correctness, and delivers an unambiguous verdict.

## Steps

### 1. Security Scan
- You MUST check for SQL injection, XSS, command injection, path traversal,
  and authentication bypass
- You MUST prefix every security finding with [SECURITY]
- You MUST NOT skip this step even if the code appears simple

### 2. Bug Detection
- You MUST identify runtime errors: IndexError, NullPointerError, type mismatches
- You MUST prefix every bug with [BUG]

### 3. Verdict
- You MUST end your review with a line starting exactly: "Verdict: "
  followed by one of: PASS | PASS_WITH_NOTES | FAIL
- You MUST provide one sentence justifying the verdict

### 4. Performance
- You SHOULD note N+1 queries, unnecessary full-table scans, or missing indices
- You SHOULD prefix performance issues with [PERF]
- You MAY skip this section if no performance issues are apparent

### 5. Style
- You MAY comment on naming conventions, PEP 8, or readability
- You MAY prefix style notes with [STYLE]
- Do NOT let style issues influence the verdict
"""


# ── 3. Sample code under review ───────────────────────────────────────────────

BUGGY_CODE = '''
def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    result = db.execute(query)
    return result[0]
'''

REVIEW_TASK = f"Review this Python function for issues:\n```python{BUGGY_CODE}```"


# ── 4. Compliance checker ─────────────────────────────────────────────────────

class ComplianceReport(BaseModel):
    security_check_done: bool    # MUST: found [SECURITY] label or explicit mention
    bug_check_done: bool         # MUST: found [BUG] label or explicit mention
    verdict_present: bool        # MUST: "Verdict: PASS/FAIL/PASS_WITH_NOTES"
    verdict: str                 # extracted verdict value
    perf_check_done: bool        # SHOULD: [PERF] label
    style_check_done: bool       # MAY: [STYLE] label

def check_compliance(review_text: str) -> ComplianceReport:
    """Pure-Python heuristic compliance check — no LLM cost."""
    text = review_text.upper()
    verdict_match = re.search(r'VERDICT:\s*(PASS_WITH_NOTES|PASS|FAIL)', review_text, re.IGNORECASE)
    return ComplianceReport(
        security_check_done = "[SECURITY]" in review_text or "sql inject" in review_text.lower(),
        bug_check_done      = "[BUG]" in review_text,
        verdict_present     = verdict_match is not None,
        verdict             = verdict_match.group(1).upper() if verdict_match else "MISSING",
        perf_check_done     = "[PERF]" in review_text,
        style_check_done    = "[STYLE]" in review_text,
    )


# ── 5. Run the comparison ─────────────────────────────────────────────────────

def run_comparison():
    print("\n" + "=" * 60)
    print("CODE REVIEW: 3 AGENTS — NO SOP | PLAIN PROMPT | SOP")
    print("=" * 60)
    print(f"\nCode under review:{BUGGY_CODE}")

    # Agent A: no system prompt
    print("─" * 60)
    print("AGENT A — No system prompt")
    print("─" * 60)
    agent_a = Agent(model=fast_model, tools=[], callback_handler=None)
    review_a = str(agent_a(REVIEW_TASK))
    print(review_a[:600])

    # Agent B: plain reviewer prompt
    print("\n" + "─" * 60)
    print("AGENT B — Plain: 'You are an expert code reviewer'")
    print("─" * 60)
    agent_b = Agent(
        model=fast_model,
        system_prompt="You are an expert code reviewer. Find all issues.",
        tools=[],
        callback_handler=None,
    )
    review_b = str(agent_b(REVIEW_TASK))
    print(review_b[:600])

    # Agent C: Code Review SOP
    print("\n" + "─" * 60)
    print("AGENT C — Code Review SOP (MUST/SHOULD/MAY)")
    print("─" * 60)
    agent_c = Agent(
        model=fast_model,
        system_prompt=CODE_REVIEW_SOP,
        tools=[],
        callback_handler=None,
    )
    review_c = str(agent_c(REVIEW_TASK))
    print(review_c[:800])

    return review_a, review_b, review_c


# ── 6. Compliance comparison table ───────────────────────────────────────────

def show_compliance_table(reviews: tuple[str, str, str]):
    review_a, review_b, review_c = reviews
    print("\n" + "=" * 60)
    print("COMPLIANCE REPORT (MUST = non-negotiable, SHOULD = preferred, MAY = optional)")
    print("=" * 60)

    agents = [
        ("A — No SOP",    review_a),
        ("B — Plain",     review_b),
        ("C — SOP",       review_c),
    ]

    header = f"  {'Agent':<18}  {'[SEC] MUST':>10}  {'[BUG] MUST':>10}  {'Verdict MUST':>12}  {'[PERF] SHOULD':>13}  {'[STYLE] MAY':>11}"
    print(header)
    print("  " + "─" * (len(header) - 2))

    for label, review in agents:
        r = check_compliance(review)
        def tick(b): return "✓" if b else "✗"
        print(
            f"  {label:<18}  {tick(r.security_check_done):>10}  "
            f"{tick(r.bug_check_done):>10}  "
            f"{r.verdict:>12}  "
            f"{tick(r.perf_check_done):>13}  "
            f"{tick(r.style_check_done):>11}"
        )

    print(f"""
  Interpretation:
    A (no SOP)    — agent DOES find SQL injection (it's obvious), but no
                    structured labels and no verdict. Output varies per run.
    B (plain)     — same as A. "Expert code reviewer" adds no guarantees.
    C (SOP)       — MUST steps enforced: [SECURITY], [BUG], Verdict always
                    present. SHOULD/MAY steps depend on content relevance.
    """)


# ── 7. Key concepts ───────────────────────────────────────────────────────────

def show_key_concepts():
    print("=" * 60)
    print("KEY CONCEPTS")
    print("=" * 60)
    print("""
  SOP = markdown string → agent system_prompt
    No SDK methods, no special runner — just structured prose.
    Works in any MCP-compatible IDE: Kiro, Cursor, Claude Code.

  RFC 2119 keywords:
    MUST        → non-negotiable; agent ALWAYS does this
    MUST NOT    → explicitly forbidden
    SHOULD      → strong preference; agent skips only if warranted
    MAY         → optional; agent uses judgment

  _with_input(user_input):
    Wraps SOP in XML envelope. Signals to the model that the
    <content> block is the authoritative workflow spec.
    Same pattern the built-in SOPs use.

  Compliance checking:
    Pure-Python regex on output. No LLM cost.
    MUST steps: check for required labels/patterns.
    If a MUST step is missing → the SOP was not followed → escalate or retry.

  vs plain system prompt:
    "You are a code reviewer"   → no guarantees, output varies
    SOP with MUST verdict       → every run includes Verdict: PASS|FAIL

  vs L42 Reflexion threshold:
    L42 numeric threshold (score >= 1.0) = MUST all tests pass
    L43 SOP constraint (MUST include verdict) = same idea, in prose
    → SOPs are human-readable Reflexion exit criteria

  Portability:
    Same .sop.md file → paste into Cursor rules, Claude Code memory,
    or MCP server tool description. No code change needed.
    """)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    show_builtin_sops()
    reviews = run_comparison()
    show_compliance_table(reviews)
    show_key_concepts()

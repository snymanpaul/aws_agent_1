"""
L43 Probe 4: does passing a SOP as system_prompt actually change agent behavior?

Task: review a buggy Python function.
Compare:
  A) no system prompt
  B) plain "you are a code reviewer" system prompt
  C) mini SOP with MUST/SHOULD/MAY constraints as system prompt
  D) code_assist_with_input() as system prompt on the same task
"""
from strands import Agent
import strands_agents_sops as sops
from tools import get_model

fast = get_model("haiku")

BUGGY_CODE = '''
def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    result = db.execute(query)
    return result[0]
'''

TASK = f"Review this Python function:\n```python{BUGGY_CODE}```"

MINI_SOP = """# Code Review SOP

## Overview
You are a code reviewer. Follow these constraints exactly.

## Steps

### 1. Security Check
- You MUST check for SQL injection, XSS, or auth bypass vulnerabilities
- You MUST call out any security issue explicitly with [SECURITY]

### 2. Correctness Check
- You MUST identify runtime errors (index errors, type errors, null dereferences)
- You MUST label each issue [BUG]

### 3. Verdict
- You MUST end your review with one of: PASS, PASS_WITH_NOTES, or FAIL
- You MUST justify the verdict in one sentence

### 4. Performance
- You SHOULD note any obvious N+1 queries or inefficient patterns
- Label these [PERF]

### 5. Style
- You MAY comment on naming, PEP8, or readability
- Label these [STYLE]
"""

# ── A: no system prompt ───────────────────────────────────────────────────────
print("=== A: no system prompt ===")
agent_a = Agent(model=fast, tools=[], callback_handler=None)
result_a = str(agent_a(TASK))
print(result_a[:500])

# ── B: plain reviewer prompt ──────────────────────────────────────────────────
print("\n=== B: plain 'you are a code reviewer' ===")
agent_b = Agent(model=fast, system_prompt="You are an expert code reviewer.", tools=[], callback_handler=None)
result_b = str(agent_b(TASK))
print(result_b[:500])

# ── C: mini SOP with MUST/SHOULD/MAY ─────────────────────────────────────────
print("\n=== C: mini SOP (MUST/SHOULD/MAY) ===")
agent_c = Agent(model=fast, system_prompt=MINI_SOP, tools=[], callback_handler=None)
result_c = str(agent_c(TASK))
print(result_c[:800])

# ── D: built-in SOP via _with_input ──────────────────────────────────────────
# codebase_summary is the most relevant for analysis
print("\n=== D: response contains verdict? ===")
for label, result in [("A (no sop)", result_a), ("B (plain)", result_b), ("C (mini SOP)", result_c)]:
    has_security = "[SECURITY]" in result or "SQL inject" in result.lower()
    has_verdict  = any(v in result for v in ["PASS", "FAIL", "PASS_WITH_NOTES"])
    has_bug      = "[BUG]" in result
    print(f"  {label:20} security={has_security} verdict={has_verdict} bug_label={has_bug}")

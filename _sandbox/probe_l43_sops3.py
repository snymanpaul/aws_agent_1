"""
L43 Probe 3: understand _with_input() and how SOP params are injected.

Questions:
1. What does _with_input() actually do — does it do templating?
2. How do curly-brace params like {task_description} get substituted?
3. What's the source of _make_wrapper?
"""
import inspect
import strands_agents_sops as sops

# ── Q1: what does _with_input() do? ───────────────────────────────────────────
print("=== Q1: pdd_with_input source ===")
fn = sops.pdd_with_input
# Get the wrapper source
try:
    src = inspect.getsource(fn)
    print(src[:800])
except Exception as e:
    print(f"  getsource error: {e}")
    # Try the underlying module
    import strands_agents_sops._loader as loader
    print(inspect.getsource(loader))

# ── Q2: _with_input with a single string ──────────────────────────────────────
print("\n=== Q2: pdd_with_input('my task') result (first 400 chars) ===")
result = sops.pdd_with_input("build a todo CLI")
print(result[:400])

# ── Q3: how many {param} placeholders in code_assist? ─────────────────────────
print("\n=== Q3: template params in code_assist ===")
import re
params = re.findall(r'\{(\w+)\}', sops.code_assist)
unique = sorted(set(params))
print(f"  {len(unique)} unique placeholders: {unique}")

# ── Q4: diff between code_assist and code_assist_with_input('') ───────────────
print("\n=== Q4: _with_input vs raw SOP (same?) ===")
raw = sops.code_assist
filled = sops.code_assist_with_input()
print(f"  raw length:    {len(raw)}")
print(f"  filled length: {len(filled)}")
if raw == filled:
    print("  identical (no substitution with empty input)")
else:
    print(f"  DIFFERENT — first diff at char {next(i for i,(a,b) in enumerate(zip(raw,filled)) if a!=b)}")

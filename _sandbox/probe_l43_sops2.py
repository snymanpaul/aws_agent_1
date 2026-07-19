"""
L43 Probe 2: figure out _with_input() API and inspect the eval SOP.

Questions:
1. What's the correct signature for code_assist_with_input()?
2. What does the eval SOP look like?
3. What's the total length of each SOP?
4. What does pdd_with_input() look like?
"""
import inspect
import strands_agents_sops as sops

# ── Q1: correct signature ──────────────────────────────────────────────────────
print("=== Q1: _with_input() signatures ===")
for name in ['code_assist_with_input', 'pdd_with_input', 'eval_with_input']:
    fn = getattr(sops, name)
    sig = inspect.signature(fn)
    print(f"  {name}{sig}")

# ── Q2: eval SOP (first 60 lines) ─────────────────────────────────────────────
print("\n=== Q2: eval SOP (first 60 lines) ===")
for i, line in enumerate(sops.eval.splitlines()[:60], 1):
    print(f"  {i:3}: {line}")

# ── Q3: SOP lengths ───────────────────────────────────────────────────────────
print("\n=== Q3: SOP lengths (chars + lines) ===")
for name in ['code_assist', 'pdd', 'eval', 'codebase_summary', 'code_task_generator']:
    content = getattr(sops, name)
    print(f"  {name}: {len(content):5} chars, {len(content.splitlines())} lines")

# ── Q4: pdd_with_input result ─────────────────────────────────────────────────
print("\n=== Q4: pdd_with_input (positional) ===")
try:
    # Try positional
    sig = inspect.signature(sops.pdd_with_input)
    params = list(sig.parameters.keys())
    print(f"  params: {params}")
    result = sops.pdd_with_input("build a CLI todo app", "todo-cli", "/tmp/todo")
    print(f"  Result (first 300 chars):\n{result[:300]}")
except Exception as e:
    print(f"  error: {e}")

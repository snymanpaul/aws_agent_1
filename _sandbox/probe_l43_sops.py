"""
L43 Probe: strands-agents-sops package — what does it expose?

Questions:
1. What names does the package export?
2. What does a built-in SOP look like (first 100 lines of code_assist)?
3. What does get_sop_format() return?
4. Are there wrapped _with_input() helpers and what do they do?
5. Can we load a custom .sop.md file?
"""
import strands_agents_sops as sops

# ── Q1: exported names ─────────────────────────────────────────────────────────
print("=== Q1: exported names ===")
names = [n for n in dir(sops) if not n.startswith("_")]
print(names)

# ── Q2: what does a built-in SOP look like? ────────────────────────────────────
print("\n=== Q2: code_assist SOP (first 80 lines) ===")
lines = sops.code_assist.splitlines()
for i, line in enumerate(lines[:80], 1):
    print(f"  {i:3}: {line}")

# ── Q3: get_sop_format ─────────────────────────────────────────────────────────
print("\n=== Q3: get_sop_format() ===")
try:
    fmt = sops.get_sop_format()
    print(fmt[:500])
except Exception as e:
    print(f"  error: {e}")

# ── Q4: _with_input helpers ────────────────────────────────────────────────────
print("\n=== Q4: code_assist_with_input() ===")
try:
    result = sops.code_assist_with_input(
        task_description="add a greet() function",
        project_name="myapp",
    )
    print(result[:600])
except Exception as e:
    print(f"  error: {e}")

# ── Q5: how does the package find its .sop.md files? ──────────────────────────
print("\n=== Q5: package structure ===")
import importlib.resources as ir
import pathlib
pkg_path = pathlib.Path(sops.__file__).parent
print(f"Package dir: {pkg_path}")
sop_files = list(pkg_path.rglob("*.sop.md"))
print(f"SOP files found: {[f.name for f in sop_files]}")

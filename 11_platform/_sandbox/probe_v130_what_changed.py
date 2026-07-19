"""
Probe: What changed from 1.19 → 1.30?
  1. Is LLMSteeringHandler anywhere in v1.30?
  2. Is concurrent_invocation_mode for parallel TOOLS or parallel AGENT calls?
  3. Does HookProvider still work?
  4. New Agent params summary

Run: uv run python 11_platform/_sandbox/probe_v130_what_changed.py
"""

import sys
import os
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import strands
pkg = os.path.dirname(strands.__file__)

# 1. Search for LLMSteeringHandler anywhere
print("=== Searching for LLMSteeringHandler in site-packages ===")
import subprocess
result = subprocess.run(
    ["grep", "-r", "LLMSteeringHandler", pkg, "--include=*.py", "-l"],
    capture_output=True, text=True
)
print(result.stdout or "NOT FOUND anywhere in strands package")

# 2. ConcurrentInvocationMode — what does it actually do?
print("\n=== ConcurrentInvocationMode usage in Agent ===")
agent_src = inspect.getsourcefile(strands.Agent)
with open(agent_src) as f:
    lines = f.readlines()
concurrent_lines = [(i+1, l.rstrip()) for i, l in enumerate(lines)
                    if "concurrent_invocation" in l.lower()]
for lineno, line in concurrent_lines[:20]:
    print(f"  {lineno:4d}: {line}")

# 3. HookProvider still importable?
print("\n=== HookProvider in v1.30 ===")
try:
    from strands.hooks import HookProvider
    print(f"  HookProvider: {HookProvider} — still works")
except ImportError as e:
    print(f"  HookProvider: GONE — {e}")

# 4. New Agent params vs 1.19
print("\n=== All Agent.__init__ params (v1.30) ===")
sig = inspect.signature(strands.Agent.__init__)
for name, p in sig.parameters.items():
    if name == "self":
        continue
    print(f"  {name}: default={p.default!r}")

# 5. Plugin — can it replace HookProvider?
print("\n=== Plugin vs HookProvider ===")
from strands.plugins import Plugin, hook
from strands.hooks import HookProvider, BeforeToolCallEvent

print(f"  Plugin MRO: {[c.__name__ for c in Plugin.__mro__]}")
print(f"  HookProvider is Protocol: {'Protocol' in str(HookProvider.__bases__)}")
print(f"  Plugin is ABC: {'ABC' in str(Plugin.__bases__)}")

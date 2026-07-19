"""
Probe: Find steering + plugins API in strands 1.30.0

Run: uv run python 11_platform/_sandbox/probe_v130_steering.py
"""

import sys
import os
import importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def try_import(name):
    try:
        mod = importlib.import_module(name)
        members = [n for n in dir(mod) if not n.startswith("_")]
        print(f"\n{name}  ({len(members)}):")
        for m in members:
            print(f"  {m}")
        return mod
    except ImportError as e:
        print(f"\n{name}: {e}")
        return None


# Find steering
import strands
import strands.plugins
pkg_dir = os.path.dirname(strands.__file__)
print(f"strands location: {pkg_dir}\n")

for root, dirs, files in os.walk(pkg_dir):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for f in files:
        if f.endswith(".py") and "steer" in f.lower():
            rel = os.path.relpath(os.path.join(root, f), pkg_dir)
            print(f"Found: strands/{rel}")

# Check plugins module
try_import("strands.plugins")

# Try direct steering imports
for path in [
    "strands.plugins.steering",
    "strands.steering",
    "strands.plugins.builtin",
]:
    try_import(path)

# Check concurrent_invocation_mode on Agent
from strands import Agent
import inspect
sig = inspect.signature(Agent.__init__)
params = sig.parameters
for name, p in params.items():
    if name in ("plugins", "concurrent_invocation_mode", "retry_strategy"):
        print(f"\nAgent.{name}: default={p.default!r}")

"""
Probe: Exact exports from strands.vended_plugins.steering in v1.30

Run: uv run python 11_platform/_sandbox/probe_steering_exports.py
"""

import sys, os, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

for mod_name in [
    "strands.vended_plugins.steering",
    "strands.vended_plugins.steering.core",
    "strands.vended_plugins.steering.handlers",
    "strands.vended_plugins.steering.handlers.llm",
]:
    try:
        mod = importlib.import_module(mod_name)
        exports = [n for n in dir(mod) if not n.startswith("_")]
        print(f"\n{mod_name}:")
        for e in exports:
            print(f"  {e}")
    except ImportError as e:
        print(f"\n{mod_name}: {e}")

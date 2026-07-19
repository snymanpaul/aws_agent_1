"""
Probe: Find Skills plugin exports in v1.30.

Run: uv run python 11_platform/_sandbox/probe_skills_exports.py
"""

import sys, os, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

for mod_name in [
    "strands.vended_plugins",
    "strands.vended_plugins.skills",
    "strands.experimental.skills",
    "strands.plugins.skills",
]:
    try:
        mod = importlib.import_module(mod_name)
        exports = [n for n in dir(mod) if not n.startswith("_")]
        print(f"\n{mod_name}:")
        for e in exports:
            print(f"  {e}")
    except ImportError as e:
        print(f"\n{mod_name}: ImportError — {e}")
    except Exception as e:
        print(f"\n{mod_name}: {type(e).__name__} — {e}")

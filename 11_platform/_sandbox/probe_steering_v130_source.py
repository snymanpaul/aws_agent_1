"""
Probe: Read SteeringHandler source in v1.30 — understand how Guide cancels tools.

Run: uv run python 11_platform/_sandbox/probe_steering_v130_source.py
"""

import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands.vended_plugins.steering import SteeringHandler
from strands.vended_plugins.steering.core import handler as handler_mod

print("=== SteeringHandler source ===")
print(inspect.getsource(SteeringHandler))

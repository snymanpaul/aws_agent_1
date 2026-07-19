"""
Probe: Inspect strands.plugins API in v1.30.0 — Plugin base, decorator, registry

Run: uv run python 11_platform/_sandbox/probe_v130_plugin_api.py
"""

import sys
import os
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands.plugins import Plugin, plugin, hook
from strands import Agent

print("=== Plugin (base class) ===")
print(inspect.getsource(Plugin))

print("\n=== @plugin decorator ===")
print(inspect.getsource(plugin))

print("\n=== @hook decorator ===")
print(inspect.getsource(hook))

# Check ConcurrentInvocationMode
print("\n=== ConcurrentInvocationMode ===")
from strands.agent.agent import ConcurrentInvocationMode
print(inspect.getsource(ConcurrentInvocationMode))

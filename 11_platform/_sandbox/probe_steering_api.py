"""
Probe: What steering/plugin API exists in strands 1.19.x?

Checks:
  1. strands.experimental.steering
  2. Any 'plugin' parameter on Agent
  3. LLMSteeringHandler, LedgerProvider existence
  4. Interrupt mechanism for hooks

Run: uv run python 11_platform/_sandbox/probe_steering_api.py
"""

import sys
import os
import importlib
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def dump(name):
    try:
        mod = importlib.import_module(name)
        members = [n for n in dir(mod) if not n.startswith("_")]
        print(f"\n{name}  ({len(members)} exports):")
        for m in members:
            print(f"  {m}")
        return mod
    except ImportError as e:
        print(f"\n{name}: NOT AVAILABLE — {e}")
        return None


# 1. Steering module
dump("strands.experimental.steering")

# 2. Agent — any 'plugin' param?
from strands import Agent
sig = inspect.signature(Agent.__init__)
print(f"\nAgent.__init__ params: {list(sig.parameters.keys())}")
plugin_params = [p for p in sig.parameters if "plugin" in p.lower()]
print(f"Plugin-related params: {plugin_params or 'NONE'}")

# 3. Interrupt mechanism
try:
    from strands.interrupt import Interrupt, InterruptException
    print(f"\nInterrupt: {Interrupt}")
    print(f"InterruptException: {InterruptException}")
    src = inspect.getsource(Interrupt)
    print(src[:800])
except ImportError as e:
    print(f"\nstrands.interrupt: {e}")

# 4. Hooks — can we interrupt from a hook callback?
try:
    from strands.hooks.registry import HookCallback
    print(f"\nHookCallback: {HookCallback}")
except ImportError as e:
    print(f"\nHookCallback: {e}")

# 5. BeforeToolCallEvent — is it Interruptible?
try:
    from strands.hooks.events import BeforeToolCallEvent
    mro = [c.__name__ for c in BeforeToolCallEvent.__mro__]
    print(f"\nBeforeToolCallEvent MRO: {mro}")
    interruptible = "Interruptible" in " ".join(mro) or "_Interruptible" in " ".join(mro)
    print(f"Is Interruptible: {interruptible}")
except Exception as e:
    print(f"\nBeforeToolCallEvent check: {e}")

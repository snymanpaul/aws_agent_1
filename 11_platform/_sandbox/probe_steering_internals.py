"""
Probe: Inspect LLMSteeringHandler, SteeringHandler, LedgerProvider internals.
Determines how to wire steering into an agent in SDK 1.19.x (no plugins= param).

Run: uv run python 11_platform/_sandbox/probe_steering_internals.py
"""

import sys
import os
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands.experimental.steering import (
    LLMSteeringHandler,
    SteeringHandler,
    LedgerProvider,
    Guide,
    Proceed,
    Interrupt,
)

# --- SteeringHandler base ---
print("=== SteeringHandler ===")
print(inspect.getsource(SteeringHandler))

# --- LedgerProvider ---
print("\n=== LedgerProvider (first 60 lines) ===")
src = inspect.getsource(LedgerProvider)
print("\n".join(src.splitlines()[:60]))

# --- LLMSteeringHandler (first 80 lines) ===
print("\n=== LLMSteeringHandler (first 80 lines) ===")
src = inspect.getsource(LLMSteeringHandler)
print("\n".join(src.splitlines()[:80]))

# --- Guide / Proceed / Interrupt ---
print("\n=== SteeringAction types ===")
for cls in [Guide, Proceed, Interrupt]:
    print(f"\n{cls.__name__}:")
    try:
        print(inspect.getsource(cls))
    except Exception:
        print(f"  (built-in or not sourceable)")

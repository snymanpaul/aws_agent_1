"""
Probe: Does mcp.server.experimental expose any server-side task support?
Also checks mcp.server.lowlevel.Server for request handler registration.

Run: uv run python 11_platform/_sandbox/probe_mcp_experimental.py
"""

import sys
import os
import importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def dump_module(name: str) -> None:
    try:
        mod = importlib.import_module(name)
        members = [n for n in dir(mod) if not n.startswith("_")]
        print(f"\n{name} ({len(members)} exports):")
        for m in members:
            print(f"  {m}")
    except ImportError as e:
        print(f"\n{name}: NOT AVAILABLE — {e}")


dump_module("mcp.server.experimental")
dump_module("mcp.server.lowlevel")

# Specifically check Server request handler API
try:
    from mcp.server.lowlevel import Server
    import inspect
    methods = [(n, m) for n, m in inspect.getmembers(Server, predicate=inspect.isfunction)]
    print(f"\nServer methods ({len(methods)}):")
    for name, _ in methods:
        print(f"  {name}")
except ImportError as e:
    print(f"\nServer import failed: {e}")

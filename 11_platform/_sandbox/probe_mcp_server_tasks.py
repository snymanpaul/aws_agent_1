"""
Probe: What server-side task APIs does the installed mcp library expose?

Checks:
  1. Can we import mcp.server and mcp.server.fastmcp?
  2. Does FastMCP (or Server) have a task registration API?
  3. What's the mcp library version?
  4. List all task-related names in mcp.types and mcp.server

Run: uv run python 11_platform/_sandbox/probe_mcp_server_tasks.py
"""

import sys
import os
import importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def check_module(name: str) -> tuple[bool, object | None]:
    try:
        mod = importlib.import_module(name)
        return True, mod
    except ImportError as e:
        return False, str(e)


# --- Version ---
ok, mcp = check_module("mcp")
if ok:
    ver = getattr(mcp, "__version__", "unknown")
    print(f"mcp version: {ver}")
else:
    print(f"mcp not importable: {mcp}")
    sys.exit(1)

# --- mcp.types task names ---
ok, types_mod = check_module("mcp.types")
if ok:
    task_names = sorted(n for n in dir(types_mod) if "task" in n.lower() or "Task" in n)
    print(f"\nmcp.types task-related names ({len(task_names)}):")
    for n in task_names:
        print(f"  {n}")

# --- mcp.server ---
ok, server_mod = check_module("mcp.server")
if ok:
    print(f"\nmcp.server exports: {[n for n in dir(server_mod) if not n.startswith('_')]}")
else:
    print(f"\nmcp.server: {server_mod}")

# --- FastMCP ---
ok, fastmcp_mod = check_module("mcp.server.fastmcp")
if ok:
    print(f"\nmcp.server.fastmcp exports: {[n for n in dir(fastmcp_mod) if not n.startswith('_')]}")
    FastMCP = getattr(fastmcp_mod, "FastMCP", None)
    if FastMCP:
        task_methods = [m for m in dir(FastMCP) if "task" in m.lower()]
        print(f"FastMCP task-related methods: {task_methods}")
else:
    print(f"\nmcp.server.fastmcp: {fastmcp_mod}")

# --- Low-level Server ---
ok, srv = check_module("mcp.server.lowlevel")
if ok:
    print(f"\nmcp.server.lowlevel exports: {[n for n in dir(srv) if not n.startswith('_')]}")
else:
    print(f"\nmcp.server.lowlevel: {srv}")

# --- stdio_server ---
ok, stdio_srv = check_module("mcp.server.stdio")
if ok:
    print(f"\nmcp.server.stdio exports: {[n for n in dir(stdio_srv) if not n.startswith('_')]}")
else:
    print(f"\nmcp.server.stdio: {stdio_srv}")

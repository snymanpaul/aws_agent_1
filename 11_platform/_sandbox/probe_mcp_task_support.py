"""
Probe: Inspect mcp.server.experimental task APIs in detail.
Determines if we can build a real MCP server with tasks capability.

Run: uv run python 11_platform/_sandbox/probe_mcp_task_support.py
"""

import sys
import os
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mcp.server import experimental

print("=== mcp.server.experimental ===")
for name in ["task_support", "task_context", "task_result_handler", "session_features", "request_context"]:
    obj = getattr(experimental, name, None)
    if obj is None:
        print(f"\n{name}: NOT FOUND")
        continue
    print(f"\n--- {name} ---")
    print(f"  type: {type(obj)}")
    try:
        print(inspect.getsource(obj))
    except (TypeError, OSError) as e:
        # Not sourceable — inspect members instead
        members = [(n, type(getattr(obj, n)).__name__) for n in dir(obj) if not n.startswith("_")]
        for n, t in members:
            print(f"  {n}: {t}")

# Also check FastMCP's task-adjacent internal modules
print("\n=== mcp.server.fastmcp internals ===")
try:
    from mcp.server.fastmcp import FastMCP
    src_file = inspect.getfile(FastMCP)
    print(f"FastMCP source: {src_file}")
    # Look for any task-related code in FastMCP
    with open(src_file) as f:
        lines = f.readlines()
    task_lines = [(i+1, l.rstrip()) for i, l in enumerate(lines) if "task" in l.lower()]
    if task_lines:
        print(f"\nTask-related lines in FastMCP ({len(task_lines)}):")
        for lineno, line in task_lines[:20]:
            print(f"  {lineno:4d}: {line}")
    else:
        print("  No task-related code found in FastMCP")
except Exception as e:
    print(f"  Error: {e}")

"""
Probe L56: Inspect MCPAgentTool object attributes from list_tools_sync().
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent.parent / "13_quality"
sys.path.insert(0, str(Path(__file__).parent.parent))

from strands.tools.mcp import MCPClient
from mcp import StdioServerParameters, stdio_client

NAIVE_SERVER = str(HERE / "_mcp_naive_server.py")

with MCPClient(lambda: stdio_client(
    StdioServerParameters(command="uv", args=["run", "python", NAIVE_SERVER])
)) as mcp:
    tools = mcp.list_tools_sync()
    print(f"list_tools_sync() returned {len(tools)} items")
    print(f"Item type: {type(tools[0])}")
    print()

    t = tools[0]
    print("dir() of first tool:")
    for attr in sorted(dir(t)):
        if not attr.startswith("__"):
            try:
                val = getattr(t, attr)
                if not callable(val):
                    print(f"  {attr:30s} = {repr(val)[:80]}")
            except Exception as e:
                print(f"  {attr:30s} ERROR: {e}")
    print()
    print("All tool names (via correct attribute):")
    for tool in tools:
        # Try common name attributes
        for attr in ("name", "tool_name", "_name", "tool"):
            if hasattr(tool, attr):
                val = getattr(tool, attr)
                if isinstance(val, str):
                    print(f"  .{attr} = {val}")
                    break

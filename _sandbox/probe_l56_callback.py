"""
Probe L56: Inspect callback_handler events during a real MCP tool call.
Also probe full tool_spec and mcp_tool attributes.
"""
import sys
import json
from pathlib import Path

HERE = Path(__file__).parent.parent / "13_quality"
sys.path.insert(0, str(Path(__file__).parent.parent))

from strands import Agent
from strands.tools.mcp import MCPClient
from mcp import StdioServerParameters, stdio_client
from tools import get_model

NAIVE_SERVER = str(HERE / "_mcp_naive_server.py")

events_seen = []

def capture_callback(**kwargs):
    keys = list(kwargs.keys())
    if keys not in [e["keys"] for e in events_seen if "keys" in e]:
        summary = {
            "keys": keys,
        }
        for k, v in kwargs.items():
            summary[f"{k}_type"] = type(v).__name__
            summary[f"{k}_repr"] = repr(v)[:120]
        events_seen.append(summary)

with MCPClient(lambda: stdio_client(
    StdioServerParameters(command="uv", args=["run", "python", NAIVE_SERVER])
)) as mcp:
    tools = mcp.list_tools_sync()

    # Print full tool_spec for first tool
    t = tools[0]
    print(f"tool_name: {t.tool_name}")
    print(f"mcp_tool type: {type(t.mcp_tool)}")
    print(f"mcp_tool.description: {t.mcp_tool.description[:100] if t.mcp_tool.description else 'None'}")
    print(f"mcp_tool.inputSchema: {t.mcp_tool.inputSchema}")
    print(f"tool_spec keys: {list(t.tool_spec.keys())}")
    print(f"tool_spec: {json.dumps(t.tool_spec, default=str)[:200]}")
    print()

    # Run a quick single-tool task and capture all callback events
    agent = Agent(
        model=get_model("gemini-flash"),
        tools=tools,
        callback_handler=capture_callback,
    )
    agent("What orders exist? Just call list_all_orders and tell me how many orders there are.")

print("\nCallback events seen:")
for i, e in enumerate(events_seen):
    print(f"\n  Event {i+1}: keys={e['keys']}")
    for k, v in e.items():
        if k != "keys":
            print(f"    {k}: {str(v)[:100]}")

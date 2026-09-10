"""Check that every mcp import the lessons use still resolves on the upgraded mcp.

Run: uv run python _sandbox/probe_upgrade_2026-09-10_mcp_symbols.py
"""
import importlib
from importlib.metadata import version

CHECKS = [
    ("mcp", ["StdioServerParameters", "stdio_client", "ClientSession"]),
    ("mcp.client.streamable_http", ["streamablehttp_client"]),
    ("mcp.server.fastmcp", ["FastMCP"]),
    ("mcp.server.lowlevel", ["Server"]),
    ("mcp.server", ["experimental"]),
    ("strands.tools.mcp", ["MCPClient"]),
    ("strands.multiagent.a2a", ["A2AServer"]),
]
print("mcp", version("mcp"), "| a2a-sdk", version("a2a-sdk"))
for mod, names in CHECKS:
    try:
        m = importlib.import_module(mod)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL import {mod}: {exc!r}")
        continue
    for n in names:
        print(f"{'ok  ' if hasattr(m, n) else 'MISS'} {mod}.{n}")

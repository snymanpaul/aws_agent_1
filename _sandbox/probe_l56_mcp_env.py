"""
Probe L56: Check MCP environment — FastMCP, MCPClient, stdio_client availability.
"""
import sys

checks = []

try:
    from mcp.server.fastmcp import FastMCP
    checks.append(("FastMCP (mcp.server.fastmcp)", "OK"))
except ImportError as e:
    checks.append(("FastMCP (mcp.server.fastmcp)", f"MISSING: {e}"))

try:
    from mcp import StdioServerParameters
    checks.append(("StdioServerParameters (mcp)", "OK"))
except ImportError as e:
    checks.append(("StdioServerParameters (mcp)", f"MISSING: {e}"))

try:
    from strands.tools.mcp import MCPClient
    checks.append(("MCPClient (strands.tools.mcp)", "OK"))
except ImportError as e:
    checks.append(("MCPClient (strands.tools.mcp)", f"MISSING: {e}"))

try:
    from importlib.metadata import version
    v = version("mcp")
    checks.append(("mcp version", v))
except Exception as e:
    checks.append(("mcp version", f"ERROR: {e}"))

# Check if stdio_client is importable
try:
    from mcp import stdio_client
    checks.append(("stdio_client (mcp)", "OK"))
except ImportError as e:
    checks.append(("stdio_client (mcp)", f"MISSING: {e}"))

# Can we instantiate a minimal FastMCP server?
try:
    s = FastMCP("probe-test")

    @s.tool()
    def probe_tool(x: str) -> str:
        """A test tool."""
        return f"ok:{x}"

    checks.append(("FastMCP server instantiation", "OK — tool registered"))
except Exception as e:
    checks.append(("FastMCP server instantiation", f"ERROR: {e}"))

print("L56 MCP environment probe")
print("=" * 50)
for label, result in checks:
    status = "✓" if not result.startswith(("MISSING", "ERROR")) else "✗"
    print(f"  {status}  {label:<40} {result}")
print()

all_ok = all(
    not r.startswith(("MISSING", "ERROR"))
    for _, r in checks
)
print(f"  Ready for L56: {'YES' if all_ok else 'NO — see failures above'}")

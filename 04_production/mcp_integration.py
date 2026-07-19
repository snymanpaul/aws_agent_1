"""
Level 9: MCP (Model Context Protocol) Integration
=================================================
Connect agents to external tools via MCP servers.

Key Concepts:
- MCP: Open protocol for LLM-tool communication
- MCPClient: Strands wrapper for MCP connections
- Transport: stdio (local), HTTP, SSE
- Tool discovery: Automatic from MCP servers

Benefits:
- Access 1000s of pre-built MCP servers
- Standardized tool interface
- No custom tool code needed

Run: uv run python 04_production/mcp_integration.py

Prerequisites (for live examples):
- Node.js installed (for npx MCP servers)
- MCP server packages vary - check https://github.com/modelcontextprotocol/servers

Note: This file demonstrates the MCP integration PATTERN.
Actual server packages may need adjustment based on availability.
"""

import asyncio
from strands import Agent
from strands.tools.mcp import MCPClient
from strands.models.openai import OpenAIModel

# Configure model
model = OpenAIModel(
    model_id="claude-sonnet-4",
    client_args={
        "base_url": "http://localhost:4000",
        "api_key": "sk-local"
    }
)


# =============================================================================
# Example 1: Filesystem MCP Server (via npx)
# =============================================================================
# This connects to a local filesystem MCP server that provides file operations

def example_filesystem_mcp():
    """
    Connect to filesystem MCP server for file operations.

    Server provides tools like:
    - read_file: Read file contents
    - write_file: Write to files
    - list_directory: List directory contents
    """
    from mcp import stdio_client, StdioServerParameters

    # Create MCP client with stdio transport
    # The server runs as a subprocess
    mcp_client = MCPClient(lambda: stdio_client(
        StdioServerParameters(
            command="npx",
            args=[
                "-y",  # Auto-confirm install
                "@modelcontextprotocol/server-filesystem",
                "/tmp"  # Root directory for file operations
            ]
        )
    ))

    # Use context manager for proper cleanup
    with mcp_client:
        # List available tools from the MCP server
        tools = mcp_client.list_tools_sync()
        print(f"Available MCP tools: {[t.name for t in tools]}")

        # Create agent with MCP tools
        agent = Agent(model=model, tools=tools)

        # Use the agent with MCP tools
        response = agent("List the contents of the /tmp directory")
        print(response)


# =============================================================================
# Example 2: Fetch MCP Server (web requests)
# =============================================================================
# This connects to a fetch MCP server for making HTTP requests

def example_fetch_mcp():
    """
    Connect to fetch MCP server for web requests.

    Server provides tools like:
    - fetch: Make HTTP requests to URLs
    """
    from mcp import stdio_client, StdioServerParameters

    mcp_client = MCPClient(lambda: stdio_client(
        StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-fetch"]
        )
    ))

    with mcp_client:
        tools = mcp_client.list_tools_sync()
        print(f"Available MCP tools: {[t.name for t in tools]}")

        agent = Agent(model=model, tools=tools)
        response = agent("Fetch the content from https://httpbin.org/json and summarize it")
        print(response)


# =============================================================================
# Example 3: Multiple MCP Servers
# =============================================================================
# Combine tools from multiple MCP servers in one agent

def example_multiple_mcp_servers():
    """
    Combine multiple MCP servers for richer capabilities.

    Uses tool prefixing to avoid name conflicts.
    """
    from mcp import stdio_client, StdioServerParameters

    # Filesystem server with prefix
    fs_client = MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
            )
        ),
        prefix="fs"  # Tools become: fs_read_file, fs_write_file, etc.
    )

    # Fetch server with prefix
    fetch_client = MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-fetch"]
            )
        ),
        prefix="web"  # Tools become: web_fetch, etc.
    )

    with fs_client, fetch_client:
        # Combine tools from both servers
        fs_tools = fs_client.list_tools_sync()
        fetch_tools = fetch_client.list_tools_sync()
        all_tools = fs_tools + fetch_tools

        print(f"Combined MCP tools: {[t.name for t in all_tools]}")

        agent = Agent(model=model, tools=all_tools)

        # Agent can now use both filesystem and web tools
        response = agent("""
        1. Fetch the JSON from https://httpbin.org/json
        2. Save the response to /tmp/httpbin_response.json
        3. Read the file back and confirm the contents
        """)
        print(response)


# =============================================================================
# Example 4: Simple Demo (no external dependencies)
# =============================================================================
# For testing without MCP servers installed

def example_simple_demo():
    """
    Simple demonstration of MCP concepts without external servers.

    This shows the pattern even if MCP servers aren't installed.
    """
    print("MCP Integration Pattern:")
    print()
    print("1. Create MCPClient with transport:")
    print("   mcp_client = MCPClient(lambda: stdio_client(params))")
    print()
    print("2. Use context manager:")
    print("   with mcp_client:")
    print()
    print("3. Get tools from server:")
    print("   tools = mcp_client.list_tools_sync()")
    print()
    print("4. Create agent with tools:")
    print("   agent = Agent(model=model, tools=tools)")
    print()
    print("5. Use agent normally:")
    print("   response = agent('Your query')")
    print()
    print("-" * 60)
    print()
    print("Common MCP Servers (via npx):")
    print("  @modelcontextprotocol/server-filesystem - File operations")
    print("  @modelcontextprotocol/server-fetch      - HTTP requests")
    print("  @modelcontextprotocol/server-github     - GitHub API")
    print("  @modelcontextprotocol/server-postgres   - PostgreSQL")
    print("  @modelcontextprotocol/server-sqlite     - SQLite")
    print()
    print("AWS MCP Servers (via uvx):")
    print("  awslabs.aws-documentation-mcp-server    - AWS docs search")
    print("  awslabs.bedrock-mcp-server              - Bedrock models")
    print()


# =============================================================================
# Demo
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Level 9: MCP (Model Context Protocol) Integration")
    print("=" * 60)
    print()

    # Run the simple demo (always works)
    example_simple_demo()

    # Note: Actual MCP examples require specific MCP servers installed
    # The pattern above shows how to integrate once servers are available
    print("\n" + "-" * 60)
    print("To run actual MCP examples:")
    print("1. Install an MCP server (e.g., via npm or uvx)")
    print("2. Uncomment the example function calls in this file")
    print("3. Update package names to match installed servers")
    print("-" * 60)

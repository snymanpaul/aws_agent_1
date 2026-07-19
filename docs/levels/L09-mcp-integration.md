# L09: MCP Integration

**Code:** `04_production/mcp_integration.py`

### Level 9: MCP Integration
**Goal:** Leverage Model Context Protocol ecosystem

```python
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters

params = StdioServerParameters(command="uvx", args=["mcp-server-fetch"])
mcp_client = MCPClient(lambda: stdio_client(params))
with mcp_client:
    agent = Agent(model=model, tools=mcp_client.list_tools_sync())
```

**Key Concepts:**
- 1000s of pre-built MCP servers available
- Standardized tool protocol
- External service integration

---

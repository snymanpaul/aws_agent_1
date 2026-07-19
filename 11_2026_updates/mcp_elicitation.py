"""
Level 60: MCP Elicitation — Server-Requested User Input
=========================================================
Strands SDK v1.35 — handling MCP server elicitation requests (-32042).

Goal: Understand MCP elicitation protocol flow and how Strands handles
      server-initiated requests for additional user input.

Depends on: L9 (MCP Integration)
Unlocks:    L47 (Human-on-the-Loop)

Iterations:
  1. Protocol Flow           — what -32042 means and when servers use it
  2. Elicitation Callback    — MCPClient's elicitation_callback parameter
  3. Agent-Side Handling     — how the agent sees elicitation in tool results
  4. Elicitation vs Handoff  — server-initiated vs agent-initiated patterns

Key insight:
    MCP elicitation is SERVER-initiated: the tool server needs information
    from the user during execution. This is different from agent handoff
    (L47) where the AGENT decides it needs human input. The -32042 error
    code triggers a structured data exchange, not a simple error message.

NOTE: This lesson demonstrates the protocol and SDK handling mechanism.
      A full end-to-end demo requires a real MCP server that returns -32042.

Usage:
    uv run python 11_2026_updates/mcp_elicitation.py
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Iteration 1: Protocol Flow — What -32042 Means
# =============================================================================
# MCP spec defines error code -32042 as "ElicitationRequired".
# Flow:
#   1. Agent calls MCP tool (e.g., "delete_file")
#   2. Server decides it needs user confirmation
#   3. Server returns error -32042 with ElicitationRequiredErrorData
#   4. Client handles the elicitation (prompt user, provide callback, etc.)
#   5. Response is relayed back to the agent as tool result

def demo_protocol_flow():
    """Explain the MCP elicitation protocol flow."""
    print("\n" + "=" * 60)
    print("Iteration 1: MCP Elicitation Protocol Flow")
    print("=" * 60)

    print("""
    MCP Elicitation Sequence:

    Agent           MCPClient           MCP Server
      │                │                    │
      │ call_tool()    │                    │
      │───────────────>│  tools/call        │
      │                │───────────────────>│
      │                │                    │ Needs user input!
      │                │  error: -32042     │
      │                │<───────────────────│
      │                │                    │
      │                │ Parse elicitation  │
      │                │ data from error    │
      │                │                    │
      │  tool_result   │                    │
      │<───────────────│                    │
      │  (contains     │                    │
      │   elicitation  │                    │
      │   prompt)      │                    │
      │                │                    │
      │ Agent decides  │                    │
      │ next action    │                    │
      └────────────────┘                    │

    The -32042 error contains structured data:
    {
        "elicitations": [
            {
                "message": "Are you sure you want to delete file.txt?",
                "requestedSchema": {
                    "type": "object",
                    "properties": {
                        "confirmed": {"type": "boolean"}
                    }
                }
            }
        ]
    }
    """)


# =============================================================================
# Iteration 2: Elicitation Callback — MCPClient Configuration
# =============================================================================
# MCPClient accepts an elicitation_callback parameter. When provided,
# MCP session uses it to handle elicitation requests from the server.

def demo_elicitation_callback():
    """Show how to configure elicitation_callback on MCPClient."""
    print("\n" + "=" * 60)
    print("Iteration 2: Elicitation Callback Configuration")
    print("=" * 60)

    # The elicitation_callback is passed to MCPClient at construction time.
    # It follows the mcp library's ElicitationFnT type signature.
    print("""
    MCPClient Configuration:

    ```python
    from strands.tools.mcp import MCPClient
    from mcp import StdioServerParameters, stdio_client

    # Define an elicitation callback
    async def handle_elicitation(context, params):
        \"\"\"Handle server-requested user input.\"\"\"
        # context: ElicitationContext with session info
        # params: ElicitationRequestParams with message + schema
        print(f"Server asks: {params.message}")

        # In a real app: prompt user, collect response
        # Return the response matching requestedSchema
        return {"confirmed": True}

    # Pass callback to MCPClient
    mcp_client = MCPClient(
        lambda: stdio_client(StdioServerParameters(
            command="python",
            args=["my_mcp_server.py"],
        )),
        elicitation_callback=handle_elicitation,
    )

    # Use with agent — elicitation is handled automatically
    agent = Agent(
        model=model,
        tools=[mcp_client],
    )
    ```

    The callback receives:
    - context: session-level metadata
    - params: the elicitation request (message + requestedSchema)

    Returns: a dict matching the requestedSchema, or None to cancel.
    """)

    print("✓ elicitation_callback wires user input into MCP tool execution")


# =============================================================================
# Iteration 3: Agent-Side Handling — Tool Result Processing
# =============================================================================
# When no elicitation_callback is provided, Strands SDK converts the -32042
# error into a tool result with the elicitation data. The agent sees it as
# a tool error containing the prompt and schema.

def demo_agent_handling():
    """Show how the agent processes elicitation as a tool result."""
    print("\n" + "=" * 60)
    print("Iteration 3: Agent-Side Handling")
    print("=" * 60)

    # Simulate what the agent sees when -32042 is returned
    # (without elicitation_callback configured)

    simulated_tool_result = {
        "toolUseId": "tool-use-123",
        "status": "error",
        "content": [{
            "text": 'MCP Elicitation required: [McpError: -32042] with data '
                    + json.dumps([{
                        "message": "This will permanently delete 'important_data.csv'. Are you sure?",
                        "requestedSchema": {
                            "type": "object",
                            "properties": {
                                "confirmed": {"type": "boolean"},
                                "reason": {"type": "string"}
                            },
                            "required": ["confirmed"]
                        }
                    }])
        }]
    }

    print("When no elicitation_callback is set, the agent sees this tool result:\n")
    print(json.dumps(simulated_tool_result, indent=2))

    print("""
    The agent can then:
    1. Parse the elicitation data from the error message
    2. Decide whether to ask the user or auto-respond
    3. Retry the tool call with the user's response

    This is the "agent-mediated" pattern — the LLM decides how to handle
    the server's request for input, rather than a callback handling it
    programmatically.
    """)

    # Parse and display the elicitation request
    text = simulated_tool_result["content"][0]["text"]
    if "MCP Elicitation required:" in text:
        data_start = text.index("with data ") + len("with data ")
        elicitations = json.loads(text[data_start:])
        for e in elicitations:
            print(f"  Server asks: {e['message']}")
            print(f"  Expected response schema: {json.dumps(e['requestedSchema'], indent=4)}")

    print("\n✓ Agent-mediated elicitation gives LLM control over the UX")


# =============================================================================
# Iteration 4: Elicitation vs Handoff — Two Complementary Patterns
# =============================================================================
# Elicitation: SERVER-initiated, structured, protocol-level
# Handoff:     AGENT-initiated, unstructured, application-level

def demo_comparison():
    """Compare MCP elicitation with agent handoff patterns."""
    print("\n" + "=" * 60)
    print("Iteration 4: Elicitation vs Handoff")
    print("=" * 60)

    print("""
    ┌─────────────────┬───────────────────────┬───────────────────────┐
    │ Aspect          │ MCP Elicitation       │ Agent Handoff (L47)   │
    ├─────────────────┼───────────────────────┼───────────────────────┤
    │ Initiated by    │ MCP Server (tool)     │ Agent (LLM)           │
    │ Trigger         │ -32042 error code     │ Agent judgment         │
    │ Data format     │ Structured schema     │ Free-form text        │
    │ Scope           │ Single tool call      │ Entire conversation   │
    │ Use case        │ Confirmation dialogs, │ Ambiguous tasks,      │
    │                 │ auth flows, dangerous │ expert escalation,    │
    │                 │ operations            │ missing context       │
    │ Response path   │ Tool retry or callback│ User message in chat  │
    │ SDK support     │ elicitation_callback  │ Custom tool/pattern   │
    └─────────────────┴───────────────────────┴───────────────────────┘

    When to use each:

    Elicitation:
    - Tool server needs confirmation before destructive action
    - OAuth/credential flow mid-tool-call
    - Server-side validation requires additional input
    - Schema-validated responses (boolean confirm, string reason, etc.)

    Handoff:
    - Agent is uncertain about user intent
    - Task requires human expertise the agent lacks
    - Conversation needs redirection
    - No structured response schema needed

    They compose well together:
    - Elicitation handles tool-level approval gates
    - Handoff handles conversation-level human judgment
    """)

    print("✓ Elicitation = server asks via protocol; Handoff = agent asks via judgment")


# =============================================================================
# Summary
# =============================================================================
# | Component              | Role                                          |
# |------------------------|-----------------------------------------------|
# | Error -32042           | MCP protocol: server needs user input         |
# | ElicitationErrorData   | Structured request: message + schema          |
# | elicitation_callback   | MCPClient param: programmatic handling        |
# | Agent-mediated         | No callback: agent sees error in tool result  |
# | vs Handoff (L47)       | Agent-initiated, free-form, conversation-wide |


if __name__ == "__main__":
    print("=" * 60)
    print("Level 60: MCP Elicitation (SDK v1.35)")
    print("=" * 60)

    demo_protocol_flow()
    demo_elicitation_callback()
    demo_agent_handling()
    demo_comparison()

    print("\n" + "=" * 60)
    print("Summary: Protocol → Callback → Agent Handling → vs Handoff")
    print("=" * 60)

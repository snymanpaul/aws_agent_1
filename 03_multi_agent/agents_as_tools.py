"""
Level 6: Agents-as-Tools Pattern (Updated for SDK v1.35)
=========================================================
Use specialist agents as tools for an orchestrator agent.

Key Concepts:
- Agent.as_tool() — explicit wrapping with name/description override
- Auto-wrapping — pass Agent instances directly in tools=[] list
- preserve_context — stateful vs stateless sub-agents
- Thread-safe concurrent access via internal locking

Prerequisites: L1-3 (basics, tools, custom tools)
Unlocks:       L7 (Swarm), L8 (Graph), L15 (Context Management)

Iterations:
  1. Legacy @tool Pattern   — the pre-v1.34 approach (deprecated, for reference)
  2. Agent.as_tool()        — explicit wrapping with control over name/description
  3. Auto-wrapping          — pass Agent instances directly in tools=[]
  4. preserve_context       — stateful sub-agents that remember across calls
  5. Full Orchestrator      — combined demo with all three specialists

Run: uv run python 03_multi_agent/agents_as_tools.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from tools import get_model

# Models
model = get_model("claude-sonnet-4")
fast_model = get_model("haiku")

# Sample code used across all iterations
SAMPLE_CODE = '''
def calculate_discount(price, discount_percent):
    if discount_percent > 100:
        discount_percent = 100
    discount = price * discount_percent / 100
    return price - discount
'''


# =============================================================================
# Iteration 1: Legacy @tool Pattern (pre-v1.34, deprecated)
# =============================================================================
# Before v1.34, wrapping an agent as a tool required a @tool closure.
# Problems: creates a new Agent per call, no state persistence, manual
# string conversion, no thread safety.

def demo_legacy_pattern():
    """Show the old @tool wrapper approach — kept for comparison only."""
    print("\n" + "=" * 60)
    print("Iteration 1: Legacy @tool Pattern (deprecated)")
    print("=" * 60)

    @tool
    def review_code(code: str) -> str:
        """Review code for bugs and best practices.

        Args:
            code: The code snippet to review
        """
        reviewer = Agent(
            model=fast_model,
            system_prompt="You are a code reviewer. Be concise (2-3 bullet points max).",
            callback_handler=None,
        )
        result = reviewer(f"Review this code:\n```python\n{code}\n```")
        return str(result)

    orchestrator = Agent(
        model=model,
        tools=[review_code],
        system_prompt="You coordinate code analysis. Use review_code for code review tasks.",
        callback_handler=None,
    )

    result = orchestrator(f"Review this code:\n```python\n{SAMPLE_CODE}\n```")
    print(f"\nResult:\n{result}")
    print("\n⚠️  Issue: Agent created fresh each call, no state, no thread safety")


# =============================================================================
# Iteration 2: Agent.as_tool() — Explicit Wrapping
# =============================================================================
# v1.34+ provides agent.as_tool(name=..., description=...) which returns an
# AgentTool with thread-safe locking, state snapshotting, and proper event
# streaming to the parent agent.

def demo_as_tool():
    """Show Agent.as_tool() — the modern explicit wrapping API."""
    print("\n" + "=" * 60)
    print("Iteration 2: Agent.as_tool() — Explicit Wrapping")
    print("=" * 60)

    # Create specialist agent with name + description (used as tool defaults)
    reviewer = Agent(
        model=fast_model,
        name="code_reviewer",
        description="Reviews code for bugs, security issues, and best practices",
        system_prompt="You are a code reviewer. Be concise (2-3 bullet points max).",
        callback_handler=None,
    )

    # Wrap as tool — name/description default from the agent's own attributes
    reviewer_tool = reviewer.as_tool()

    # Can also override name/description at wrapping time:
    # reviewer_tool = reviewer.as_tool(name="custom_name", description="Custom desc")

    orchestrator = Agent(
        model=model,
        tools=[reviewer_tool],
        system_prompt="You coordinate code analysis. Use code_reviewer for reviews.",
        callback_handler=None,
    )

    result = orchestrator(f"Review this code:\n```python\n{SAMPLE_CODE}\n```")
    print(f"\nResult:\n{result}")
    print("\n✓ Agent created once, reused across calls, thread-safe")


# =============================================================================
# Iteration 3: Auto-wrapping — Pass Agents Directly in tools=[]
# =============================================================================
# v1.34+ auto-wraps Agent instances in the tools list by calling .as_tool()
# with defaults. The agent's name becomes the tool name, its description
# becomes the tool description.

def demo_auto_wrap():
    """Show auto-wrapping — Agent instances passed directly in tools=[]."""
    print("\n" + "=" * 60)
    print("Iteration 3: Auto-wrapping — Agents in tools=[] directly")
    print("=" * 60)

    # Create three specialist agents — name and description are required
    # for auto-wrapping (they become the tool name and description)
    reviewer = Agent(
        model=fast_model,
        name="code_reviewer",
        description="Reviews code for bugs and best practices",
        system_prompt="You are a code reviewer. Be concise (2-3 bullet points).",
        callback_handler=None,
    )

    writer = Agent(
        model=fast_model,
        name="doc_writer",
        description="Writes clear technical documentation for code",
        system_prompt="You are a technical writer. Write a concise docstring.",
        callback_handler=None,
    )

    tester = Agent(
        model=fast_model,
        name="test_generator",
        description="Generates pytest unit tests for code",
        system_prompt="You are a test engineer. Write 2-3 pytest tests. Output only code.",
        callback_handler=None,
    )

    # Pass agents directly — SDK auto-wraps each via .as_tool()
    orchestrator = Agent(
        model=model,
        tools=[reviewer, writer, tester],
        system_prompt="""You coordinate a team of specialists.
Delegate to the appropriate agent(s) based on the task.
Synthesize results into a cohesive response.""",
        callback_handler=None,
    )

    result = orchestrator(f"""Analyze this function:
```python
{SAMPLE_CODE}
```
Give me: 1) code review, 2) a docstring, 3) two pytest tests.""")
    print(f"\nResult:\n{result}")
    print("\n✓ Three agents passed directly in tools=[] — zero boilerplate")


# =============================================================================
# Iteration 4: preserve_context — Stateful Sub-Agents
# =============================================================================
# By default, sub-agents reset to their initial state before each call
# (preserve_context=False). With preserve_context=True, the sub-agent
# remembers its conversation history across invocations.

def demo_preserve_context():
    """Show preserve_context=True vs False."""
    print("\n" + "=" * 60)
    print("Iteration 4: preserve_context — Stateful Sub-Agents")
    print("=" * 60)

    # Stateless (default) — each call starts fresh
    stateless_agent = Agent(
        model=fast_model,
        name="stateless_helper",
        description="Answers questions (forgets between calls)",
        system_prompt="You are a helpful assistant. Be very concise (1 sentence).",
        callback_handler=None,
    )
    stateless_tool = stateless_agent.as_tool(preserve_context=False)  # default

    # Stateful — remembers conversation across calls
    stateful_agent = Agent(
        model=fast_model,
        name="stateful_helper",
        description="Answers questions (remembers between calls)",
        system_prompt="You are a helpful assistant. Be very concise (1 sentence).",
        callback_handler=None,
    )
    stateful_tool = stateful_agent.as_tool(preserve_context=True)

    orchestrator = Agent(
        model=model,
        tools=[stateless_tool, stateful_tool],
        system_prompt="""You have two helpers:
- stateless_helper: forgets between calls
- stateful_helper: remembers between calls

When asked to test memory, call each helper with the same sequence of messages.""",
        callback_handler=None,
    )

    result = orchestrator("""Test memory:
1. Tell stateful_helper "My name is Alice"
2. Tell stateless_helper "My name is Alice"
3. Ask stateful_helper "What is my name?"
4. Ask stateless_helper "What is my name?"
Report what each helper answered.""")
    print(f"\nResult:\n{result}")
    print("\n✓ Stateful helper remembers; stateless helper does not")


# =============================================================================
# Iteration 5: Full Orchestrator — Production Pattern
# =============================================================================
# Combines auto-wrapping with as_tool() where we need preserve_context.

def demo_full_orchestrator():
    """Full orchestrator combining auto-wrap and explicit as_tool()."""
    print("\n" + "=" * 60)
    print("Iteration 5: Full Orchestrator — Production Pattern")
    print("=" * 60)

    # Auto-wrapped specialists (stateless, fresh each call)
    reviewer = Agent(
        model=fast_model,
        name="code_reviewer",
        description="Reviews code for bugs, security issues, and best practices",
        system_prompt="""You are an expert code reviewer. Your job is to:
1. Identify bugs and potential issues
2. Check for security vulnerabilities
3. Recommend best practices
Be concise but thorough.""",
        callback_handler=None,
    )

    writer = Agent(
        model=fast_model,
        name="doc_writer",
        description="Writes clear technical documentation",
        system_prompt="""You are a technical writer. Write clear, structured documentation.
Include parameter descriptions and return value. Be concise.""",
        callback_handler=None,
    )

    tester = Agent(
        model=fast_model,
        name="test_generator",
        description="Generates comprehensive pytest unit tests",
        system_prompt="""You are a testing specialist using pytest.
Write comprehensive tests covering edge cases. Output only test code.""",
        callback_handler=None,
    )

    # Orchestrator — auto-wraps the three specialists
    orchestrator = Agent(
        model=model,
        tools=[reviewer, writer, tester],
        system_prompt="""You are a senior software engineering lead.
You coordinate a team of specialists:
- code_reviewer: Reviews code for bugs and best practices
- doc_writer: Writes clear technical documentation
- test_generator: Generates unit tests

When given a task:
1. Determine which specialist(s) to delegate to
2. Call the appropriate agent(s)
3. Synthesize the results into a cohesive response""",
        callback_handler=None,
    )

    print("Task: Comprehensive code analysis")
    print("-" * 40)
    print(SAMPLE_CODE)
    print("-" * 40)

    result = orchestrator(f"""Analyze this Python function:

```python
{SAMPLE_CODE}
```

I need:
1. A code review identifying any issues
2. Documentation for the function
3. Unit tests using pytest

Coordinate with your team to provide a comprehensive analysis.""")
    print(f"\nResult:\n{result}")


# =============================================================================
# Summary
# =============================================================================
# | Pattern            | API                    | State    | Thread-safe |
# |--------------------|------------------------|----------|-------------|
# | @tool closure      | @tool def wrapper()    | None     | No          |
# | agent.as_tool()    | agent.as_tool(name=..) | Snapshot | Yes (lock)  |
# | Auto-wrap          | tools=[agent]          | Snapshot | Yes (lock)  |
# | preserve_context   | as_tool(preserve_..=T) | Shared   | Yes (lock)  |


if __name__ == "__main__":
    print("=" * 60)
    print("Level 6: Agents-as-Tools Pattern (SDK v1.35)")
    print("=" * 60)

    demo_legacy_pattern()
    demo_as_tool()
    demo_auto_wrap()
    demo_preserve_context()
    demo_full_orchestrator()

    print("\n" + "=" * 60)
    print("Summary: Legacy → as_tool() → Auto-wrap → preserve_context")
    print("=" * 60)

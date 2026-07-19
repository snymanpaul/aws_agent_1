"""
Level 2: Agent with Built-in Tools
===================================
Strands agent using pre-built tools from strands-agents-tools.

Key Concepts:
- Tools extend agent capabilities
- LLM decides when to use tools based on the task
- Tool results feed back into the agent's reasoning

Available tools in strands_tools:
- calculator: Math operations using SymPy
- current_time: Get current date/time
- file_read, file_write: File operations
- http_request: Make HTTP calls
- python_repl: Execute Python code
- shell: Run shell commands

Run: uv run python 01_basics/agent_with_tools.py
"""

from strands import Agent
from strands.models.openai import OpenAIModel
from strands_tools import calculator, current_time

# Configure model to use your local LiteLLM proxy
model = OpenAIModel(
    model_id="claude-sonnet-4",
    client_args={
        "base_url": "http://localhost:4000",
        "api_key": "sk-local"
    }
)

# Create agent with tools
agent = Agent(
    model=model,
    tools=[calculator, current_time]  # Give the agent these capabilities
)

print("=" * 60)
print("Level 2: Agent with Built-in Tools")
print("=" * 60)
print()

# Test 1: Time awareness
# Agent streams output to stdout by default via PrintingCallbackHandler
print("Test 1: Current time")
print("-" * 40)
agent("What time is it right now? What day of the week is it?")
print()

# Test 2: Calculator
print("Test 2: Calculator")
print("-" * 40)
agent("Calculate: What is 42 * 17 + 156 / 4?")
print()

# Test 3: Combined reasoning
print("Test 3: Combined reasoning")
print("-" * 40)
agent(
    "If I invest $10,000 at 7.5% annual interest compounded yearly, "
    "how much will I have after 5 years? Show your calculation."
)

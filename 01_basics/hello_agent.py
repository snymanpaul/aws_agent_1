"""
Level 1: Hello World Agent
===========================
The simplest possible Strands agent using your local LiteLLM proxy.

Key Concepts:
- Agent loop: prompt -> LLM reasoning -> response
- Model provider abstraction (OpenAI-compatible API via LiteLLM proxy)
- Same code works locally and in production

Run: uv run python 01_basics/hello_agent.py
"""

from strands import Agent
from strands.models.openai import OpenAIModel

# Configure model to use your local LiteLLM proxy (OpenAI-compatible API)
model = OpenAIModel(
    model_id="claude-sonnet-4",  # Model alias from your litellm_config.yaml
    client_args={
        "base_url": "http://localhost:4000",  # LiteLLM proxy
        "api_key": "sk-local"  # Your LITELLM_MASTER_KEY
    }
)

# Create the agent with the model
agent = Agent(model=model)

# Run a simple query
print("=" * 60)
print("Level 1: Hello World Agent")
print("=" * 60)
print()

# Agent streams output to stdout by default via PrintingCallbackHandler
agent("Hello! What are AI agents and why are they useful? Keep your response concise.")

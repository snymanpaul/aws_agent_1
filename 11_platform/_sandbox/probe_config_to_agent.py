"""
Probe: config_to_agent (experimental) — verify declarative agent creation in SDK 1.19.x

Tests dict-based config; verifies name, system prompt pass-through.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands.experimental.agent_config import config_to_agent

# Dict-based config (no model key — falls back to Bedrock default; we'll override via kwargs)
from strands.models.openai import OpenAIModel

model = OpenAIModel(
    model_id="claude-sonnet-4",
    client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
)

config = {
    "name": "WeatherAgent",
    "prompt": "You are a concise weather assistant. Answer in one sentence.",
}

agent = config_to_agent(config, model=model, callback_handler=None)

print(f"Agent name : {agent.name}")
print(f"Agent type : {type(agent).__name__}")

result = agent("What is the weather like in Cape Town today?")
print(f"Response   : {result}")

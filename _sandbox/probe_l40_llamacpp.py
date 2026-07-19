"""Probe: does LlamaCppModel work with Ollama's OpenAI-compatible endpoint?"""
from strands import Agent
from strands.models import LlamaCppModel

# Ollama serves OpenAI-compatible API at localhost:11434
model = LlamaCppModel(
    base_url="http://localhost:11434",
    model_id="llama3.2:3b",
)

agent = Agent(model=model, callback_handler=None)
result = agent("Reply with exactly: EDGE_OK")
print(result)

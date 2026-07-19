# L01: Hello World Agent

**Code:** `01_basics/hello_agent.py`
**Reflection:** [`levels-1-5-reflection.md`](../../.claude/learnings/reflections/levels-1-5-reflection.md)

### Level 1: Hello World Agent
**Goal:** Understand the basic agent loop

```python
from strands import Agent
from strands.models.openai import OpenAIModel

model = OpenAIModel(
    model_id="claude-sonnet-4",
    client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"}
)

agent = Agent(model=model)
agent("Hello! Tell me about AI agents.")  # Streams to stdout by default
```

**Key Concepts:**
- Agent loop: prompt -> LLM reasoning -> response
- Model provider abstraction (OpenAIModel for LiteLLM proxy)
- Default streaming via PrintingCallbackHandler

---

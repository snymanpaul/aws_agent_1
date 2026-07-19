# L03: Custom Tools

**Code:** `01_basics/custom_tools.py`
**Reflection:** [`levels-1-5-reflection.md`](../../.claude/learnings/reflections/levels-1-5-reflection.md)

### Level 3: Custom Tools
**Goal:** Create domain-specific tools

```python
from strands import Agent, tool

@tool
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp": 72, "condition": "sunny"}

agent = Agent(model=model, tools=[get_weather])
agent("What's the weather in Seattle?")
```

**Key Concepts:**
- @tool decorator converts functions to tools
- Docstrings = LLM instructions (affects tool selection)
- Type hints enable parameter validation

---

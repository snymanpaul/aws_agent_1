# L02: Built-in Tools

**Code:** `01_basics/agent_with_tools.py`
**Reflection:** [`levels-1-5-reflection.md`](../../.claude/learnings/reflections/levels-1-5-reflection.md)

### Level 2: Built-in Tools
**Goal:** Understand tool calling

```python
from strands import Agent
from strands_tools import calculator, current_time

agent = Agent(model=model, tools=[calculator, current_time])
agent("What time is it and what is 42 * 17?")
```

**Key Concepts:**
- Tools extend agent capabilities
- LLM decides WHEN to use tools based on task
- Tool results feed back into reasoning loop

---

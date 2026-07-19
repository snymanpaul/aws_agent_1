# L06: Agents-as-Tools Pattern

**Code:** `03_multi_agent/agents_as_tools.py`
**Reflection:** [`level-6-reflection.md`](../../.claude/learnings/reflections/level-6-reflection.md)

### Level 6: Agents-as-Tools Pattern
**Goal:** Hierarchical agent delegation

```python
@tool
def research_agent(query: str) -> str:
    """Delegate research tasks to specialist."""
    researcher = Agent(
        model=model,
        system_prompt="You are a research specialist..."
    )
    return str(researcher(query))

orchestrator = Agent(model=model, tools=[research_agent, code_agent])
```

**Key Concepts:**
- Agents can call other agents as tools
- Specialization improves quality
- Orchestrator coordinates specialists

---

# Level 6 Reflection: Agents-as-Tools Pattern

**Date:** 2025-12-10
**File:** `03_multi_agent/agents_as_tools.py`

## What We Built

Hierarchical multi-agent system with orchestrator pattern:
- **Orchestrator**: Senior engineering lead (sonnet) that delegates tasks
- **Specialists** (haiku): Code Reviewer, Documentation Writer, Test Generator

## Key Patterns

### 1. Agent Wrapping with @tool
```python
@tool
def specialist_agent(input: str) -> str:
    """Docstring becomes tool description."""
    agent = Agent(model=fast_model, system_prompt="...")
    return str(agent(input))  # Must convert to str
```

### 2. Model Hierarchy for Cost Efficiency
- Orchestrator: `claude-sonnet-4` (complex reasoning, coordination)
- Specialists: `claude-3-5-haiku` (fast, focused tasks)

### 3. Focused System Prompts
Specialists with narrow scope outperform generalists. Each specialist has:
- Clear role definition
- Specific responsibilities
- Output format guidance

## Insights

1. **Clean foundation matters**: No errors in Level 6 because Levels 1-5 established correct patterns (OpenAIModel, streaming, @tool decorator).

2. **LLM orchestration works**: The orchestrator correctly decided to call all 3 specialists for "comprehensive analysis" - no explicit routing logic needed.

3. **Return type conversion**: Agent responses must be `str(result)` when returned from tool functions.

## Questions for Future Levels

- How do Swarm patterns differ from this hierarchical model?
- Can specialists share context/memory?
- How to handle failures in specialist agents?

## Observations Logged

6 new observations added to `observations.jsonl`:
- 3 patterns (agents-as-tools, model-selection, specialist-agents)
- 3 insights (str conversion, orchestration, solid foundation)

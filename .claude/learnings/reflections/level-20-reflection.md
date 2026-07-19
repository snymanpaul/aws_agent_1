# Level 20: Meta-Agents - Reflection

**Date**: 2025-12-14
**Iterations**: 8
**Status**: Complete

## Summary

Level 20 introduces meta-agents - agents that create and modify other agents at runtime. This represents a significant step toward self-improving AI systems, building on the structured planning patterns from L19.

## Core Concept

**Meta-agents** are agents that operate at a higher level of abstraction, creating, configuring, and managing other agents rather than directly performing tasks. This enables:
- Dynamic agent composition based on task requirements
- Self-improvement through prompt optimization
- Reusable agent blueprints across sessions

## Iteration Breakdown

| # | Pattern | Key Learning |
|---|---------|--------------|
| 1 | Basic Agent Factory | JSON blueprints → runtime agent instantiation |
| 2 | Runtime Prompt Optimization | Test-based scoring drives prompt improvements |
| 3 | Dynamic Team Composition | Architect agent designs multi-agent teams |
| 4 | Self-Modifying Prompt Tuning | Evolutionary approach: mutate → evaluate → select |
| 5 | Graphiti-Persisted Meta-Learning | Store successful blueprints for cross-session reuse |
| 6 | Blueprint Validation | Catch errors before instantiation (tools, model, prompt) |
| 7 | Parallel Agent Creation | ThreadPoolExecutor for ~2x speedup |
| 8 | Mermaid Visualization | Generate flowcharts from team structures |

## Key Patterns

### 1. Agent Blueprint Model
```python
class AgentBlueprint(BaseModel):
    name: str
    description: str
    system_prompt: str
    model_alias: str = "haiku"
    tools: list[str] = []
```

### 2. Tool Registry Pattern
```python
TOOL_REGISTRY = {
    "calculator": calculator,
    "file_read": file_read,
    "file_write": file_write,
}

def get_tools_by_names(tool_names: list[str]) -> list:
    return [TOOL_REGISTRY[name] for name in tool_names if name in TOOL_REGISTRY]
```

### 3. Factory Agent Prompt
```python
factory_prompt = """You are an Agent Factory.
Output ONLY valid JSON blueprint:
{
    "name": "agent_name",
    "description": "...",
    "system_prompt": "...",
    "model_alias": "haiku",
    "tools": ["tool_name"]
}"""
```

## Comparison to Previous Levels

| Dimension | L18: Debate | L19: Planning | L20: Meta-Agents |
|-----------|------------|---------------|------------------|
| **Focus** | Adversarial reasoning | Task execution | Agent creation |
| **Iterations** | 5 | 9 | 8 |
| **Output** | Decisions | Artifacts | Agents |
| **Meta-level** | No | No | Yes |
| **Parallelism** | No | Yes (DAG) | Yes (creation) |

## Key Learnings

1. **Blueprint-Based Creation**: JSON schemas make agent creation declarative and reproducible
2. **Tool Registry**: Mapping tool names to functions enables dynamic tool assignment
3. **Validation First**: Check blueprint validity before instantiation to catch errors early
4. **Thread Safety**: Same lesson as L19 - fresh agent instance per thread
5. **Parallel Speedup**: ~2x speedup for team creation with ThreadPoolExecutor
6. **Self-Improvement**: Evolutionary prompt tuning works but needs harder test cases to show improvement
7. **Mermaid Integration**: Visual diagrams help understand agent hierarchies

## Observations

### Patterns That Worked Well
- Factory agents reliably produce valid JSON when given clear schemas
- Blueprint validation catches common errors (unknown tools, invalid models)
- Team composition naturally maps to agents-as-tools pattern from L6

### Areas for Improvement
- Test cases for prompt optimization were too easy (100% baseline)
- Could add more sophisticated mutation strategies
- Mermaid browser preview failed but diagrams generated correctly

### MCP Integrations Verified
- **Graphiti**: Real persistence to `aws_agent_1-meta-agents` group
  - Facts extracted: agent role, model, tools, descriptions
  - Searchable via `search_memory_facts`
- **Mermaid**: Diagram generation works (browser preview failed in headless env)

## Connection to Future Levels

L20 provides foundation for:
- **L24 (Tool Synthesis)**: Agents creating tools, not just agents
- **L25 (Self-Improving Agents)**: More sophisticated self-modification beyond prompts

## Code Statistics

- **File**: `07_advanced_multiagent/meta_agents.py`
- **Lines**: ~1250
- **Iterations**: 8
- **Data Models**: AgentBlueprint, TeamBlueprint, PromptEvolution, ValidationResult

## Questions Answered

1. **Can agents create other agents?** Yes, via factory pattern with JSON blueprints
2. **Can agents improve themselves?** Yes, through prompt mutation and selection
3. **How to validate agent configs?** Check tools, models, prompt quality before instantiation
4. **How to parallelize creation?** ThreadPoolExecutor with fresh agent per thread

## Observations Captured

| Category | Count | Key Topics |
|----------|-------|------------|
| Patterns | 5 | AgentBlueprint, Tool Registry, Blueprint Validation, Parallel Creation, TeamBlueprint |
| Mistakes | 2 | Easy test cases, LiteLLM restart during benchmark |
| Insights | 3 | Calculator crutch, Graphiti persistence, Mermaid headless |

**Graphiti Sync**: ✅ 5 observations synced to `aws_agent_1-learnings`

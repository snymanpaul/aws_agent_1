# Level 7 Reflection: Swarm Pattern

**Date:** 2025-12-10
**File:** `03_multi_agent/swarm_example.py`

## What We Built

Peer-to-peer software development team:
- **researcher**: Gathers requirements
- **architect**: Designs solution
- **coder**: Implements code
- **reviewer**: Reviews and concludes (FINAL step)

## Key Difference from Level 6

| Aspect | Level 6 (Agents-as-Tools) | Level 7 (Swarm) |
|--------|---------------------------|-----------------|
| Coordination | Hierarchical | Peer-to-peer |
| Control | Orchestrator decides | Agents decide |
| Handoffs | Explicit tool calls | `handoff_to_agent()` |
| Context | Via tool returns | Built-in shared memory |

## Mistakes Made

### 1. Swarm API Misuse
```python
# Wrong
Swarm(agents=[a1, a2, ...])

# Correct
Swarm([a1, a2, ...])  # Positional argument
```

### 2. Ping-Pong Loop
First run failed because coder↔reviewer kept handing off to each other.
- **Time**: 145s, Status: FAILED
- **Sequence**: researcher→architect→coder→reviewer→coder→reviewer→...

## Patterns That Worked

### 1. Ping-Pong Prevention
```python
Swarm(
    [agents...],
    repetitive_handoff_detection_window=5,
    repetitive_handoff_min_unique_agents=3,
)
```

### 2. Clear Final Agent Prompt
```python
reviewer = Agent(
    system_prompt="""...
    IMPORTANT: You are the FINAL step.
    - Do NOT hand off to other agents
    - Complete the review yourself"""
)
```

### 3. Result After Fixes
- **Time**: 53s, Status: COMPLETED
- **Sequence**: researcher→architect→coder→reviewer (clean!)

## Insights

1. **Swarm has built-in shared context**: Original request, agent history, and knowledge from previous agents are automatically available. No manual plumbing.

2. **Safety parameters are essential**: `max_handoffs`, `max_iterations`, `execution_timeout`, `node_timeout`, `repetitive_handoff_detection`. Use all of them.

3. **Performance impact of proper guards**: 3x faster (145s → 53s) + success vs failure.

## Open Questions for Future Levels

- How do Graph workflows compare to Swarm?
- Can we combine patterns (e.g., Swarm within a Graph)?
- How to debug agent decision-making in swarms?

## Observations Logged

8 new observations added to `observations.jsonl`:
- 2 mistakes (API misuse, ping-pong)
- 3 patterns (prevention, final prompt, safety params)
- 3 insights (swarm vs hierarchical, shared context, performance)

# L07: Swarm Pattern

**Code:** `03_multi_agent/swarm_example.py`
**Reflection:** [`level-7-reflection.md`](../../.claude/learnings/reflections/level-7-reflection.md)

### Level 7: Swarm Pattern
**Goal:** Peer-to-peer agent collaboration

```python
from strands.multiagent import Swarm

swarm = Swarm(
    [agent1, agent2, agent3],        # positional list of agents
    entry_point=agent1,
    max_handoffs=10,
    repetitive_handoff_detection_window=5,   # prevents ping-pong loops
    repetitive_handoff_min_unique_agents=3,
)
result = swarm("Analyze this architecture...")
```

**Key Concepts:**
- No single orchestrator — agents hand off to each other
- Handoff caps and ping-pong detection keep the loop bounded
- Parallel execution

---

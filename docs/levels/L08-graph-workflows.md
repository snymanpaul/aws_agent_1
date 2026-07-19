# L08: Graph Workflows

**Code:** `03_multi_agent/graph_workflow.py`
**Reflection:** [`level-8-v142-reflection.md`](../../.claude/learnings/reflections/level-8-v142-reflection.md)

### Level 8: Graph Workflows
**Goal:** Structured agent workflows (DAG)

```python
from strands.multiagent import GraphBuilder

graph = GraphBuilder()
graph.add_node("planner", planner_agent)
graph.add_node("executor", executor_agent)
graph.add_node("reviewer", reviewer_agent)
graph.add_edge("planner", "executor")
graph.add_edge("executor", "reviewer")
```

**Key Concepts:**
- DAG-based workflows
- Conditional routing
- Complex task decomposition

---

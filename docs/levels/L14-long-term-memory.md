# L14: Long-term Memory

**Code:** `06_memory/longterm_memory.py`
**Reflection:** [`level-14-reflection.md`](../../.claude/learnings/reflections/level-14-reflection.md)

### Level 14: Long-term Memory
**Goal:** Memory that persists across sessions

**Three Memory Layers:**
| Layer | What | Where | Persistence |
|-------|------|-------|-------------|
| Working | Current conversation | SessionManager | Session only |
| Episodic | Specific events | Graphiti/JSON | Cross-session |
| Semantic | Facts/knowledge | ChromaDB/Graphiti | Cross-session |

**6 Progressive Iterations:**
1. Local JSON (keyword search)
2. ChromaDB (semantic vector search)
3. Graphiti (graph + temporal facts)
4. Mem0 (SOTA comparison)
5. Memory-Augmented Agent
6. Cross-Session Persistence Demo

**Key Patterns:**
```python
# Episodic memory (events)
@tool
def remember_event(event: str, context: str = "") -> str:
    """Store interaction in episodic memory."""
    episodic_memory.store(event, context)

# Semantic memory (facts)
@tool
def learn_fact(entity: str, fact_type: str, value: str) -> str:
    """Store fact in semantic memory."""
    semantic_memory.store(entity, fact_type, value)

# Memory-augmented agent
agent = Agent(
    model=model,
    session_manager=FileSessionManager(...),  # Working
    tools=[remember_event, learn_fact, recall_*]  # Long-term
)
```

**Key Insight:** Search evolution matters:
- Keyword: Simple but limited ("Python" doesn't find "programming")
- Semantic: Meaning-based ("code bugs" finds "debugging")
- Graph: Relationships + temporal validity

---

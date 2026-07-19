# L17: Graph Memory Deep Dive

**Code:** `06_memory/graph_memory_benchmark.py`
**Reflection:** [`level-17-reflection.md`](../../.claude/learnings/reflections/level-17-reflection.md)

### Level 17: Graph Memory Deep Dive
**Goal:** Test graph database strengths that vector DBs cannot match

**Infrastructure (SDK Approach - Recommended):**
| Component | Connection | Isolation | Notes |
|-----------|------------|-----------|-------|
| FalkorDB | `localhost:6379` | Named graphs | Direct Cypher OR via Graphiti SDK |
| Graphiti SDK | `pip install graphiti-core` | `group_id` | Connects to FalkorDB, adds temporal facts |
| LanceDB | Directory path | Directories | Baseline vector comparison |

**Critical Gotchas (from prior Graphiti benchmarking):**
- **LiteLLM incompatible** with Graphiti structured outputs (wraps JSON in markdown)
- Use **direct GeminiClient** for entity extraction (87% recall)
- Entity types must be **list, not dict**: `[PersonEntity, TechEntity]`
- Pass entity_types to `add_episode()`, NOT `Graphiti.__init__()`
- Embedding dimension **locked** once set (use 1536-dim consistently)

**5 Iterations:**

1. **Graphiti SDK Setup** - Direct FalkorDB connection via SDK
   ```python
   driver = FalkorDriver(host='localhost', port=6379)
   graphiti = Graphiti(graph_driver=driver, llm_client=GeminiClient(...))
   await graphiti.add_episode(..., group_id="l17_benchmark")
   ```
   - Learn: SDK vs MCP tradeoffs, async patterns

2. **Temporal Query Benchmark** - Test time-aware facts
   - "What was true before the LanceDB iteration?"
   - "Which facts have been superseded?"
   - Compare: Vector DBs have NO temporal awareness

3. **Multi-Hop Reasoning Benchmark** - 2-3 hop traversals
   - "What technologies are compared to ChromaDB and what are their tradeoffs?"
   - "Starting from 'memory architecture', what connects to it?"
   - Expected: Graphiti excels, vectors fail

4. **Knowledge Update Semantics** - Fact versioning
   - Add conflicting information, verify old facts marked `invalid_at`
   - Test graph consistency over time
   - Compare: Vectors overwrite, graphs version

5. **Graph-Augmented Agent** - Practical integration
   - Agent with Graphiti SDK tools (not MCP)
   - Demonstrate relationship reasoning in conversation

**Key Concepts:**
- Graphiti SDK async patterns (`await graphiti.add_episode()`)
- Direct GeminiClient for entity extraction
- Temporal fact validity (`valid_at`, `invalid_at`, `expired_at`)
- Multi-hop vs single-hop retrieval
- Graph memory vs vector memory tradeoffs

**Existing Data:**
- `benchmark-094640` group: 134 observations with extracted entities
- An unrelated personal graph shares the same FalkorDB in its own group (isolated, don't modify)

---

# Level 16 Reflection: Unified Memory Architecture

**Date**: 2025-12-12 (Updated)
**Status**: Complete (10 Iterations + Benchmark + MCP Fix + LanceDB)
**Observations**: 34 captured (8 new from LanceDB Iteration 10), synced to Graphiti

## Executive Summary

**The uncomfortable truth**: Graphiti is NOT faster than ChromaDB. Each iteration added *capability*, not *speed*. The 40% context rule (L15) had more performance impact than any memory backend choice.

## What Was Built

A unified memory system (~2700 lines) integrating all memory layers from L5, L13, L14, L15 into a cohesive architecture with 10 progressive iterations:

1. **Memory Facade** - Manual routing with `MemoryConfig` dataclass
2. **Intelligent Router** - Auto-classification via pattern matching
3. **Context-Aware Retrieval** - Token budget management
4. **Automatic Compression** - 40% rule enforcement
5. **Unified Memory Agent** - Complete tool integration
6. **Cross-Session Persistence** - Lifecycle demonstration
7. **Graphiti MCP Integration** - REAL MCP calls to graph database
8. **Document Memory Layer** - RAG integration from L13
9. **NLP Entity Extraction** - spaCy-based extraction replacing regex
10. **LanceDB Memory Backend** - Vector DB with BYOE pattern, local/API embeddings

## Key Learnings

### 1. MCP Client Connectivity (Critical!)

Finding the correct MCP transport was challenging. Key learnings:

```python
# Check project's .mcp.json for server config:
# {"mcpServers": {"graphiti-memory": {"command": "npx", "args": ["-y", "mcp-remote", "http://localhost:8000/mcp"]}}}

# Use Streamable HTTP transport, NOT SSE
from mcp.client.streamable_http import streamablehttp_client
MCPClient(lambda: streamablehttp_client("http://localhost:8000/mcp"))

# call_tool_sync requires tool_use_id as first parameter!
result = client.call_tool_sync(tool_use_id, "tool_name", {args})
```

**Lesson**: Always check `.mcp.json` for endpoint (`/mcp` vs `/sse`). Use correct transport (`streamable_http` for HTTP-based servers). The `call_tool_sync` signature requires `tool_use_id`.

### 2. Unified Facade Pattern

`UnifiedMemory` hides backend differences (JSON, ChromaDB, Graphiti) behind a consistent API:

```python
memory = UnifiedMemory(config)
memory.store(content, layer="auto")  # Auto-routes
memory.recall(query, budget_tokens=2000)  # Budget-aware
```

**Lesson**: Backend-agnostic interfaces enable swapping implementations without changing agent code.

### 3. Pattern-Based Routing

Simple regex patterns effectively classify content:
- `"prefers|likes|uses"` → semantic
- `"discussed|met|happened"` → episodic

**Lesson**: Don't overcomplicate classification. Heuristics work well for common cases.

### 4. NLP Entity Extraction

spaCy outperforms regex for entity extraction:

```python
nlp = spacy.load("en_core_web_sm")
doc = nlp(text)
entities = [(ent.text, ent.label_) for ent in doc.ents]
# Returns: [("Python", "ORG"), ("TensorFlow", "PRODUCT")]
```

**Lesson**: Use NLP for production entity extraction; regex for prototypes.

### 5. Document Layer Integration

ChromaDB's document layer completes the 4-layer architecture:
- Working: Current session
- Episodic: Past events
- Semantic: Facts/knowledge
- Document: RAG knowledge base

**Lesson**: Each layer has a specific purpose; the facade unifies access.

### 6. Backend Selection Guide

| Backend | Use Case | Tradeoff |
|---------|----------|----------|
| JSON | Prototyping, simple apps | No semantic search |
| ChromaDB | Semantic search needed | Local only, auto-embeddings |
| LanceDB | Full embedding control, offline-first | BYOE complexity |
| Graphiti | Relationships, temporal facts | MCP server + FalkorDB |

**Lesson**: Start simple (JSON), graduate to ChromaDB or LanceDB for semantic search, add Graphiti for relationships.

## What Worked Well

1. **Progressive iteration structure** - Each iteration builds cleanly on previous
2. **Tool reuse from L14/L15** - `EpisodicMemory`, `SemanticMemory`, `TokenBudget`
3. **REAL MCP integration** - Actual calls to Graphiti via Streamable HTTP
4. **spaCy NLP** - Much better entity extraction than regex
5. **Demo functions** - Each iteration has clear, runnable demonstration

## Patterns for Future Levels

1. **Facade + Adapters** - Central facade with backend-specific adapters
2. **Config-driven behavior** - Dataclass config with sensible defaults
3. **MCP client pattern** - Check `.mcp.json`, use correct transport
4. **NLP integration** - spaCy for production entity work

## Integration with Previous Levels

| Level | What It Contributed |
|-------|---------------------|
| L5 | `FileSessionManager` for working memory |
| L13 | ChromaDB patterns for document search |
| L14 | `EpisodicMemory`, `SemanticMemory` classes |
| L15 | `TokenBudget`, `HierarchicalSummarizer`, 40% rule |

## File Stats

- **unified_memory.py**: ~2700 lines
- **10 iterations** with demos
- **10+ tools** for agent use
- **4 memory layer adapters** (Working, Episodic, Semantic, Document)
- **5 backend adapters** (JSON, ChromaDB, Graphiti, OpenMemory, LanceDB)
- **Dependencies**: chromadb, spacy, mcp, strands-agents, lancedb, sentence-transformers, pyarrow

## Debugging Notes

MCP connection issues encountered and resolved:
1. **404 on `/sse`** - Wrong endpoint; server uses `/mcp`
2. **400 Bad Request** - Wrong transport; use `streamable_http`, not `sse`
3. **`'MCPAgentTool' has no attribute 'name'`** - Use `tool_name` attribute
4. **Validation error on `call_tool_sync`** - Missing `tool_use_id` parameter

## Mistakes Made

1. **Simulated instead of real MCP calls** - Overthought the problem, created mocks when server was running
2. **Didn't check .mcp.json first** - Guessed endpoints instead of reading config
3. **Wrong transport assumption** - Assumed SSE when server used Streamable HTTP
4. **Described features, not insights** - Initially reported "what was built" not "what was learned"
5. **MCP URL missing trailing slash** - `http://localhost:8000/mcp` vs `http://localhost:8000/mcp/` caused connection failures
6. **Malformed settings.local.json** - Complex bash permission entries with escaped quotes broke Claude Code config parsing

## Performance Reality

| Backend | Latency | When to Use |
|---------|---------|-------------|
| JSON | ~0ms | Prototypes, simple apps |
| ChromaDB | ~100ms | Semantic search, real-time queries |
| Graphiti | ~200ms+ | Accumulated data, relationship reasoning |
| spaCy NLP | ~50ms | Production entity extraction |

**Key insight**: Simpler is faster. Add complexity only when capability is needed.

## Open Questions

1. How does Graphiti perform with 1000+ accumulated memories over weeks?
2. What's the optimal layer weight allocation for different query types?
3. Can we benchmark the 40% rule's impact on agent reasoning quality?

## Benchmark Results (4-System Comparison)

After implementing the unified memory architecture, we ran a comparative benchmark using 112 real learning observations across 4 memory systems:

### Final Results (2025-12-12 with Real Graphiti MCP + LanceDB Iteration 10)

| System | Store Time | Warm Query | Recall | Architecture |
|--------|------------|------------|--------|--------------|
| JSON | 72ms | 0.3ms | 0.12 | Keyword search |
| ChromaDB | 37,595ms | 319ms | **0.62** | Vector similarity |
| **LanceDB_Local** | 9,664ms | **98ms** | **0.62** | Vector (384-dim local) |
| **LanceDB_API** | 59,702ms | 329ms | **0.62** | Vector (1536-dim API) |
| Graphiti | 1,376ms | 277ms | 0.26 | Knowledge graph |
| OpenMemory | 2,123ms | 778ms | 0.59 | 5-sector cognitive |

**Key Findings**:
1. All three vector DBs (LanceDB_Local, LanceDB_API, ChromaDB) tie at **62% recall**
2. LanceDB_Local has **fastest warm queries (98ms)** - 3x faster than ChromaDB (319ms)
3. 1536-dim API embeddings don't improve recall over 384-dim local embeddings
4. LanceDB_API slower due to network latency for each embedding call

### Key Benchmark Insights

1. **Async Processing Gotcha**: Graphiti returns immediately from store calls but processes entities asynchronously via LLM (~12.7s per episode). Must wait for processing before querying.

2. **Two-Phase Benchmark Pattern**: For async systems, split into `benchmark_store.py` (stores data, saves state) and `benchmark_query.py` (runs after processing).

3. **Architecture vs Metrics Mismatch**: Keyword recall favors vector stores. Graphiti's low recall (12%) doesn't mean it's worse - it extracts entities and relationships, not raw content. Its value is multi-hop reasoning, not keyword search.

4. **API Endpoint Matters**: Graphiti's `search_memory_facts` searches relationships (edges), `search_nodes` searches entities. Wrong choice = wrong results.

5. **OpenMemory Integration**: 5-sector cognitive model with Bearer auth. Returns `matches` key (not `results`). Good recall (54%) with automatic sector classification.

### When to Use Each System

| System | Best For | Avoid When |
|--------|----------|------------|
| JSON | Prototypes, debugging | Need semantic search |
| ChromaDB | Real-time semantic search, auto-embeddings | Full embedding control needed |
| **LanceDB** | BYOE control, faster warm queries, local-first | Need automatic embeddings |
| Graphiti | Accumulated data, temporal queries, "What connects X to Y?" | Real-time queries, keyword search |
| OpenMemory | Cognitive-aligned storage, multi-type memory | Simple key-value needs |

### Iteration 10: LanceDB Insights

1. **BYOE Pattern**: LanceDB requires you to compute embeddings yourself (Bring Your Own Embeddings). This gives more control but adds complexity vs ChromaDB's automatic embedding.

2. **Model Caching Critical**: Cold queries are 3.6s due to model loading; warm queries drop to 132ms. Cache the embedding model at module level:
   ```python
   _EMBEDDING_MODEL = None
   def get_local_embedding_model():
       global _EMBEDDING_MODEL
       if not _EMBEDDING_MODEL:
           _EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
       return _EMBEDDING_MODEL
   ```

3. **PyArrow Schema Required**: LanceDB needs explicit schema with vector dimensions:
   ```python
   schema = pa.schema([
       pa.field('event', pa.string()),
       pa.field('vector', pa.list_(pa.float32(), 384)),  # dimension must match!
   ])
   ```

4. **Dimension Parity**: Local (384-dim) and API (1536-dim) embeddings need different schemas. Can't mix them in same table.

5. **API Auth**: LiteLLM proxy requires valid authentication - won't work with dummy keys. Local embeddings work offline.

### Files Created

- `06_memory/benchmark_store.py` - Phase 1: Store to all systems
- `06_memory/benchmark_query.py` - Phase 2: Query and compare
- `06_memory/benchmark_state.json` - Shared state between phases

## Next Steps

Level 16 completes the Memory Architecture tier (L14-16). The next tier could focus on:
- Production deployment patterns
- Multi-agent memory coordination
- Memory optimization and caching
- Multi-hop reasoning benchmarks for Graphiti

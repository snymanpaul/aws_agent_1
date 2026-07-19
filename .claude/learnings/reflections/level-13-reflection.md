# Level 13 Reflection: RAG Integration

**Date**: 2025-12-11
**Focus**: Retrieval-Augmented Generation with ChromaDB and LanceDB

## What Was Built

Three progressive iterations of RAG implementation:

| Iteration | Vector Store | Doc Source | Embeddings | Key Finding |
|-----------|--------------|------------|------------|-------------|
| 1 | ChromaDB | README (marketing) | Local 384-dim | Low relevance |
| 2 | ChromaDB | Technical docs | Local 384-dim | 2/3 validation PASS |
| 3 | LanceDB | Technical docs | Both compared | API ~15% better |

### Files Created
- `05_advanced/rag_integration.py` - ChromaDB implementation (Iter 1→2)
- `05_advanced/rag_lancedb.py` - LanceDB with embedding comparison (Iter 3)

## Key Patterns

### ChromaDB Setup (Simple)
```python
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="docs")
collection.add(documents=[...], ids=[...])
results = collection.query(query_texts=["query"], n_results=3)
```

### LanceDB Setup (Flexible)
```python
db = lancedb.connect("./lance_vectors")
data = [{"text": chunk, "vector": embedding} for ...]
table = db.create_table("docs", data)
results = table.search(query_vector).limit(3).to_pandas()
```

### RAG Tool Pattern
```python
@tool
def search_knowledge_base(query: str) -> str:
    """Search KB - use for Strands questions."""
    results = collection.query(query_texts=[query], n_results=3)
    return format_passages(results)
```

## Key Insights

1. **Document quality > embedding model** - Technical docs outperformed marketing README more than embedding model choice affected results

2. **API embeddings ~15% better** - text-embedding-3-small (1536-dim) consistently outperformed all-MiniLM-L6-v2 (384-dim) in relevance scores

3. **ChromaDB vs LanceDB trade-offs**:
   - ChromaDB: Auto-embeddings, simpler setup, good for prototyping
   - LanceDB: BYOE, more flexible, hybrid search, better for production

4. **Validation is crucial** - Expected answer keywords enabled objective RAG quality measurement

## Mistakes Made

1. **Marketing docs for RAG** - First iteration's low relevance taught the importance of technical content

2. **urllib3 dependency conflict** - Had to recreate .venv when dependencies conflicted

3. **Missing pandas for LanceDB** - to_pandas() requires explicit pandas dependency

## Open Questions

1. How does LanceDB hybrid search (vector + SQL) compare in practice?
2. What's the cost/benefit of text-embedding-3-large (3072-dim)?
3. How to handle document updates in production RAG systems?

## Observations Captured

12 observations added to `observations.jsonl`:
- 3 mistakes (doc quality, urllib3, pandas)
- 5 patterns (ChromaDB, LanceDB, multi-source, validation, tool wrapper)
- 4 insights (raw URLs, embeddings, doc quality, chunking)

## Graphiti Sync Status

✅ 6 key observations synced to `aws_agent_1-learnings` graph

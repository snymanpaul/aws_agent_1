"""
Level 13: RAG Integration - Iteration 3 (LanceDB + Embedding Comparison)
========================================================================
Comparing vector stores (ChromaDB vs LanceDB) and embedding models
(local sentence-transformers vs API text-embedding-3-small).

Key Concepts:
- LanceDB as alternative to ChromaDB
- Embedding model comparison (local vs API)
- Trade-offs: speed vs accuracy vs cost

Run: uv run python 05_advanced/rag_lancedb.py
"""

import sys
sys.path.insert(0, ".")

import os
import lancedb
import requests
import numpy as np
from sentence_transformers import SentenceTransformer
from strands import Agent, tool
from tools import get_model

# Use sonnet for reliable tool-use
model = get_model("claude-sonnet-4")

# =============================================================================
# Configuration
# =============================================================================
LANCE_DB_PATH = "./lance_vectors"
LITELLM_URL = "http://localhost:4000/v1/embeddings"

# Same documentation sources as Iteration 2
DOCS_SOURCES = [
    {
        "url": "https://raw.githubusercontent.com/strands-agents/docs/main/docs/user-guide/concepts/tools/custom-tools.md",
        "name": "Custom Tools Guide"
    },
    {
        "url": "https://raw.githubusercontent.com/strands-agents/docs/main/docs/user-guide/concepts/multi-agent/multi-agent-patterns.md",
        "name": "Multi-Agent Patterns"
    },
    {
        "url": "https://raw.githubusercontent.com/strands-agents/docs/main/docs/user-guide/concepts/multi-agent/agents-as-tools.md",
        "name": "Agents-as-Tools Pattern"
    }
]

# Expected answers for validation
EXPECTED_ANSWERS = {
    "How do I create a tool in Strands?": {
        "keywords": ["@tool", "decorator", "type hints", "docstring"],
        "description": "@tool decorator on a function with type hints and docstring"
    },
    "What are the multi-agent patterns in Strands?": {
        "keywords": ["Agents-as-Tools", "Swarm", "Graph"],
        "description": "Agents-as-Tools (hierarchical), Swarm (autonomous), Graph (deterministic)"
    }
}

# Fallback content
SAMPLE_CONTENT = """
# Strands Agents - Custom Tools

The @tool decorator transforms functions into agent tools.
Use type hints and docstrings for automatic specification generation.

## Multi-Agent Patterns

Three primary patterns:
1. Agents-as-Tools: Hierarchical delegation with orchestrator agent
2. Swarm: Autonomous agent collaboration with handoffs
3. Graph: Deterministic workflow with defined edges
"""

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


# =============================================================================
# Helper Functions
# =============================================================================
def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    if not text:
        return []
    chunks = []
    position = 0
    while position < len(text):
        end = min(position + chunk_size, len(text))
        chunk = text[position:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        position = end - overlap
    return chunks


def fetch_docs() -> str:
    """Fetch documentation from GitHub sources."""
    all_content = []
    for source in DOCS_SOURCES:
        try:
            print(f"  Fetching {source['name']}...")
            response = requests.get(source["url"], timeout=10)
            response.raise_for_status()
            all_content.append(f"\n# SOURCE: {source['name']}\n{response.text}")
        except requests.RequestException as e:
            print(f"    Error: {e}")
    return "\n".join(all_content) if all_content else SAMPLE_CONTENT


# =============================================================================
# Embedding Functions
# =============================================================================
# Load local model once
_local_model = None

def get_local_model():
    """Lazy load the local sentence transformer model."""
    global _local_model
    if _local_model is None:
        print("  Loading local model (all-MiniLM-L6-v2)...")
        _local_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _local_model


def embed_local(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using local sentence-transformers (384-dim)."""
    model = get_local_model()
    embeddings = model.encode(texts)
    return embeddings.tolist()


def embed_api(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using LiteLLM API (1536-dim)."""
    try:
        response = requests.post(
            LITELLM_URL,
            json={
                "model": "text-embedding-3-small",
                "input": texts
            },
            headers={"Authorization": "Bearer sk-local"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return [d["embedding"] for d in data["data"]]
    except Exception as e:
        print(f"  API embedding error: {e}")
        print("  Falling back to local embeddings...")
        return embed_local(texts)


# =============================================================================
# LanceDB Operations
# =============================================================================
def create_lancedb_table(table_name: str, chunks: list[str], use_api: bool = False):
    """Create LanceDB table with embeddings."""
    db = lancedb.connect(LANCE_DB_PATH)

    # Generate embeddings
    embed_fn = embed_api if use_api else embed_local
    print(f"  Generating {'API' if use_api else 'local'} embeddings for {len(chunks)} chunks...")
    embeddings = embed_fn(chunks)

    # Prepare data
    data = [
        {
            "text": chunk,
            "vector": embedding,
            "chunk_id": i
        }
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]

    # Create table (drop if exists)
    if table_name in db.table_names():
        db.drop_table(table_name)

    table = db.create_table(table_name, data)
    print(f"  Created table '{table_name}' with {len(chunks)} rows")
    return table


def search_lancedb(table_name: str, query: str, use_api: bool = False, limit: int = 3):
    """Search LanceDB table."""
    db = lancedb.connect(LANCE_DB_PATH)
    table = db.open_table(table_name)

    # Get query embedding
    embed_fn = embed_api if use_api else embed_local
    query_embedding = embed_fn([query])[0]

    # Search
    results = table.search(query_embedding).limit(limit).to_pandas()
    return results


# =============================================================================
# Demo 1: Building LanceDB Knowledge Base
# =============================================================================
def build_kb_demo():
    """Build knowledge bases with both embedding types."""
    print("\n" + "=" * 60)
    print("Demo 1: Building LanceDB Knowledge Base")
    print("=" * 60)

    # Fetch docs
    print("\nFetching documentation...")
    content = fetch_docs()
    chunks = chunk_text(content)
    print(f"Total: {len(content):,} chars -> {len(chunks)} chunks")

    # Create table with local embeddings
    print("\n--- Local Embeddings (all-MiniLM-L6-v2, 384-dim) ---")
    create_lancedb_table("strands_local", chunks, use_api=False)

    # Create table with API embeddings (if LiteLLM is running)
    print("\n--- API Embeddings (text-embedding-3-small, 1536-dim) ---")
    try:
        create_lancedb_table("strands_api", chunks, use_api=True)
    except Exception as e:
        print(f"  Skipped API table: {e}")
        print("  (Make sure LiteLLM proxy is running on localhost:4000)")

    return len(chunks)


# =============================================================================
# Demo 2: Embedding Model Comparison
# =============================================================================
def embedding_comparison_demo():
    """Compare search results from local vs API embeddings."""
    print("\n" + "=" * 60)
    print("Demo 2: Embedding Model Comparison")
    print("=" * 60)

    db = lancedb.connect(LANCE_DB_PATH)
    has_api_table = "strands_api" in db.table_names()

    test_queries = [
        "How do I create a tool in Strands?",
        "What are the multi-agent patterns in Strands?"
    ]

    for query in test_queries:
        print(f"\nQuery: \"{query}\"")
        expected = EXPECTED_ANSWERS.get(query, {})
        if expected:
            print(f"Expected keywords: {expected['keywords']}")

        # Local embeddings
        print("\n  --- Local (all-MiniLM-L6-v2, 384-dim) ---")
        results_local = search_lancedb("strands_local", query, use_api=False)
        for idx, row in results_local.iterrows():
            # LanceDB returns _distance, lower is better
            distance = row.get('_distance', 0)
            relevance = 1 / (1 + distance)  # Convert to 0-1 scale
            preview = row['text'][:150].replace('\n', ' ')
            print(f"  [{idx+1}] (relevance: {relevance:.2f}) {preview}...")

        # API embeddings (if available)
        if has_api_table:
            print("\n  --- API (text-embedding-3-small, 1536-dim) ---")
            try:
                results_api = search_lancedb("strands_api", query, use_api=True)
                for idx, row in results_api.iterrows():
                    distance = row.get('_distance', 0)
                    relevance = 1 / (1 + distance)
                    preview = row['text'][:150].replace('\n', ' ')
                    print(f"  [{idx+1}] (relevance: {relevance:.2f}) {preview}...")
            except Exception as e:
                print(f"  Error querying API table: {e}")


# =============================================================================
# Demo 3: RAG Agent with LanceDB
# =============================================================================
# Create tool that uses LanceDB
@tool
def search_lancedb_kb(query: str, num_results: int = 3) -> str:
    """
    Search the Strands Agents knowledge base using LanceDB.
    Use this tool when asked questions about Strands Agents, tools,
    or multi-agent patterns.

    Args:
        query: The search query
        num_results: Number of results to return

    Returns:
        Relevant text passages from the knowledge base
    """
    try:
        results = search_lancedb("strands_local", query, use_api=False, limit=num_results)
        if results.empty:
            return "No relevant information found."

        passages = []
        for idx, row in results.iterrows():
            distance = row.get('_distance', 0)
            relevance = 1 / (1 + distance)
            text = row['text'][:300]
            passages.append(f"[{idx+1}] (relevance: {relevance:.2f}): {text}...")

        return "\n\n".join(passages)
    except Exception as e:
        return f"Error searching knowledge base: {e}"


def rag_agent_demo():
    """Demonstrate RAG agent using LanceDB."""
    print("\n" + "=" * 60)
    print("Demo 3: RAG Agent with LanceDB")
    print("=" * 60)

    agent = Agent(
        model=model,
        tools=[search_lancedb_kb],
        system_prompt="""You are a helpful assistant that answers questions about Strands Agents SDK.
Always use the search_lancedb_kb tool to find relevant information before answering.
Base your answers on the retrieved information.""",
        callback_handler=None
    )

    question = "What are the three multi-agent patterns in Strands?"
    print(f"\nQuestion: {question}")
    print("-" * 40)

    result = agent(question)
    print(f"\nAgent response:\n{result}")

    return result


# =============================================================================
# Demo 4: Vector Store Comparison Summary
# =============================================================================
def comparison_summary():
    """Summarize ChromaDB vs LanceDB comparison."""
    print("\n" + "=" * 60)
    print("Demo 4: Vector Store Comparison Summary")
    print("=" * 60)

    print("""
| Metric              | ChromaDB                  | LanceDB                    |
|---------------------|---------------------------|----------------------------|
| Setup               | PersistentClient(path=)   | connect(path)              |
| Query API           | collection.query()        | table.search().to_pandas() |
| Default Embedding   | all-MiniLM-L6-v2 (auto)   | BYOE (bring your own)      |
| Storage Format      | SQLite + Parquet          | Lance columnar format      |
| Hybrid Search       | No                        | Yes (vector + SQL)         |
| Metadata Filtering  | Yes                       | Yes (SQL-like)             |

Embedding Model Comparison:
| Model                    | Dimensions | Speed   | Quality | Cost      |
|--------------------------|------------|---------|---------|-----------|
| all-MiniLM-L6-v2 (local) | 384        | Fast    | Good    | Free      |
| text-embedding-3-small   | 1536       | Medium  | Better  | ~$0.02/1M |

Key Insights:
- ChromaDB: Simpler setup, auto-embeddings, good for prototyping
- LanceDB: More flexible, better for production, hybrid search
- Local embeddings: Fast, free, but lower semantic precision
- API embeddings: Higher quality, but requires network + cost
""")


# =============================================================================
# Main Demo
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Level 13: RAG Integration - Iteration 3")
    print("LanceDB + Embedding Comparison")
    print("=" * 60)

    # Suppress tokenizer warnings
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    print("\nThis iteration compares:")
    print("- Vector stores: ChromaDB vs LanceDB")
    print("- Embeddings: Local (384-dim) vs API (1536-dim)")

    # Run demos
    print("\nRunning Demo 1: Building Knowledge Base...")
    build_kb_demo()

    print("\nRunning Demo 2: Embedding Comparison...")
    embedding_comparison_demo()

    print("\nRunning Demo 3: RAG Agent with LanceDB...")
    rag_agent_demo()

    print("\nRunning Demo 4: Comparison Summary...")
    comparison_summary()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print("""
Key Patterns for LanceDB:

1. Connect:
   db = lancedb.connect("./lance_vectors")

2. Create Table:
   data = [{"text": chunk, "vector": embedding, "id": i} for ...]
   table = db.create_table("docs", data)

3. Search:
   results = table.search(query_vector).limit(3).to_pandas()

4. Key Differences from ChromaDB:
   - Must provide your own embeddings (BYOE)
   - Returns pandas DataFrame
   - Uses _distance (lower = more similar)
   - Supports SQL-like filtering

Recommendation:
- Use ChromaDB for quick prototypes (auto-embeddings)
- Use LanceDB for production (flexibility, hybrid search)
- Use local embeddings for development (fast, free)
- Use API embeddings for production (better quality)
""")

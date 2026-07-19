"""
Level 13: RAG Integration (Iteration 2)
=======================================
Retrieval-Augmented Generation with ChromaDB and Strands Agents.

Iteration 2 Improvements:
- Technical docs instead of marketing README
- Test questions with known expected answers
- Validation of RAG retrieval quality

Key Concepts:
- Vector embeddings for semantic search
- Document chunking strategies
- ChromaDB persistent storage
- RAG tool integration with agents

Run: uv run python 05_advanced/rag_integration.py
"""

import sys
sys.path.insert(0, ".")

import chromadb
import requests
from strands import Agent, tool
from tools import get_model

# Use sonnet for reliable tool-use and response generation
model = get_model("claude-sonnet-4")

# =============================================================================
# Configuration
# =============================================================================
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "strands_docs_v2"  # New collection for Iteration 2
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# Documentation sources (technical docs, not marketing README)
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

# Expected answers for validation (based on actual doc content)
EXPECTED_ANSWERS = {
    "How do I create a tool in Strands?": {
        "keywords": ["@tool", "decorator", "type hints", "docstring"],
        "description": "@tool decorator on a function with type hints and docstring"
    },
    "What are the multi-agent patterns in Strands?": {
        "keywords": ["Agents-as-Tools", "Swarm", "Graph"],
        "description": "Agents-as-Tools (hierarchical), Swarm (autonomous), Graph (deterministic)"
    },
    "When should I use Swarm vs Graph?": {
        "keywords": ["autonomous", "deterministic", "handoff", "workflow"],
        "description": "Swarm for autonomous collaboration; Graph for deterministic workflows"
    },
    "What does a tool docstring need?": {
        "keywords": ["description", "purpose", "when", "parameters"],
        "description": "Purpose, when to use it, parameters, expected output"
    }
}

# Fallback content if network unavailable
SAMPLE_STRANDS_CONTENT = """
# Strands Agents SDK

Strands Agents is a model-driven approach to building AI agents in just a few lines of code.

## Key Features

- **Simple Agent Creation**: Create agents with `Agent(model=model, tools=[...])`
- **Tool System**: Use `@tool` decorator to convert functions into agent tools
- **Multi-Agent Patterns**: Support for swarms, graphs, and agents-as-tools
- **Session Management**: FileSessionManager for conversation persistence
- **Model Flexibility**: Works with any LLM via OpenAI-compatible API

## Basic Example

```python
from strands import Agent, tool

@tool
def get_weather(city: str) -> str:
    \"\"\"Get weather for a city.\"\"\"
    return f"Weather in {city}: Sunny, 72F"

agent = Agent(model=model, tools=[get_weather])
agent("What's the weather in Seattle?")
```

## System Prompts

Shape agent behavior with system prompts:
- Same model + different prompt = different behavior
- Constraints work ("be concise" -> concise output)

## Sessions

Maintain context across interactions:
- Agent is stateless; session_manager holds state
- FileSessionManager(session_id="x", storage_dir="./sessions")

## Tool Best Practices

Tools need good docstrings because the LLM uses them to decide when to call:
- Describe WHAT the tool does
- Describe WHEN to use it
- Include example inputs if helpful

## Multi-Agent Patterns

Three main patterns:
1. Agents-as-Tools: Wrap agents with @tool for hierarchical delegation
2. Swarm: Multiple agents collaborating with handoffs
3. Graph: Explicit workflow with nodes and edges

## Error Handling

Strands provides StructuredOutputException for validation errors.
Use try/except blocks for graceful degradation.
"""


# =============================================================================
# Helper Functions
# =============================================================================
def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping chunks.

    Plain English: Break large text into smaller pieces (~500 chars each),
    with 50-char overlap between chunks to preserve context at boundaries.

    Args:
        text: The text to chunk
        chunk_size: Target size of each chunk in characters
        overlap: Number of characters to overlap between chunks

    Returns:
        List of text chunks
    """
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
    """
    Fetch Strands documentation from multiple GitHub sources.
    Falls back to sample content if network unavailable.
    """
    all_content = []
    total_chars = 0

    for source in DOCS_SOURCES:
        try:
            print(f"Fetching {source['name']}...")
            response = requests.get(source["url"], timeout=10)
            response.raise_for_status()
            content = response.text
            chars = len(content)
            total_chars += chars
            print(f"  -> {chars:,} chars")
            all_content.append(f"\n\n# SOURCE: {source['name']}\n\n{content}")
        except requests.RequestException as e:
            print(f"  -> Error fetching {source['name']}: {e}")

    if all_content:
        combined = "\n".join(all_content)
        print(f"Total: {total_chars:,} chars from {len(all_content)} sources")
        return combined
    else:
        print("All fetches failed. Using fallback sample content...")
        return SAMPLE_STRANDS_CONTENT


def get_collection():
    """Get or create ChromaDB collection with error handling."""
    try:
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        return client.get_or_create_collection(name=COLLECTION_NAME)
    except Exception as e:
        print(f"ChromaDB persistent client error: {e}")
        print("Falling back to in-memory client...")
        client = chromadb.Client()
        return client.get_or_create_collection(name=COLLECTION_NAME)


def build_knowledge_base(force_rebuild: bool = False) -> int:
    """
    Build the knowledge base from documentation.

    Returns:
        Number of chunks stored
    """
    collection = get_collection()

    # Check if already populated
    existing_count = collection.count()
    if existing_count > 0 and not force_rebuild:
        print(f"Knowledge base already contains {existing_count} chunks")
        return existing_count

    # Clear existing if rebuilding
    if force_rebuild and existing_count > 0:
        print(f"Clearing {existing_count} existing chunks...")
        # Delete all existing documents by getting their IDs first
        existing = collection.get()
        if existing["ids"]:
            collection.delete(ids=existing["ids"])

    # Fetch and chunk documents
    content = fetch_docs()
    chunks = chunk_text(content)

    if not chunks:
        print("No chunks to store")
        return 0

    # Store in ChromaDB
    ids = [f"chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"source": "strands_docs", "chunk_index": i} for i in range(len(chunks))]

    collection.add(
        documents=chunks,
        ids=ids,
        metadatas=metadatas
    )

    avg_chunk_size = sum(len(c) for c in chunks) // len(chunks)
    print(f"Stored {len(chunks)} chunks (avg {avg_chunk_size} chars each)")

    return len(chunks)


# =============================================================================
# RAG Tool
# =============================================================================
@tool
def search_knowledge_base(query: str, num_results: int = 3) -> str:
    """
    Search the Strands Agents knowledge base for relevant information.
    Use this tool when asked questions about Strands Agents, agents, tools,
    multi-agent patterns, sessions, or related SDK concepts.

    Args:
        query: The search query describing what information you need
        num_results: Number of results to return (default: 3)

    Returns:
        Relevant text passages from the knowledge base
    """
    collection = get_collection()

    # Check if collection has documents
    if collection.count() == 0:
        return "Knowledge base is empty. Please run build_knowledge_base() first."

    # Query the collection
    results = collection.query(
        query_texts=[query],
        n_results=min(num_results, collection.count())
    )

    # Format results for the agent
    if not results["documents"] or not results["documents"][0]:
        return "No relevant information found in the knowledge base."

    passages = []
    for i, doc in enumerate(results["documents"][0]):
        distance = results["distances"][0][i] if results.get("distances") else None
        relevance = f" (relevance: {1 - distance:.2f})" if distance is not None else ""
        passages.append(f"[{i+1}]{relevance}: {doc[:300]}...")

    return "\n\n".join(passages)


# =============================================================================
# Demo 1: Building a Knowledge Base
# =============================================================================
def build_kb_demo():
    """Demonstrate building a knowledge base with ChromaDB."""
    print("\n" + "=" * 60)
    print("Demo 1: Building a Knowledge Base")
    print("=" * 60)

    print("\nKey pattern: ChromaDB + automatic embeddings")
    print("ChromaDB uses all-MiniLM-L6-v2 by default (no API key needed)")

    # Build the KB
    num_chunks = build_knowledge_base(force_rebuild=True)

    # Show collection info
    collection = get_collection()
    print(f"\nCollection '{COLLECTION_NAME}' stats:")
    print(f"  - Documents: {collection.count()}")
    print(f"  - Storage: {CHROMA_DB_PATH}/")

    return num_chunks


# =============================================================================
# Demo 2: Semantic Search with Validation
# =============================================================================
def validate_result(result_text: str, expected: dict) -> bool:
    """Check if result contains expected keywords."""
    result_lower = result_text.lower()
    found = [kw for kw in expected["keywords"] if kw.lower() in result_lower]
    return len(found) >= 2  # At least 2 keywords found


def semantic_search_demo():
    """Demonstrate semantic search with expected answer validation."""
    print("\n" + "=" * 60)
    print("Demo 2: Semantic Search (with validation)")
    print("=" * 60)

    collection = get_collection()
    validation_results = []

    # Test queries with expected answers
    test_queries = [
        "How do I create a tool in Strands?",
        "What are the multi-agent patterns in Strands?",
        "What does a tool docstring need?"
    ]

    for query in test_queries:
        print(f"\nQuery: \"{query}\"")
        expected = EXPECTED_ANSWERS.get(query, {})
        if expected:
            print(f"Expected: {expected['description']}")
        print("-" * 40)

        results = collection.query(
            query_texts=[query],
            n_results=3
        )

        # Check if expected content is found
        found_expected = False
        for i, doc in enumerate(results["documents"][0]):
            distance = results["distances"][0][i]
            relevance = 1 - distance
            print(f"[{i+1}] (relevance: {relevance:.2f})")
            preview = doc[:200].replace("\n", " ")
            print(f"    {preview}...")

            if expected and validate_result(doc, expected):
                found_expected = True

        # Validation status
        if expected:
            status = "PASS" if found_expected else "FAIL"
            print(f"\nValidation: {status}")
            validation_results.append((query, found_expected))

    # Summary
    passed = sum(1 for _, v in validation_results if v)
    total = len(validation_results)
    print(f"\n{'=' * 40}")
    print(f"Validation Summary: {passed}/{total} queries found expected content")

    return validation_results


# =============================================================================
# Demo 3: RAG Agent
# =============================================================================
def rag_agent_demo():
    """Demonstrate an agent using the RAG tool."""
    print("\n" + "=" * 60)
    print("Demo 3: RAG Agent")
    print("=" * 60)

    # Create agent with RAG tool
    agent = Agent(
        model=model,
        tools=[search_knowledge_base],
        system_prompt="""You are a helpful assistant that answers questions about Strands Agents SDK.
Always use the search_knowledge_base tool to find relevant information before answering.
Base your answers on the retrieved information, citing what you found.""",
        callback_handler=None
    )

    # Ask a question
    question = "How do I create a tool in Strands Agents?"
    print(f"\nQuestion: {question}")
    print("-" * 40)

    result = agent(question)
    print(f"\nAgent response:\n{result}")

    return result


# =============================================================================
# Demo 4: RAG vs No-RAG Comparison (with validation)
# =============================================================================
def comparison_demo():
    """Compare agent responses with and without RAG, validating against expected."""
    print("\n" + "=" * 60)
    print("Demo 4: RAG vs No-RAG Comparison (with validation)")
    print("=" * 60)

    question = "What are the multi-agent patterns in Strands?"
    expected = EXPECTED_ANSWERS.get(question, {})
    expected_keywords = expected.get("keywords", ["Agents-as-Tools", "Swarm", "Graph"])

    print(f"\nQuestion: {question}")
    print(f"Expected keywords: {', '.join(expected_keywords)}")

    # Without RAG
    print("\n--- Without RAG ---")
    agent_no_rag = Agent(
        model=model,
        tools=[],
        system_prompt="You are a helpful assistant. Answer based on your training knowledge only.",
        callback_handler=None
    )

    result_no_rag = str(agent_no_rag(question))
    print(f"Response: {result_no_rag[:500]}...")

    # Validate no-RAG response
    no_rag_keywords = [kw for kw in expected_keywords if kw.lower() in result_no_rag.lower()]
    print(f"Keywords found: {no_rag_keywords if no_rag_keywords else 'None'}")

    # With RAG
    print("\n--- With RAG ---")
    agent_with_rag = Agent(
        model=model,
        tools=[search_knowledge_base],
        system_prompt="""You are a helpful assistant that answers questions about Strands Agents SDK.
Always use the search_knowledge_base tool to find relevant information before answering.
Base your answers on the retrieved information.""",
        callback_handler=None
    )

    result_with_rag = str(agent_with_rag(question))
    print(f"Response: {result_with_rag[:500]}...")

    # Validate RAG response
    rag_keywords = [kw for kw in expected_keywords if kw.lower() in result_with_rag.lower()]
    print(f"Keywords found: {rag_keywords if rag_keywords else 'None'}")

    # Comparison summary
    print("\n--- Validation Summary ---")
    no_rag_score = len(no_rag_keywords)
    rag_score = len(rag_keywords)
    print(f"Without RAG: {no_rag_score}/{len(expected_keywords)} keywords")
    print(f"With RAG:    {rag_score}/{len(expected_keywords)} keywords")

    if rag_score > no_rag_score:
        print("Result: RAG improved answer accuracy")
    elif rag_score == no_rag_score:
        print("Result: Both approaches found similar content")
    else:
        print("Result: Unexpected - no-RAG performed better (check docs)")

    return {
        "no_rag": result_no_rag,
        "with_rag": result_with_rag,
        "no_rag_score": no_rag_score,
        "rag_score": rag_score
    }


# =============================================================================
# Main Demo
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Level 13: RAG Integration - Iteration 2 (Technical Docs)")
    print("=" * 60)
    print("\nImprovements in this iteration:")
    print("- Technical docs from strands-agents/docs repo")
    print("- Test questions with known expected answers")
    print("- Validation of RAG retrieval quality")

    # Run demos
    print("\nRunning Demo 1: Building a Knowledge Base...")
    build_kb_demo()

    print("\nRunning Demo 2: Semantic Search...")
    semantic_search_demo()

    print("\nRunning Demo 3: RAG Agent...")
    rag_agent_demo()

    print("\nRunning Demo 4: RAG vs No-RAG Comparison...")
    comparison_demo()

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print("""
Key Patterns:

1. ChromaDB Setup:
   client = chromadb.PersistentClient(path="./chroma_db")
   collection = client.get_or_create_collection(name="docs")

2. Document Chunking:
   chunks = chunk_text(content, chunk_size=500, overlap=50)

3. Add Documents:
   collection.add(documents=[...], ids=[...], metadatas=[...])

4. Query:
   results = collection.query(query_texts=["..."], n_results=3)
   # Returns: documents, distances, metadatas, ids

5. RAG Tool:
   @tool
   def search_knowledge_base(query: str) -> str:
       results = collection.query(query_texts=[query])
       return formatted_results

Key Insights:

- ChromaDB uses all-MiniLM-L6-v2 embeddings by default (local, no API)
- Persistent storage survives restarts (./chroma_db/)
- Semantic search finds conceptually similar content, not just keywords
- RAG grounds agent responses in actual documentation
- Overlap in chunking preserves context at boundaries
""")

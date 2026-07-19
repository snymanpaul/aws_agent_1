#!/usr/bin/env python3
"""
Level 17: Graph Memory Deep Dive
================================
Test graph database strengths vs vectors:
- Temporal queries (time-scoped facts)
- Multi-hop reasoning (relationship traversal)
- Knowledge update semantics (fact versioning)

Uses:
- Graphiti SDK (direct FalkorDB connection)
- LanceDB (vector baseline)

Run: uv run python 06_memory/graph_memory_benchmark.py
"""

import os
import sys
import time
import asyncio
from datetime import datetime
from dataclasses import dataclass

# Apply nest_asyncio at module level for nested event loops
import nest_asyncio
nest_asyncio.apply()

# Load environment variables (LESSON_DOTENV can point at an external dotenv)
from dotenv import load_dotenv
load_dotenv(os.environ.get("LESSON_DOTENV", ".env"))

# Add project root to path
sys.path.insert(0, ".")

# Global reference for graphiti client (set during iteration 1)
_GRAPHITI_CLIENT = None

# =============================================================================
# TEST DATASET
# =============================================================================

TEST_EPISODES = [
    # Temporal series (same topic, evolving over time)
    {"name": "rec_v1", "body": "For RAG systems, ChromaDB is the recommended vector database.", "time": "2025-01-01T00:00:00"},
    {"name": "rec_v2", "body": "After benchmarking, LanceDB now outperforms ChromaDB for large datasets.", "time": "2025-06-01T00:00:00"},
    {"name": "rec_v3", "body": "For hybrid search, Graphiti combines vectors with graph relationships.", "time": "2025-12-01T00:00:00"},

    # Relationship chains (multi-hop)
    {"name": "arch_1", "body": "The memory architecture has three layers: working, episodic, and semantic."},
    {"name": "arch_2", "body": "Working memory uses FileSessionManager for per-session state."},
    {"name": "arch_3", "body": "Episodic memory stores past events with timestamps."},
    {"name": "arch_4", "body": "Semantic memory stores facts extracted from episodic events."},

    # Entity relationships
    {"name": "tech_1", "body": "ChromaDB uses HNSW indexing for approximate nearest neighbor search."},
    {"name": "tech_2", "body": "LanceDB uses Lance columnar format with IVF-PQ indexing."},
    {"name": "tech_3", "body": "FalkorDB uses GraphBLAS for sparse matrix operations."},

    # Cross-references
    {"name": "compare_1", "body": "ChromaDB vs LanceDB: ChromaDB has easier API, LanceDB is faster for large data."},
    {"name": "compare_2", "body": "Vector search vs Graph: Vectors find similar content, graphs find relationships."},
]

GROUP_ID = "l17_benchmark"
LANCEDB_PATH = "06_memory/l17_lancedb"


# =============================================================================
# GRAPHITI SDK SETUP
# =============================================================================

async def create_graphiti_client():
    """
    Create Graphiti client with direct FalkorDB connection.

    Critical gotchas (from prior Graphiti benchmarking):
    1. LiteLLM incompatible - use direct GeminiClient
    2. Entity types must be list, not dict
    3. Pass entity_types to add_episode(), not __init__()
    4. Embedding dimension locked at 1536
    """
    from graphiti_core import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.llm_client.gemini_client import GeminiClient
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from openai import AsyncOpenAI

    # 1. FalkorDB driver (shared instance at localhost:6379)
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        database='l17_benchmark',  # Isolated graph
        username=None,
        password=None
    )

    # 2. LLM client - Direct Gemini (NOT LiteLLM - incompatible with structured outputs)
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY environment variable required")

    llm_client = GeminiClient(
        config=LLMConfig(
            api_key=gemini_api_key,
            model="gemini-2.0-flash",
            temperature=0.7,
            max_tokens=8192
        )
    )

    # 3. Embedder - Azure OpenAI (1536-dim, locked)
    azure_key = os.getenv('AZURE_OPENAI_EMBEDDINGS_KEY')
    azure_endpoint = os.getenv('AZURE_OPENAI_EMBEDDINGS_ENDPOINT')

    if not azure_key or not azure_endpoint:
        raise ValueError("AZURE_OPENAI_EMBEDDINGS_KEY and AZURE_OPENAI_EMBEDDINGS_ENDPOINT required")

    embeddings_client = AsyncOpenAI(
        api_key=azure_key,
        base_url=f"{azure_endpoint}/openai/v1/",
        default_headers={"api-key": azure_key},
        timeout=30.0,
        max_retries=0
    )

    embedder = OpenAIEmbedder(
        client=embeddings_client,
        config=OpenAIEmbedderConfig(
            api_key=azure_key,
            embedding_model="text-embedding-3-small",
            embedding_dim=1536
        )
    )

    # 4. Initialize Graphiti
    graphiti = Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=embedder
    )

    return graphiti


# =============================================================================
# LANCEDB SETUP
# =============================================================================

def create_lancedb_store(storage_path: str):
    """Create LanceDB store for baseline comparison."""
    import lancedb
    import pyarrow as pa
    from openai import OpenAI

    # Create database
    db = lancedb.connect(storage_path)

    # Define schema
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("name", pa.string()),
        pa.field("body", pa.string()),
        pa.field("timestamp", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), 1536)),
    ])

    # Create or overwrite table
    if "episodes" in db.table_names():
        db.drop_table("episodes")
    table = db.create_table("episodes", schema=schema)

    return db, table


def get_embedding(text: str) -> list[float]:
    """Get embedding via LiteLLM proxy."""
    from openai import OpenAI

    client = OpenAI(
        api_key="sk-local",
        base_url="http://localhost:4000"
    )

    response = client.embeddings.create(
        model="azure/text-embedding-3-small",
        input=[text]
    )
    return response.data[0].embedding


# =============================================================================
# ASYNC PROCESSING WAIT
# =============================================================================

async def wait_for_processing(graphiti, group_id: str, expected_entities: int = 5, timeout_sec: int = 1200):
    """
    Wait for Graphiti entity extraction with progress indicator.

    Args:
        graphiti: Graphiti client
        group_id: Group ID to check
        expected_entities: Minimum entities needed
        timeout_sec: Max wait time (default 20 min)

    Returns:
        True if entities found, False on timeout
    """
    start = time.time()
    poll_interval = 30  # seconds

    print(f"\nWaiting for entity extraction (timeout: {timeout_sec//60} min)...")

    while time.time() - start < timeout_sec:
        elapsed = int(time.time() - start)

        try:
            # Check for extracted entities via search
            results = await graphiti.search(
                query="technology database memory",
                group_ids=[group_id],
                num_results=100
            )
            entity_count = len(results)

            print(f"  [{elapsed//60:02d}:{elapsed%60:02d}] Found {entity_count} results (need {expected_entities})")

            if entity_count >= expected_entities:
                print(f"  ✓ Entity extraction complete in {elapsed//60}:{elapsed%60:02d}")
                return True

        except Exception as e:
            print(f"  [{elapsed//60:02d}:{elapsed%60:02d}] Query error: {e}")

        await asyncio.sleep(poll_interval)

    print(f"  ⚠ Timeout after {timeout_sec//60} min. Proceeding anyway.")
    return False


# =============================================================================
# ITERATION 1: DATA LOADING
# =============================================================================

async def iteration_1_setup_and_load():
    """
    Iteration 1: Graphiti SDK Setup + Data Loading

    Phase 1A: SDK connection
    Phase 1B: Load data to both systems
    Phase 1C: Wait for entity extraction
    """
    print("=" * 60)
    print("ITERATION 1: Graphiti SDK Setup + Data Loading")
    print("=" * 60)

    # Phase 1A: Setup
    print("\n[Phase 1A] Creating Graphiti client...")
    try:
        graphiti = await create_graphiti_client()
        print("  ✓ Graphiti client created")
        print(f"  ✓ FalkorDB: localhost:6379")
        print(f"  ✓ Graph: l17_benchmark")
    except Exception as e:
        print(f"  ✗ Failed to create Graphiti client: {e}")
        return None

    # Phase 1B: Store data
    print(f"\n[Phase 1B] Loading {len(TEST_EPISODES)} episodes...")

    # Store to Graphiti
    print("\n  Storing to Graphiti...")
    from graphiti_core.nodes import EpisodeType

    graphiti_start = time.perf_counter()
    for i, ep in enumerate(TEST_EPISODES):
        ref_time = datetime.fromisoformat(ep.get("time", datetime.now().isoformat()))

        await graphiti.add_episode(
            name=ep["name"],
            episode_body=ep["body"],
            source=EpisodeType.text,
            source_description="L17 benchmark data",
            reference_time=ref_time,
            group_id=GROUP_ID
        )
        print(f"    [{i+1}/{len(TEST_EPISODES)}] {ep['name']}")

    graphiti_elapsed = (time.perf_counter() - graphiti_start) * 1000
    print(f"  ✓ Graphiti: {len(TEST_EPISODES)} episodes in {graphiti_elapsed:.0f}ms")

    # Store to LanceDB
    print("\n  Storing to LanceDB...")
    import shutil
    if os.path.exists(LANCEDB_PATH):
        shutil.rmtree(LANCEDB_PATH)

    db, table = create_lancedb_store(LANCEDB_PATH)

    lancedb_start = time.perf_counter()
    records = []
    for i, ep in enumerate(TEST_EPISODES):
        vector = get_embedding(ep["body"])
        records.append({
            "id": f"ep_{i}",
            "name": ep["name"],
            "body": ep["body"],
            "timestamp": ep.get("time", ""),
            "vector": vector
        })
        print(f"    [{i+1}/{len(TEST_EPISODES)}] {ep['name']}")

    table.add(records)
    lancedb_elapsed = (time.perf_counter() - lancedb_start) * 1000
    print(f"  ✓ LanceDB: {len(TEST_EPISODES)} episodes in {lancedb_elapsed:.0f}ms")

    # Phase 1C: Wait for Graphiti processing
    print("\n[Phase 1C] Waiting for Graphiti entity extraction...")
    await wait_for_processing(graphiti, GROUP_ID, expected_entities=5)

    print("\n" + "=" * 60)
    print("ITERATION 1 COMPLETE")
    print("=" * 60)

    return graphiti


# =============================================================================
# ITERATION 2: TEMPORAL QUERY BENCHMARK
# =============================================================================

async def iteration_2_temporal_benchmark(graphiti):
    """
    Iteration 2: Temporal Query Benchmark

    Test time-aware facts that vectors cannot match.
    """
    print("\n" + "=" * 60)
    print("ITERATION 2: Temporal Query Benchmark")
    print("=" * 60)

    import lancedb

    # Connect to LanceDB
    db = lancedb.connect(LANCEDB_PATH)
    table = db.open_table("episodes")

    queries = [
        ("What is recommended for RAG?", "Current recommendation"),
        ("What was recommended before June 2025?", "Time-scoped filter"),
        ("database recommendation history", "Recommendation history"),
    ]

    for query, description in queries:
        print(f"\n[Query] {description}")
        print(f"  '{query}'")

        # LanceDB query (no temporal awareness)
        print("\n  LanceDB results:")
        query_vector = get_embedding(query)
        lance_results = table.search(query_vector).limit(3).to_pandas()
        for _, row in lance_results.iterrows():
            print(f"    - {row['name']}: {row['body'][:60]}...")
            if row['timestamp']:
                print(f"      (timestamp: {row['timestamp']}, but NOT used in search)")

        # Graphiti query (temporal awareness)
        print("\n  Graphiti results:")
        try:
            graphiti_results = await graphiti.search(
                query=query,
                group_ids=[GROUP_ID],
                num_results=3
            )
            for r in graphiti_results:
                fact = getattr(r, 'fact', str(r))
                valid_at = getattr(r, 'valid_at', None)
                invalid_at = getattr(r, 'invalid_at', None)
                print(f"    - {fact[:60]}...")
                if valid_at or invalid_at:
                    print(f"      (valid_at: {valid_at}, invalid_at: {invalid_at})")
        except Exception as e:
            print(f"    Error: {e}")

    print("\n" + "=" * 60)
    print("ITERATION 2 COMPLETE")
    print("=" * 60)


# =============================================================================
# ITERATION 3: MULTI-HOP REASONING BENCHMARK
# =============================================================================

async def iteration_3_multihop_benchmark(graphiti):
    """
    Iteration 3: Multi-Hop Reasoning Benchmark

    Test relationship traversal that vectors miss.
    """
    print("\n" + "=" * 60)
    print("ITERATION 3: Multi-Hop Reasoning Benchmark")
    print("=" * 60)

    import lancedb

    db = lancedb.connect(LANCEDB_PATH)
    table = db.open_table("episodes")

    queries = [
        ("What are the layers of memory architecture and what does each use?", "2-hop traversal"),
        ("What is ChromaDB compared to?", "Entity relationships"),
        ("What indexing methods do vector databases use?", "Category aggregation"),
    ]

    for query, description in queries:
        print(f"\n[Query] {description}")
        print(f"  '{query}'")

        # LanceDB (single-hop only)
        print("\n  LanceDB results (single-hop keyword match):")
        query_vector = get_embedding(query)
        lance_results = table.search(query_vector).limit(5).to_pandas()
        for _, row in lance_results.iterrows():
            print(f"    - {row['name']}: {row['body'][:60]}...")

        # Graphiti (relationship traversal)
        print("\n  Graphiti results (relationship-aware):")
        try:
            graphiti_results = await graphiti.search(
                query=query,
                group_ids=[GROUP_ID],
                num_results=5
            )
            for r in graphiti_results:
                fact = getattr(r, 'fact', str(r))
                source = getattr(r, 'source_node', None)
                target = getattr(r, 'target_node', None)
                print(f"    - {fact[:60]}...")
                if source and target:
                    print(f"      (relationship: {source.name} → {target.name})")
        except Exception as e:
            print(f"    Error: {e}")

    print("\n" + "=" * 60)
    print("ITERATION 3 COMPLETE")
    print("=" * 60)


# =============================================================================
# ITERATION 4: KNOWLEDGE UPDATE SEMANTICS
# =============================================================================

async def iteration_4_update_benchmark(graphiti):
    """
    Iteration 4: Knowledge Update Semantics

    Test fact versioning vs overwrite behavior.
    """
    print("\n" + "=" * 60)
    print("ITERATION 4: Knowledge Update Semantics")
    print("=" * 60)

    import lancedb

    db = lancedb.connect(LANCEDB_PATH)
    table = db.open_table("episodes")

    # Query before update
    query = "What is recommended for RAG?"
    print(f"\n[Before Update] '{query}'")

    query_vector = get_embedding(query)

    print("\n  LanceDB:")
    lance_before = table.search(query_vector).limit(3).to_pandas()
    for _, row in lance_before.iterrows():
        print(f"    - {row['body'][:60]}...")

    print("\n  Graphiti:")
    try:
        graphiti_before = await graphiti.search(query=query, group_ids=[GROUP_ID], num_results=3)
        for r in graphiti_before:
            print(f"    - {getattr(r, 'fact', str(r))[:60]}...")
    except Exception as e:
        print(f"    Error: {e}")

    # Add contradicting fact
    print("\n[Adding Update] 'ChromaDB is deprecated for new projects'")

    from graphiti_core.nodes import EpisodeType

    # Add to Graphiti
    await graphiti.add_episode(
        name="deprecation_notice",
        episode_body="ChromaDB is now deprecated for new projects. Use LanceDB or Graphiti instead.",
        source=EpisodeType.text,
        source_description="L17 update test",
        reference_time=datetime.now(),
        group_id=GROUP_ID
    )

    # Add to LanceDB
    new_vector = get_embedding("ChromaDB is now deprecated for new projects. Use LanceDB or Graphiti instead.")
    table.add([{
        "id": "ep_update",
        "name": "deprecation_notice",
        "body": "ChromaDB is now deprecated for new projects. Use LanceDB or Graphiti instead.",
        "timestamp": datetime.now().isoformat(),
        "vector": new_vector
    }])

    # Wait briefly for Graphiti to process
    print("\n  Waiting 30s for Graphiti to process update...")
    await asyncio.sleep(30)

    # Query after update
    print(f"\n[After Update] '{query}'")

    print("\n  LanceDB (returns both old and new - no invalidation):")
    lance_after = table.search(query_vector).limit(5).to_pandas()
    for _, row in lance_after.iterrows():
        print(f"    - {row['body'][:60]}...")

    print("\n  Graphiti (should show versioning):")
    try:
        graphiti_after = await graphiti.search(query=query, group_ids=[GROUP_ID], num_results=5)
        for r in graphiti_after:
            fact = getattr(r, 'fact', str(r))
            invalid_at = getattr(r, 'invalid_at', None)
            status = " [INVALID]" if invalid_at else ""
            print(f"    - {fact[:60]}...{status}")
    except Exception as e:
        print(f"    Error: {e}")

    print("\n" + "=" * 60)
    print("ITERATION 4 COMPLETE")
    print("=" * 60)


# =============================================================================
# ITERATION 5: GRAPH-AUGMENTED AGENT
# =============================================================================

async def iteration_5_agent_demo(graphiti):
    """
    Iteration 5: Graph-Augmented Agent

    Practical Strands agent with graph tools.
    """
    print("\n" + "=" * 60)
    print("ITERATION 5: Graph-Augmented Agent")
    print("=" * 60)

    # Set global reference for tools to access
    global _GRAPHITI_CLIENT
    _GRAPHITI_CLIENT = graphiti

    from strands import Agent, tool
    from tools import get_model

    # Create tools that use the global Graphiti client
    @tool
    def graph_search(query: str) -> str:
        """Search the knowledge graph for facts and relationships. Returns facts with their validity status."""
        global _GRAPHITI_CLIENT
        if _GRAPHITI_CLIENT is None:
            return "Error: Graphiti client not initialized"

        async def _search():
            results = await _GRAPHITI_CLIENT.search(
                query=query,
                group_ids=[GROUP_ID],
                num_results=5
            )
            output = []
            for r in results:
                fact = getattr(r, 'fact', str(r))
                invalid = " [INVALID]" if getattr(r, 'invalid_at', None) else ""
                output.append(f"- {fact}{invalid}")
            return "\n".join(output) if output else "No results found"

        return asyncio.get_event_loop().run_until_complete(_search())

    @tool
    def graph_temporal_search(query: str, before_date: str = "", after_date: str = "") -> str:
        """Search facts with temporal metadata. Returns facts with valid_at and invalid_at timestamps."""
        global _GRAPHITI_CLIENT
        if _GRAPHITI_CLIENT is None:
            return "Error: Graphiti client not initialized"

        async def _search():
            results = await _GRAPHITI_CLIENT.search(
                query=query,
                group_ids=[GROUP_ID],
                num_results=5
            )
            output = []
            for r in results:
                fact = getattr(r, 'fact', str(r))
                valid_at = getattr(r, 'valid_at', None)
                invalid_at = getattr(r, 'invalid_at', None)
                status = f" (valid: {valid_at}, invalid: {invalid_at})"
                output.append(f"- {fact}{status}")
            return "\n".join(output) if output else "No results found"

        return asyncio.get_event_loop().run_until_complete(_search())

    # Test tools directly first
    print("\n[Testing tools directly]")
    test_result = graph_search("RAG recommendation")
    print(f"  graph_search test: {test_result[:200]}...")

    # Create agent
    model = get_model("claude-sonnet-4")
    agent = Agent(
        model=model,
        tools=[graph_search, graph_temporal_search],
        system_prompt="""You are a helpful assistant with access to a temporal knowledge graph.

You have two tools:
- graph_search: Find facts and relationships in the knowledge graph
- graph_temporal_search: Find facts valid at specific times

IMPORTANT: Always use the graph tools to answer questions. Do not rely on your general knowledge. The graph contains the authoritative information.

When asked about recommendations or comparisons, use graph_search first."""
    )

    # Demo conversation
    demo_queries = [
        "What's currently recommended for RAG systems?",
        "What was recommended 6 months ago?",
        "How does ChromaDB relate to other technologies?",
    ]

    for query in demo_queries:
        print(f"\n[User] {query}")
        print("\n[Agent]")
        # Use the agent and capture response (let default streaming work)
        import io
        import contextlib

        # Capture output to avoid streaming noise
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            response = agent(query)

        # Print clean response
        response_text = str(response)
        print(f"  {response_text[:500]}...")

    print("\n" + "=" * 60)
    print("ITERATION 5 COMPLETE")
    print("=" * 60)


# =============================================================================
# ITERATION 6: TRUE MULTI-HOP TRAVERSAL
# =============================================================================

async def iteration_6_multihop_traversal(graphiti):
    """
    Iteration 6: True Multi-Hop Edge Traversal

    Use Graphiti's get_nodes and edge retrieval to follow actual
    graph relationships, not just semantic search.
    """
    print("\n" + "=" * 60)
    print("ITERATION 6: True Multi-Hop Edge Traversal")
    print("=" * 60)

    # First, let's see what nodes exist in the graph
    print("\n[Step 1] Discovering entities in the graph...")

    # Search for technology-related nodes
    tech_results = await graphiti.search(
        query="ChromaDB LanceDB FalkorDB",
        group_ids=[GROUP_ID],
        num_results=20
    )

    print(f"  Found {len(tech_results)} results from semantic search")

    # Extract unique entities mentioned
    entities_found = set()
    for r in tech_results:
        fact = getattr(r, 'fact', str(r))
        # Look for technology names in facts
        for tech in ['ChromaDB', 'LanceDB', 'FalkorDB', 'Graphiti', 'HNSW', 'IVF-PQ', 'GraphBLAS']:
            if tech.lower() in fact.lower():
                entities_found.add(tech)

    print(f"  Entities mentioned: {', '.join(sorted(entities_found))}")

    # Now use Graphiti's node retrieval to get actual graph nodes
    print("\n[Step 2] Retrieving actual graph nodes...")

    try:
        # Use _search method to get nodes directly
        from graphiti_core.search.search_utils import get_relevant_nodes

        # Get nodes related to ChromaDB
        nodes = await graphiti._search(
            query="ChromaDB",
            group_ids=[GROUP_ID],
            num_results=10
        )

        print(f"  Retrieved {len(nodes)} nodes")
        for node in nodes[:5]:
            node_name = getattr(node, 'name', 'unknown')
            node_type = type(node).__name__
            print(f"    - [{node_type}] {node_name}")

    except Exception as e:
        print(f"  Note: Direct node retrieval: {e}")

    # Get edges/facts and show their structure
    print("\n[Step 3] Examining fact/edge structure...")

    for i, r in enumerate(tech_results[:5]):
        print(f"\n  Fact {i+1}:")
        print(f"    fact: {getattr(r, 'fact', 'N/A')[:80]}...")
        print(f"    source_node: {getattr(r, 'source_node', None)}")
        print(f"    target_node: {getattr(r, 'target_node', None)}")
        print(f"    valid_at: {getattr(r, 'valid_at', None)}")
        print(f"    uuid: {getattr(r, 'uuid', 'N/A')[:8]}...")

    # Demonstrate traversal pattern: Start from one entity, find connections
    print("\n[Step 4] Traversal pattern: ChromaDB → connections → their connections")

    # Level 1: What connects to ChromaDB?
    level1 = await graphiti.search(
        query="ChromaDB",
        group_ids=[GROUP_ID],
        num_results=10
    )
    print(f"\n  Level 1 (ChromaDB direct): {len(level1)} facts")

    connected_entities = set()
    for r in level1:
        fact = str(getattr(r, 'fact', ''))
        for tech in ['LanceDB', 'Graphiti', 'HNSW', 'RAG', 'vector']:
            if tech.lower() in fact.lower():
                connected_entities.add(tech)

    print(f"    Connected to: {', '.join(connected_entities)}")

    # Level 2: What connects to those entities?
    if connected_entities:
        next_entity = list(connected_entities)[0]
        level2 = await graphiti.search(
            query=next_entity,
            group_ids=[GROUP_ID],
            num_results=10
        )
        print(f"\n  Level 2 ({next_entity}): {len(level2)} facts")
        for r in level2[:3]:
            print(f"    - {getattr(r, 'fact', str(r))[:70]}...")

    print("\n" + "=" * 60)
    print("ITERATION 6 COMPLETE")
    print("=" * 60)


# =============================================================================
# ITERATION 7: TIME-SCOPED QUERIES
# =============================================================================

async def iteration_7_temporal_queries(graphiti):
    """
    Iteration 7: Time-Scoped Queries with before_date

    Query facts that were valid at specific points in time.
    """
    print("\n" + "=" * 60)
    print("ITERATION 7: Time-Scoped Queries")
    print("=" * 60)

    from datetime import datetime, timezone

    # Define time points to query
    time_points = [
        ("2025-01-15", "Mid-January 2025 (after rec_v1)"),
        ("2025-06-15", "Mid-June 2025 (after rec_v2)"),
        ("2025-12-15", "Mid-December 2025 (after rec_v3 and updates)"),
    ]

    print("\n[Test] Querying 'RAG recommendation' at different time points")
    print("=" * 50)

    for date_str, description in time_points:
        print(f"\n[{date_str}] {description}")

        # Query for RAG recommendations
        results = await graphiti.search(
            query="RAG recommendation database",
            group_ids=[GROUP_ID],
            num_results=10
        )

        # Parse the reference date
        ref_date = datetime.fromisoformat(f"{date_str}T00:00:00+00:00")

        # Filter results by validity at that time
        valid_at_time = []
        for r in results:
            valid_at = getattr(r, 'valid_at', None)
            invalid_at = getattr(r, 'invalid_at', None)

            # Check if fact was valid at reference date
            is_valid = True
            if valid_at and valid_at > ref_date:
                is_valid = False  # Not yet valid
            if invalid_at and invalid_at <= ref_date:
                is_valid = False  # Already invalidated

            if is_valid:
                valid_at_time.append((r, valid_at, invalid_at))

        print(f"  Facts valid at {date_str}: {len(valid_at_time)}")
        for r, va, ia in valid_at_time[:3]:
            fact = getattr(r, 'fact', str(r))[:60]
            status = ""
            if ia:
                status = f" [invalidated {ia.date()}]"
            print(f"    - {fact}...{status}")

    # Demonstrate what LanceDB would return (no filtering)
    print("\n" + "=" * 50)
    print("[Comparison] LanceDB has no temporal filtering capability")
    print("  → Returns ALL matching documents regardless of when they were valid")
    print("  → Application must handle versioning logic manually")

    # Show the temporal metadata that Graphiti provides
    print("\n" + "=" * 50)
    print("[Graphiti Temporal Metadata Example]")

    results = await graphiti.search(
        query="ChromaDB recommendation",
        group_ids=[GROUP_ID],
        num_results=5
    )

    for r in results:
        fact = getattr(r, 'fact', str(r))[:50]
        valid_at = getattr(r, 'valid_at', None)
        invalid_at = getattr(r, 'invalid_at', None)
        created_at = getattr(r, 'created_at', None)

        print(f"\n  Fact: {fact}...")
        print(f"    valid_at:   {valid_at}")
        print(f"    invalid_at: {invalid_at}")
        print(f"    created_at: {created_at}")

    print("\n" + "=" * 60)
    print("ITERATION 7 COMPLETE")
    print("=" * 60)


# =============================================================================
# ITERATION 8: DIRECT CYPHER QUERIES
# =============================================================================

async def iteration_8_cypher_queries(graphiti):
    """
    Iteration 8: Direct Cypher Queries to FalkorDB

    Bypass Graphiti SDK and query the graph directly with Cypher.
    """
    print("\n" + "=" * 60)
    print("ITERATION 8: Direct Cypher Queries to FalkorDB")
    print("=" * 60)

    from falkordb import FalkorDB

    # Connect directly to FalkorDB
    print("\n[Step 1] Connecting to FalkorDB directly...")
    db = FalkorDB(host='localhost', port=6379)
    graph = db.select_graph('l17_benchmark')  # Same graph name as Graphiti uses

    print("  ✓ Connected to FalkorDB")
    print("  ✓ Selected graph: l17_benchmark")

    # Query 1: Count all nodes
    print("\n[Query 1] Count all nodes")
    result = graph.query("MATCH (n) RETURN count(n) as node_count")
    for row in result.result_set:
        print(f"  Total nodes: {row[0]}")

    # Query 2: Count all relationships
    print("\n[Query 2] Count all relationships/edges")
    result = graph.query("MATCH ()-[r]->() RETURN count(r) as edge_count")
    for row in result.result_set:
        print(f"  Total edges: {row[0]}")

    # Query 3: List node labels (types)
    print("\n[Query 3] Node labels (entity types)")
    result = graph.query("MATCH (n) RETURN DISTINCT labels(n) as labels, count(*) as count")
    for row in result.result_set:
        print(f"  {row[0]}: {row[1]} nodes")

    # Query 4: List relationship types
    print("\n[Query 4] Relationship types")
    result = graph.query("MATCH ()-[r]->() RETURN DISTINCT type(r) as rel_type, count(*) as count")
    for row in result.result_set:
        print(f"  {row[0]}: {row[1]} edges")

    # Query 5: Find specific entity and its connections
    print("\n[Query 5] Find 'ChromaDB' entity and connections")
    result = graph.query("""
        MATCH (n)
        WHERE n.name CONTAINS 'ChromaDB' OR n.name CONTAINS 'chromadb'
        RETURN n.name, labels(n)
        LIMIT 5
    """)
    if result.result_set:
        for row in result.result_set:
            print(f"  Found: {row[0]} [{row[1]}]")
    else:
        print("  No direct 'ChromaDB' node found")
        # Try broader search
        result = graph.query("""
            MATCH (n)
            WHERE toLower(n.name) CONTAINS 'chroma'
            RETURN n.name, labels(n)
            LIMIT 5
        """)
        for row in result.result_set:
            print(f"  Found (partial): {row[0]} [{row[1]}]")

    # Query 6: Sample some actual nodes
    print("\n[Query 6] Sample 10 nodes with properties")
    result = graph.query("""
        MATCH (n)
        RETURN n.name, n.uuid, labels(n)
        LIMIT 10
    """)
    for row in result.result_set:
        name = row[0][:40] if row[0] else 'N/A'
        uuid = row[1][:8] if row[1] else 'N/A'
        labels = row[2]
        print(f"  [{labels}] {name}... (uuid: {uuid}...)")

    # Query 7: Find edges with facts
    print("\n[Query 7] Sample edges (relationships/facts)")
    result = graph.query("""
        MATCH (a)-[r]->(b)
        RETURN a.name, type(r), b.name, r.fact
        LIMIT 5
    """)
    for row in result.result_set:
        src = (row[0] or 'N/A')[:20]
        rel = row[1]
        tgt = (row[2] or 'N/A')[:20]
        fact = (row[3] or 'N/A')[:40]
        print(f"  {src}... --[{rel}]--> {tgt}...")
        if fact != 'N/A':
            print(f"    fact: {fact}...")

    # Query 8: Multi-hop traversal with Cypher
    print("\n[Query 8] 2-hop traversal from any 'memory' node")
    result = graph.query("""
        MATCH path = (a)-[r1]->(b)-[r2]->(c)
        WHERE toLower(a.name) CONTAINS 'memory'
        RETURN a.name, type(r1), b.name, type(r2), c.name
        LIMIT 5
    """)
    if result.result_set:
        for row in result.result_set:
            print(f"  {row[0][:15]}... --[{row[1]}]--> {row[2][:15]}... --[{row[3]}]--> {row[4][:15]}...")
    else:
        print("  No 2-hop paths found from 'memory' nodes")

    print("\n" + "=" * 60)
    print("ITERATION 8 COMPLETE")
    print("=" * 60)


# =============================================================================
# MAIN
# =============================================================================

async def main():
    print("=" * 60)
    print("Level 17: Graph Memory Deep Dive")
    print("=" * 60)
    print(f"Date: {datetime.now().isoformat()}")
    print(f"Group ID: {GROUP_ID}")
    print(f"Test episodes: {len(TEST_EPISODES)}")

    # Run iterations
    graphiti = await iteration_1_setup_and_load()

    if graphiti:
        await iteration_2_temporal_benchmark(graphiti)
        await iteration_3_multihop_benchmark(graphiti)
        await iteration_4_update_benchmark(graphiti)
        # Run 6-8 before agent demo (5) to avoid event loop conflicts
        await iteration_6_multihop_traversal(graphiti)
        await iteration_7_temporal_queries(graphiti)
        await iteration_8_cypher_queries(graphiti)
        # Agent demo last (creates new event loops via nest_asyncio)
        await iteration_5_agent_demo(graphiti)

    print("\n" + "=" * 60)
    print("ALL 8 ITERATIONS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

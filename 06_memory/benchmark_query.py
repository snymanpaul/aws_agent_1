"""
Memory Systems Benchmark - Phase 2: Query
==========================================
Run queries against all 6 memory backends and compare recall.
Loads state from benchmark_state.json (created by benchmark_store.py).

Systems:
1. JSON - Keyword search (baseline)
2. ChromaDB - Vector similarity (384-dim embeddings)
3. Graphiti - Knowledge graph (ASYNC)
4. OpenMemory - 5-sector cognitive model
5. LanceDB_Local - Vector similarity (384-dim local embeddings)
6. LanceDB_API - Vector similarity (1536-dim API embeddings)

Run: uv run python 06_memory/benchmark_query.py

Prerequisites:
- benchmark_store.py was run first
- Wait ~25-30 minutes for Graphiti processing
"""

import sys
import json
import os
import time
import statistics
from datetime import datetime
from dataclasses import dataclass, field

import requests

sys.path.insert(0, ".")

# Reuse existing L14 implementations
from longterm_memory import (
    EpisodicMemoryJSON,
    SemanticMemoryJSON,
    CHROMADB_AVAILABLE,
)

if CHROMADB_AVAILABLE:
    from longterm_memory import EpisodicMemoryChroma, SemanticMemoryChroma

# MCP client for Graphiti
try:
    from strands.tools.mcp import MCPClient
    from mcp.client.streamable_http import streamablehttp_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


# =============================================================================
# CONFIGURATION
# =============================================================================

BENCHMARK_DIR = "06_memory"
STATE_FILE = os.path.join(BENCHMARK_DIR, "benchmark_state.json")


# =============================================================================
# TEST QUERIES
# =============================================================================

TEST_QUERIES = [
    {
        "query": "streaming",
        "type": "exact_match",
        "expected_keywords": ["stream", "callback", "PrintingCallbackHandler", "output"]
    },
    {
        "query": "ChromaDB",
        "type": "exact_match",
        "expected_keywords": ["chroma", "vector", "embedding", "semantic"]
    },
    {
        "query": "mistake error bug",
        "type": "category_filter",
        "expected_keywords": ["mistake", "error", "failed", "bug", "TypeError"]
    },
    {
        "query": "level 16 unified memory",
        "type": "temporal",
        "expected_keywords": ["unified", "facade", "layer", "routing", "backend"]
    },
    {
        "query": "level 1 basics hello",
        "type": "temporal",
        "expected_keywords": ["OpenAIModel", "LiteLLM", "proxy", "provider"]
    },
    {
        "query": "context management memory optimization",
        "type": "cross_reference",
        "expected_keywords": ["40%", "utilization", "token", "compress", "budget"]
    },
    {
        "query": "multi-agent patterns coordination",
        "type": "cross_reference",
        "expected_keywords": ["swarm", "graph", "orchestrator", "handoff", "delegation"]
    },
    {
        "query": "tools needed for RAG retrieval",
        "type": "multi_hop",
        "expected_keywords": ["ChromaDB", "embedding", "chunk", "search", "document"]
    },
    {
        "query": "production deployment requirements",
        "type": "multi_hop",
        "expected_keywords": ["AgentCore", "MCP", "health", "endpoint", "8080"]
    },
    {
        "query": "how to make agents remember things",
        "type": "semantic",
        "expected_keywords": ["session", "episodic", "semantic", "persist", "store"]
    }
]


# =============================================================================
# QUERY FUNCTIONS
# =============================================================================

def query_json(query: str, max_results: int = 5, storage_dir: str = "./benchmark_json") -> tuple[list[dict], float]:
    """Query JSON backend, return (results, latency_ms)."""
    episodic = EpisodicMemoryJSON(storage_dir=storage_dir, group_id="benchmark")
    semantic = SemanticMemoryJSON(storage_dir=storage_dir, group_id="benchmark")

    start = time.perf_counter()
    results = []

    ep_results = episodic.search(query, max_results)
    sem_results = semantic.search(query)[:max_results]

    for r in ep_results:
        results.append({"source": "episodic", "content": r.get("event", "")})
    for r in sem_results:
        results.append({"source": "semantic", "content": r.get("value", str(r))})

    elapsed_ms = (time.perf_counter() - start) * 1000
    return results, elapsed_ms


def query_chromadb(query: str, max_results: int = 5, storage_dir: str = "./benchmark_chroma") -> tuple[list[dict], float]:
    """Query ChromaDB backend, return (results, latency_ms)."""
    if not CHROMADB_AVAILABLE:
        return [], 0

    episodic = EpisodicMemoryChroma(storage_dir=storage_dir, collection_name="benchmark_episodes", in_memory=False)
    semantic = SemanticMemoryChroma(storage_dir=storage_dir, collection_name="benchmark_facts", in_memory=False)

    start = time.perf_counter()
    results = []

    ep_results = episodic.search(query, max_results)
    sem_results = semantic.search(query, max_results)

    for r in ep_results:
        results.append({"source": "episodic", "content": r.get("event", ""), "relevance": r.get("relevance", 0)})
    for r in sem_results:
        results.append({"source": "semantic", "content": r.get("value", ""), "relevance": r.get("relevance", 0)})

    elapsed_ms = (time.perf_counter() - start) * 1000
    return results, elapsed_ms


def query_graphiti(query: str, group_id: str, max_results: int = 5) -> tuple[list[dict], float]:
    """Query Graphiti MCP using search_nodes (entities), return (results, latency_ms)."""
    if not MCP_AVAILABLE:
        return [], 0

    try:
        client = MCPClient(lambda: streamablehttp_client("http://localhost:8000/mcp"))
        client.__enter__()

        import uuid
        start = time.perf_counter()

        # Use search_nodes to find entities (not search_memory_facts which finds relationships)
        tool_use_id = f"search-{uuid.uuid4().hex[:8]}"
        raw_result = client.call_tool_sync(
            tool_use_id,
            "search_nodes",
            {"query": query, "group_ids": [group_id], "max_nodes": max_results}
        )

        elapsed_ms = (time.perf_counter() - start) * 1000
        client.__exit__(None, None, None)

        # Parse structured result - nodes have name and summary
        results = []
        structured = raw_result.get("structuredContent", {}).get("result", {})
        nodes = structured.get("nodes", [])

        for node in nodes[:max_results]:
            if isinstance(node, dict):
                # Nodes have 'name' and 'summary' fields
                content = node.get("summary", node.get("name", str(node)))
                results.append({
                    "source": "graphiti",
                    "content": str(content)[:300],
                    "name": node.get("name", ""),
                    "uuid": node.get("uuid", "")
                })

        return results, elapsed_ms

    except Exception as e:
        return [{"error": str(e)}], 0


def query_openmemory(query: str, max_results: int = 5) -> tuple[list[dict], float]:
    """Query OpenMemory, return (results, latency_ms)."""
    session = requests.Session()
    session.headers.update({
        "Authorization": "Bearer benchmark-test-key-2025",
        "Content-Type": "application/json"
    })

    start = time.perf_counter()
    results = []

    try:
        payload = {"query": query, "limit": max_results}
        response = session.post("http://localhost:8080/memory/query", json=payload, timeout=10)

        if response.status_code == 200:
            data = response.json()
            items = data.get("matches", data.get("results", data.get("memories", [])))

            for item in items[:max_results]:
                if isinstance(item, dict):
                    results.append({
                        "source": "openmemory",
                        "content": item.get("content", item.get("text", str(item)[:200])),
                        "sector": item.get("sector", item.get("primary_sector", "unknown")),
                        "score": item.get("score", item.get("similarity", 0))
                    })

    except Exception as e:
        results.append({"error": str(e)})

    elapsed_ms = (time.perf_counter() - start) * 1000
    return results, elapsed_ms


def query_lancedb(query: str, storage_path: str, embedding_type: str, max_results: int = 5) -> tuple[list[dict], float]:
    """Query LanceDB with specified embedding type, return (results, latency_ms)."""
    try:
        from unified_memory import EpisodicMemoryLanceDB, SemanticMemoryLanceDB, LANCEDB_AVAILABLE
        if not LANCEDB_AVAILABLE:
            return [{"error": "LanceDB not installed"}], 0
    except ImportError as e:
        return [{"error": f"Import error: {e}"}], 0

    full_path = f"{storage_path}_{embedding_type}"

    if not os.path.exists(full_path):
        return [{"error": f"Storage path not found: {full_path}"}], 0

    start = time.perf_counter()
    results = []

    try:
        episodic = EpisodicMemoryLanceDB(full_path, embedding_type)
        semantic = SemanticMemoryLanceDB(full_path, embedding_type)

        # Query episodic
        ep_results = episodic.search(query, max_results)
        for r in ep_results:
            results.append({
                "source": "episodic",
                "content": r.get("event", ""),
                "relevance": r.get("relevance", 0)
            })

        # Query semantic
        sem_results = semantic.search(query, max_results)
        for r in sem_results:
            results.append({
                "source": "semantic",
                "content": r.get("value", str(r)[:200]),
                "relevance": r.get("relevance", 0)
            })

    except Exception as e:
        results.append({"error": str(e)})

    elapsed_ms = (time.perf_counter() - start) * 1000
    return results, elapsed_ms


# =============================================================================
# SCORING
# =============================================================================

def score_retrieval(results: list[dict], expected_keywords: list[str]) -> dict:
    """Score retrieval quality based on keyword presence."""
    if not results or not expected_keywords:
        return {"recall": 0, "found": 0, "total": len(expected_keywords)}

    combined_text = " ".join(str(r.get("content", "")) for r in results).lower()
    found = sum(1 for kw in expected_keywords if kw.lower() in combined_text)
    total = len(expected_keywords)
    recall = found / total if total > 0 else 0

    return {"recall": round(recall, 3), "found": found, "total": total}


# =============================================================================
# BENCHMARK RUNNER
# =============================================================================

@dataclass
class SystemMetrics:
    """Aggregated metrics for one system."""
    system: str
    available: bool
    query_latencies_ms: list = field(default_factory=list)
    query_avg_latency_ms: float = 0
    query_cold_latency_ms: float = 0
    query_warm_latency_ms: float = 0
    avg_recall: float = 0
    query_recalls: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def check_graphiti_ready(group_id: str) -> bool:
    """Check if Graphiti has finished processing by searching for any nodes."""
    try:
        client = MCPClient(lambda: streamablehttp_client("http://localhost:8000/mcp"))
        client.__enter__()

        import uuid
        tool_use_id = f"check-{uuid.uuid4().hex[:8]}"
        raw_result = client.call_tool_sync(
            tool_use_id,
            "search_nodes",
            {"query": "agent", "group_ids": [group_id], "max_nodes": 1}
        )

        client.__exit__(None, None, None)

        structured = raw_result.get("structuredContent", {}).get("result", {})
        nodes = structured.get("nodes", [])
        return len(nodes) > 0

    except Exception:
        return False


def run_benchmark(state: dict) -> dict[str, SystemMetrics]:
    """Run queries against all systems."""
    results = {}

    # JSON
    print("\n" + "=" * 60)
    print("Querying: JSON")
    print("=" * 60)
    metrics = SystemMetrics(system="JSON", available=True)

    for i, q in enumerate(TEST_QUERIES):
        query_results, latency = query_json(q["query"])
        metrics.query_latencies_ms.append(latency)
        scores = score_retrieval(query_results, q["expected_keywords"])
        metrics.query_recalls.append(scores["recall"])
        print(f"  Q{i+1}: {latency:6.1f}ms, recall={scores['recall']:.2f}, results={len(query_results)}")

    if metrics.query_latencies_ms:
        metrics.query_avg_latency_ms = statistics.mean(metrics.query_latencies_ms)
        metrics.query_cold_latency_ms = metrics.query_latencies_ms[0]
        metrics.query_warm_latency_ms = statistics.mean(metrics.query_latencies_ms[1:]) if len(metrics.query_latencies_ms) > 1 else 0
    if metrics.query_recalls:
        metrics.avg_recall = statistics.mean(metrics.query_recalls)
    results["JSON"] = metrics

    # ChromaDB
    print("\n" + "=" * 60)
    print("Querying: ChromaDB")
    print("=" * 60)
    metrics = SystemMetrics(system="ChromaDB", available=CHROMADB_AVAILABLE)

    if CHROMADB_AVAILABLE:
        for i, q in enumerate(TEST_QUERIES):
            query_results, latency = query_chromadb(q["query"])
            metrics.query_latencies_ms.append(latency)
            scores = score_retrieval(query_results, q["expected_keywords"])
            metrics.query_recalls.append(scores["recall"])
            print(f"  Q{i+1}: {latency:6.1f}ms, recall={scores['recall']:.2f}, results={len(query_results)}")

        if metrics.query_latencies_ms:
            metrics.query_avg_latency_ms = statistics.mean(metrics.query_latencies_ms)
            metrics.query_cold_latency_ms = metrics.query_latencies_ms[0]
            metrics.query_warm_latency_ms = statistics.mean(metrics.query_latencies_ms[1:]) if len(metrics.query_latencies_ms) > 1 else 0
        if metrics.query_recalls:
            metrics.avg_recall = statistics.mean(metrics.query_recalls)
    else:
        print("  [SKIP] ChromaDB not available")
    results["ChromaDB"] = metrics

    # Graphiti
    print("\n" + "=" * 60)
    print("Querying: Graphiti")
    print("=" * 60)
    graphiti_state = state.get("systems", {}).get("Graphiti", {})
    group_id = graphiti_state.get("group_id", "")
    metrics = SystemMetrics(system="Graphiti", available=bool(group_id))

    if group_id:
        # Check if processing is complete
        print(f"  Checking if Graphiti finished processing (group: {group_id})...")
        ready = check_graphiti_ready(group_id)

        if not ready:
            print("  [WARNING] Graphiti may still be processing - results may be incomplete")
            print("  To check: docker logs graphiti-mcp-server -f")

        for i, q in enumerate(TEST_QUERIES):
            query_results, latency = query_graphiti(q["query"], group_id)
            metrics.query_latencies_ms.append(latency)
            scores = score_retrieval(query_results, q["expected_keywords"])
            metrics.query_recalls.append(scores["recall"])
            print(f"  Q{i+1}: {latency:6.1f}ms, recall={scores['recall']:.2f}, results={len(query_results)}")

        if metrics.query_latencies_ms:
            metrics.query_avg_latency_ms = statistics.mean(metrics.query_latencies_ms)
            metrics.query_cold_latency_ms = metrics.query_latencies_ms[0]
            metrics.query_warm_latency_ms = statistics.mean(metrics.query_latencies_ms[1:]) if len(metrics.query_latencies_ms) > 1 else 0
        if metrics.query_recalls:
            metrics.avg_recall = statistics.mean(metrics.query_recalls)
    else:
        print("  [SKIP] No Graphiti group_id in state")
    results["Graphiti"] = metrics

    # OpenMemory
    print("\n" + "=" * 60)
    print("Querying: OpenMemory")
    print("=" * 60)
    metrics = SystemMetrics(system="OpenMemory", available=True)

    for i, q in enumerate(TEST_QUERIES):
        query_results, latency = query_openmemory(q["query"])
        metrics.query_latencies_ms.append(latency)
        scores = score_retrieval(query_results, q["expected_keywords"])
        metrics.query_recalls.append(scores["recall"])
        print(f"  Q{i+1}: {latency:6.1f}ms, recall={scores['recall']:.2f}, results={len(query_results)}")

    if metrics.query_latencies_ms:
        metrics.query_avg_latency_ms = statistics.mean(metrics.query_latencies_ms)
        metrics.query_cold_latency_ms = metrics.query_latencies_ms[0]
        metrics.query_warm_latency_ms = statistics.mean(metrics.query_latencies_ms[1:]) if len(metrics.query_latencies_ms) > 1 else 0
    if metrics.query_recalls:
        metrics.avg_recall = statistics.mean(metrics.query_recalls)
    results["OpenMemory"] = metrics

    # LanceDB Local
    print("\n" + "=" * 60)
    print("Querying: LanceDB_Local (384-dim embeddings)")
    print("=" * 60)
    lancedb_local_state = state.get("systems", {}).get("LanceDB_Local", {})
    storage_path = lancedb_local_state.get("storage_path", "./benchmark_lancedb_local")
    metrics = SystemMetrics(system="LanceDB_Local", available="error" not in lancedb_local_state)

    if metrics.available:
        for i, q in enumerate(TEST_QUERIES):
            query_results, latency = query_lancedb(q["query"], "./benchmark_lancedb", "local")
            metrics.query_latencies_ms.append(latency)
            scores = score_retrieval(query_results, q["expected_keywords"])
            metrics.query_recalls.append(scores["recall"])
            print(f"  Q{i+1}: {latency:6.1f}ms, recall={scores['recall']:.2f}, results={len(query_results)}")

        if metrics.query_latencies_ms:
            metrics.query_avg_latency_ms = statistics.mean(metrics.query_latencies_ms)
            metrics.query_cold_latency_ms = metrics.query_latencies_ms[0]
            metrics.query_warm_latency_ms = statistics.mean(metrics.query_latencies_ms[1:]) if len(metrics.query_latencies_ms) > 1 else 0
        if metrics.query_recalls:
            metrics.avg_recall = statistics.mean(metrics.query_recalls)
    else:
        print(f"  [SKIP] LanceDB_Local not available: {lancedb_local_state.get('error', 'unknown')}")
    results["LanceDB_Local"] = metrics

    # LanceDB API
    print("\n" + "=" * 60)
    print("Querying: LanceDB_API (1536-dim embeddings)")
    print("=" * 60)
    lancedb_api_state = state.get("systems", {}).get("LanceDB_API", {})
    storage_path = lancedb_api_state.get("storage_path", "./benchmark_lancedb_api")
    metrics = SystemMetrics(system="LanceDB_API", available="error" not in lancedb_api_state)

    if metrics.available:
        for i, q in enumerate(TEST_QUERIES):
            query_results, latency = query_lancedb(q["query"], "./benchmark_lancedb", "api")
            metrics.query_latencies_ms.append(latency)
            scores = score_retrieval(query_results, q["expected_keywords"])
            metrics.query_recalls.append(scores["recall"])
            print(f"  Q{i+1}: {latency:6.1f}ms, recall={scores['recall']:.2f}, results={len(query_results)}")

        if metrics.query_latencies_ms:
            metrics.query_avg_latency_ms = statistics.mean(metrics.query_latencies_ms)
            metrics.query_cold_latency_ms = metrics.query_latencies_ms[0]
            metrics.query_warm_latency_ms = statistics.mean(metrics.query_latencies_ms[1:]) if len(metrics.query_latencies_ms) > 1 else 0
        if metrics.query_recalls:
            metrics.avg_recall = statistics.mean(metrics.query_recalls)
    else:
        print(f"  [SKIP] LanceDB_API not available: {lancedb_api_state.get('error', 'unknown')}")
    results["LanceDB_API"] = metrics

    return results


# =============================================================================
# RESULTS FORMATTING
# =============================================================================

def format_results_table(results: dict[str, SystemMetrics], state: dict) -> str:
    """Format benchmark results as human-readable table."""
    lines = []
    lines.append("\n" + "=" * 85)
    lines.append("MEMORY SYSTEMS BENCHMARK RESULTS")
    lines.append("=" * 85)
    lines.append(f"Store timestamp: {state.get('timestamp', 'unknown')}")
    lines.append(f"Query timestamp: {datetime.now().isoformat()}")
    lines.append(f"Observations: {state.get('observations_count', 0)}")
    lines.append("")

    # Summary table
    header = f"{'System':<12} {'Avail':<6} {'Query Avg':<12} {'Cold':<10} {'Warm':<10} {'Recall':<8}"
    lines.append(header)
    lines.append("-" * 85)

    for name, m in results.items():
        avail = "Yes" if m.available else "No"
        q_avg = f"{m.query_avg_latency_ms:.1f}" if m.query_avg_latency_ms else "N/A"
        cold = f"{m.query_cold_latency_ms:.1f}" if m.query_cold_latency_ms else "N/A"
        warm = f"{m.query_warm_latency_ms:.1f}" if m.query_warm_latency_ms else "N/A"
        recall = f"{m.avg_recall:.2f}" if m.avg_recall else "N/A"

        lines.append(f"{name:<12} {avail:<6} {q_avg:<12} {cold:<10} {warm:<10} {recall:<8}")

    lines.append("")
    lines.append("Legend:")
    lines.append("  Query Avg  = Average query latency across all queries")
    lines.append("  Cold       = First query latency (cache cold)")
    lines.append("  Warm       = Average of queries 2-N (cache warm)")
    lines.append("  Recall     = Avg found keywords / expected keywords")

    # Per-system details
    lines.append("\n" + "=" * 85)
    lines.append("DETAILED RESULTS BY SYSTEM")
    lines.append("=" * 85)

    for name, m in results.items():
        lines.append(f"\n[{name}]")
        lines.append(f"  Available: {m.available}")
        if m.available and m.query_latencies_ms:
            lines.append(f"  Queries: avg={m.query_avg_latency_ms:.1f}ms, cold={m.query_cold_latency_ms:.1f}ms, warm={m.query_warm_latency_ms:.1f}ms")
            lines.append(f"  Retrieval: avg recall={m.avg_recall:.3f}")
            if m.query_recalls:
                lines.append(f"  Per-query recalls: {[f'{r:.2f}' for r in m.query_recalls]}")

    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("Memory Systems Benchmark - Phase 2: QUERY")
    print("=" * 60)

    # Load state
    if not os.path.exists(STATE_FILE):
        print(f"\nERROR: State file not found: {STATE_FILE}")
        print("Run benchmark_store.py first!")
        return

    with open(STATE_FILE, "r") as f:
        state = json.load(f)

    print(f"\nLoaded state from: {STATE_FILE}")
    print(f"  Store timestamp: {state.get('timestamp')}")
    print(f"  Observations: {state.get('observations_count')}")

    # Show store results
    print("\nStore phase results:")
    for name, data in state.get("systems", {}).items():
        if "error" in data:
            print(f"  {name}: ERROR - {data['error']}")
        else:
            print(f"  {name}: {data.get('records_stored', 0)} records stored")

    # Run queries
    results = run_benchmark(state)

    # Format and print results
    output = format_results_table(results, state)
    print(output)

    print("\n" + "=" * 60)
    print("BENCHMARK COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()

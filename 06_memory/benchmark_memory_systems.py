"""
Memory Systems Benchmark
========================
Compare 4 memory backends using real learning observations data.

Systems:
1. JSON (baseline) - Keyword search, local files
2. ChromaDB - Vector similarity, embeddings
3. Graphiti MCP - Knowledge graph at localhost:8000
4. OpenMemory - 5-sector cognitive model at localhost:8080

Data Source: 112 observations from .claude/learnings/observations.jsonl

Run: uv run python 06_memory/benchmark_memory_systems.py
"""

import sys
import json
import os
import time
import statistics
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from abc import ABC, abstractmethod

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
# DATA LOADING
# =============================================================================

@dataclass
class Observation:
    """Single learning observation record."""
    ts: str
    level: int
    cat: str      # pattern, insight, mistake
    topic: str
    obs: str      # The main observation text
    ctx: str      # Context
    repo: str = ""
    entities: list = field(default_factory=list)

    def to_searchable_text(self) -> str:
        """Combine fields for embedding/storage."""
        return f"{self.obs}. Context: {self.ctx}. Topic: {self.topic}"

    def to_metadata(self) -> dict:
        """Extract metadata for filtering."""
        return {
            "level": self.level,
            "category": self.cat,
            "topic": self.topic,
            "timestamp": self.ts
        }


def load_observations(filepath: str = None) -> list[Observation]:
    """Load observations from JSONL file."""
    filepath = filepath or ".claude/learnings/observations.jsonl"
    observations = []

    with open(filepath, "r") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            observations.append(Observation(
                ts=data.get("ts", ""),
                level=data.get("level", 0),
                cat=data.get("cat", ""),
                topic=data.get("topic", ""),
                obs=data.get("obs", ""),
                ctx=data.get("ctx", ""),
                repo=data.get("repo", ""),
                entities=data.get("entities", [])
            ))

    return observations


# =============================================================================
# BENCHMARK RESULT & ADAPTER INTERFACE
# =============================================================================

@dataclass
class BenchmarkResult:
    """Results from a single benchmark operation."""
    system: str
    operation: str          # "store" or "query"
    latency_ms: float
    success: bool
    result_count: int = 0
    error: str = ""


class MemorySystemAdapter(ABC):
    """Base interface for memory system adapters."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Check if system is available."""
        pass

    @abstractmethod
    def store_all(self, observations: list[Observation]) -> BenchmarkResult:
        """Store all observations, return aggregate result."""
        pass

    @abstractmethod
    def query(self, query: str, max_results: int = 5) -> tuple[list[dict], BenchmarkResult]:
        """Query and return (results, benchmark_result)."""
        pass

    def clear(self):
        """Clear stored data for fresh benchmark."""
        pass


# =============================================================================
# JSON ADAPTER (BASELINE)
# =============================================================================

class JSONAdapter(MemorySystemAdapter):
    """
    JSON file storage with keyword search.

    Plain English: Simple local file storage, searches by exact keyword match.
    This is the baseline - fast but limited in finding semantic matches.
    """

    name = "JSON"

    def __init__(self, storage_dir: str = "./benchmark_json"):
        self.storage_dir = storage_dir
        self.episodic = None
        self.semantic = None

    def is_available(self) -> bool:
        return True  # Always available

    def clear(self):
        if os.path.exists(self.storage_dir):
            shutil.rmtree(self.storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)
        self.episodic = EpisodicMemoryJSON(storage_dir=self.storage_dir, group_id="benchmark")
        self.semantic = SemanticMemoryJSON(storage_dir=self.storage_dir, group_id="benchmark")

    def store_all(self, observations: list[Observation]) -> BenchmarkResult:
        start = time.perf_counter()
        success = True
        error = ""

        try:
            for obs in observations:
                self.episodic.store(
                    event=obs.obs,
                    context=f"Level {obs.level}: {obs.ctx}"
                )
                self.semantic.store(
                    entity=obs.topic,
                    fact_type=obs.cat,
                    value=obs.obs[:200]
                )
        except Exception as e:
            success = False
            error = str(e)

        elapsed_ms = (time.perf_counter() - start) * 1000
        return BenchmarkResult(
            system=self.name,
            operation="store",
            latency_ms=elapsed_ms,
            success=success,
            result_count=len(observations) * 2,
            error=error
        )

    def query(self, query: str, max_results: int = 5) -> tuple[list[dict], BenchmarkResult]:
        start = time.perf_counter()
        results = []
        success = True
        error = ""

        try:
            episodic_results = self.episodic.search(query, max_results)
            semantic_results = self.semantic.search(query)[:max_results]

            for r in episodic_results:
                results.append({"source": "episodic", "content": r.get("event", "")})
            for r in semantic_results:
                results.append({"source": "semantic", "content": r.get("value", str(r))})
        except Exception as e:
            success = False
            error = str(e)

        elapsed_ms = (time.perf_counter() - start) * 1000
        return results, BenchmarkResult(
            system=self.name,
            operation="query",
            latency_ms=elapsed_ms,
            success=success,
            result_count=len(results),
            error=error
        )


# =============================================================================
# CHROMADB ADAPTER
# =============================================================================

class ChromaDBAdapter(MemorySystemAdapter):
    """
    ChromaDB vector storage with semantic search.

    Plain English: Stores embeddings, finds results by MEANING not just keywords.
    "programming languages" finds "Python vs Kotlin" discussion.
    """

    name = "ChromaDB"

    def __init__(self, storage_dir: str = "./benchmark_chroma"):
        self.storage_dir = storage_dir
        self.episodic = None
        self.semantic = None

    def is_available(self) -> bool:
        return CHROMADB_AVAILABLE

    def clear(self):
        if os.path.exists(self.storage_dir):
            shutil.rmtree(self.storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)
        self.episodic = EpisodicMemoryChroma(
            storage_dir=self.storage_dir,
            collection_name="benchmark_episodes",
            in_memory=False
        )
        self.semantic = SemanticMemoryChroma(
            storage_dir=self.storage_dir,
            collection_name="benchmark_facts",
            in_memory=False
        )

    def store_all(self, observations: list[Observation]) -> BenchmarkResult:
        start = time.perf_counter()
        success = True
        error = ""

        try:
            for obs in observations:
                self.episodic.store(
                    event=obs.obs,
                    context=f"Level {obs.level}: {obs.ctx}"
                )
                self.semantic.store(
                    entity=obs.topic,
                    fact_type=obs.cat,
                    value=obs.obs[:200]
                )
        except Exception as e:
            success = False
            error = str(e)

        elapsed_ms = (time.perf_counter() - start) * 1000
        return BenchmarkResult(
            system=self.name,
            operation="store",
            latency_ms=elapsed_ms,
            success=success,
            result_count=len(observations) * 2,
            error=error
        )

    def query(self, query: str, max_results: int = 5) -> tuple[list[dict], BenchmarkResult]:
        start = time.perf_counter()
        results = []
        success = True
        error = ""

        try:
            episodic_results = self.episodic.search(query, max_results)
            semantic_results = self.semantic.search(query, max_results)

            for r in episodic_results:
                results.append({
                    "source": "episodic",
                    "content": r.get("event", ""),
                    "relevance": r.get("relevance", 0)
                })
            for r in semantic_results:
                results.append({
                    "source": "semantic",
                    "content": r.get("value", ""),
                    "relevance": r.get("relevance", 0)
                })
        except Exception as e:
            success = False
            error = str(e)

        elapsed_ms = (time.perf_counter() - start) * 1000
        return results, BenchmarkResult(
            system=self.name,
            operation="query",
            latency_ms=elapsed_ms,
            success=success,
            result_count=len(results),
            error=error
        )


# =============================================================================
# GRAPHITI MCP ADAPTER
# =============================================================================

class GraphitiAdapter(MemorySystemAdapter):
    """
    Graphiti MCP knowledge graph at localhost:8000.

    Plain English: Graph database that extracts entities and relationships.
    Note: Graphiti processes entities asynchronously - immediate queries may return empty.
    """

    name = "Graphiti"

    def __init__(self, server_url: str = "http://localhost:8000", group_id: str = "benchmark"):
        self.server_url = server_url
        self.group_id = group_id
        self.mcp_client = None
        self._connected = False

    def is_available(self) -> bool:
        if not MCP_AVAILABLE:
            return False
        try:
            response = requests.get(f"{self.server_url}/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def _connect(self):
        """Connect to Graphiti MCP server."""
        if self._connected:
            return True

        try:
            self.mcp_client = MCPClient(
                lambda: streamablehttp_client(f"{self.server_url}/mcp")
            )
            self.mcp_client.__enter__()
            self._connected = True
            return True
        except Exception as e:
            print(f"  [!] Graphiti connection failed: {e}")
            return False

    def _disconnect(self):
        if self.mcp_client and self._connected:
            try:
                self.mcp_client.__exit__(None, None, None)
            except Exception:
                pass
            self._connected = False

    def clear(self):
        # Use new group_id for fresh benchmark
        self.group_id = f"benchmark-{datetime.now().strftime('%H%M%S')}"
        self._connect()

    def store_all(self, observations: list[Observation]) -> BenchmarkResult:
        if not self._connect():
            return BenchmarkResult(
                system=self.name, operation="store", latency_ms=0,
                success=False, error="Connection failed"
            )

        start = time.perf_counter()
        success = True
        error = ""
        count = 0

        try:
            import uuid
            for obs in observations:
                tool_use_id = f"store-{uuid.uuid4().hex[:8]}"
                self.mcp_client.call_tool_sync(
                    tool_use_id,
                    "add_memory",
                    {
                        "name": f"L{obs.level}-{obs.topic}",
                        "episode_body": obs.to_searchable_text(),
                        "group_id": self.group_id,
                        "source": "text",
                        "source_description": f"Learning observation L{obs.level}"
                    }
                )
                count += 1
        except Exception as e:
            success = False
            error = str(e)

        elapsed_ms = (time.perf_counter() - start) * 1000
        return BenchmarkResult(
            system=self.name,
            operation="store",
            latency_ms=elapsed_ms,
            success=success,
            result_count=count,
            error=error
        )

    def query(self, query: str, max_results: int = 5) -> tuple[list[dict], BenchmarkResult]:
        if not self._connected:
            return [], BenchmarkResult(
                system=self.name, operation="query", latency_ms=0,
                success=False, error="Not connected"
            )

        start = time.perf_counter()
        results = []
        success = True
        error = ""

        try:
            import uuid
            tool_use_id = f"search-{uuid.uuid4().hex[:8]}"
            raw_result = self.mcp_client.call_tool_sync(
                tool_use_id,
                "search_memory_facts",
                {"query": query, "group_ids": [self.group_id], "max_facts": max_results}
            )
            # Parse result
            result_str = str(raw_result)
            results.append({"source": "graphiti", "content": result_str[:500]})
        except Exception as e:
            success = False
            error = str(e)

        elapsed_ms = (time.perf_counter() - start) * 1000
        return results, BenchmarkResult(
            system=self.name,
            operation="query",
            latency_ms=elapsed_ms,
            success=success,
            result_count=len(results),
            error=error
        )


# =============================================================================
# OPENMEMORY ADAPTER
# =============================================================================

class OpenMemoryAdapter(MemorySystemAdapter):
    """
    OpenMemory HSG v3 at localhost:8080.

    Plain English: 5-sector cognitive model that auto-classifies memories.
    Sectors: episodic, semantic, procedural, emotional, reflective.
    """

    name = "OpenMemory"

    def __init__(self, server_url: str = "http://localhost:8080", api_key: str = "benchmark-test-key-2025"):
        self.server_url = server_url
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })

    def is_available(self) -> bool:
        try:
            response = self.session.get(f"{self.server_url}/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def clear(self):
        # Clear existing memories if endpoint exists
        try:
            response = self.session.get(f"{self.server_url}/memory/all", timeout=5)
            if response.status_code == 200:
                data = response.json()
                memories = data.get("memories", data) if isinstance(data, dict) else data
                if isinstance(memories, list):
                    for m in memories[:100]:  # Limit cleanup
                        if isinstance(m, dict) and "id" in m:
                            self.session.delete(
                                f"{self.server_url}/memory/{m['id']}",
                                timeout=2
                            )
        except Exception:
            pass  # Proceed even if clear fails

    def store_all(self, observations: list[Observation]) -> BenchmarkResult:
        start = time.perf_counter()
        success = True
        error = ""
        count = 0

        try:
            for obs in observations:
                payload = {
                    "content": obs.to_searchable_text(),
                    "metadata": obs.to_metadata()
                }
                response = self.session.post(
                    f"{self.server_url}/memory/add",
                    json=payload,
                    timeout=5
                )
                if response.status_code in (200, 201):
                    count += 1
        except Exception as e:
            success = False
            error = str(e)

        elapsed_ms = (time.perf_counter() - start) * 1000
        return BenchmarkResult(
            system=self.name,
            operation="store",
            latency_ms=elapsed_ms,
            success=success,
            result_count=count,
            error=error
        )

    def query(self, query: str, max_results: int = 5) -> tuple[list[dict], BenchmarkResult]:
        start = time.perf_counter()
        results = []
        success = True
        error = ""

        try:
            payload = {
                "query": query,
                "limit": max_results
            }
            response = self.session.post(
                f"{self.server_url}/memory/query",
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                # Normalize response format - OpenMemory uses "matches" key
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
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
            success = False
            error = str(e)

        elapsed_ms = (time.perf_counter() - start) * 1000
        return results, BenchmarkResult(
            system=self.name,
            operation="query",
            latency_ms=elapsed_ms,
            success=success,
            result_count=len(results),
            error=error
        )


# =============================================================================
# TEST QUERIES
# =============================================================================

TEST_QUERIES = [
    # Exact Match (keyword-friendly)
    {
        "query": "streaming",
        "type": "exact_match",
        "description": "Find observations about streaming behavior",
        "expected_keywords": ["stream", "callback", "PrintingCallbackHandler", "output"]
    },
    {
        "query": "ChromaDB",
        "type": "exact_match",
        "description": "Find ChromaDB-specific learnings",
        "expected_keywords": ["chroma", "vector", "embedding", "semantic"]
    },

    # Category Filter
    {
        "query": "mistake error bug",
        "type": "category_filter",
        "description": "Find all mistakes/errors",
        "expected_keywords": ["mistake", "error", "failed", "bug", "TypeError"]
    },

    # Temporal/Level
    {
        "query": "level 16 unified memory",
        "type": "temporal",
        "description": "Learnings from L16 unified memory",
        "expected_keywords": ["unified", "facade", "layer", "routing", "backend"]
    },
    {
        "query": "level 1 basics hello",
        "type": "temporal",
        "description": "Basic learnings from L1",
        "expected_keywords": ["OpenAIModel", "LiteLLM", "proxy", "provider"]
    },

    # Cross-Reference (semantic)
    {
        "query": "context management memory optimization",
        "type": "cross_reference",
        "description": "How context relates to memory",
        "expected_keywords": ["40%", "utilization", "token", "compress", "budget"]
    },
    {
        "query": "multi-agent patterns coordination",
        "type": "cross_reference",
        "description": "Agent collaboration patterns",
        "expected_keywords": ["swarm", "graph", "orchestrator", "handoff", "delegation"]
    },

    # Multi-hop (relationship)
    {
        "query": "tools needed for RAG retrieval",
        "type": "multi_hop",
        "description": "RAG implementation requirements",
        "expected_keywords": ["ChromaDB", "embedding", "chunk", "search", "document"]
    },
    {
        "query": "production deployment requirements",
        "type": "multi_hop",
        "description": "What's needed for production agents",
        "expected_keywords": ["AgentCore", "MCP", "health", "endpoint", "8080"]
    },

    # Semantic Understanding
    {
        "query": "how to make agents remember things",
        "type": "semantic",
        "description": "Memory persistence (natural language)",
        "expected_keywords": ["session", "episodic", "semantic", "persist", "store"]
    }
]


# =============================================================================
# SCORING
# =============================================================================

def score_retrieval(results: list[dict], expected_keywords: list[str]) -> dict:
    """
    Score retrieval quality.

    Plain English: Check how many expected keywords appear in results.
    Returns recall (of expected) and simple accuracy metric.
    """
    if not results or not expected_keywords:
        return {"recall": 0, "found": 0, "total": len(expected_keywords)}

    # Combine all result content
    combined_text = " ".join(str(r.get("content", "")) for r in results).lower()

    # Count keyword hits
    found = sum(1 for kw in expected_keywords if kw.lower() in combined_text)
    total = len(expected_keywords)

    recall = found / total if total > 0 else 0

    return {
        "recall": round(recall, 3),
        "found": found,
        "total": total
    }


# =============================================================================
# BENCHMARK RUNNER
# =============================================================================

@dataclass
class SystemMetrics:
    """Aggregated metrics for one system."""
    system: str
    available: bool
    store_latency_ms: float = 0
    store_success: bool = False
    records_stored: int = 0

    # Query metrics
    query_latencies_ms: list = field(default_factory=list)
    query_avg_latency_ms: float = 0
    query_cold_latency_ms: float = 0
    query_warm_latency_ms: float = 0

    # Retrieval quality
    avg_recall: float = 0
    query_recalls: list = field(default_factory=list)

    errors: list = field(default_factory=list)


def run_benchmark(
    adapters: list[MemorySystemAdapter],
    observations: list[Observation],
    queries: list[dict]
) -> dict[str, SystemMetrics]:
    """Run full benchmark across all systems."""
    results = {}

    for adapter in adapters:
        print(f"\n{'='*60}")
        print(f"Benchmarking: {adapter.name}")
        print(f"{'='*60}")

        metrics = SystemMetrics(system=adapter.name, available=adapter.is_available())

        if not metrics.available:
            print(f"  [SKIP] {adapter.name} not available")
            results[adapter.name] = metrics
            continue

        # Clear and store
        print(f"\n[1/3] Clearing previous data...")
        adapter.clear()

        print(f"[2/3] Storing {len(observations)} observations...")
        store_result = adapter.store_all(observations)
        metrics.store_latency_ms = store_result.latency_ms
        metrics.store_success = store_result.success
        metrics.records_stored = store_result.result_count

        if not store_result.success:
            metrics.errors.append(f"Store failed: {store_result.error}")
            print(f"  [ERROR] {store_result.error}")
            results[adapter.name] = metrics
            continue

        print(f"  Stored {store_result.result_count} records in {store_result.latency_ms:.1f}ms")

        # Run queries
        print(f"[3/3] Running {len(queries)} test queries...")

        for i, q in enumerate(queries):
            query_results, query_benchmark = adapter.query(q["query"])
            metrics.query_latencies_ms.append(query_benchmark.latency_ms)

            # Score retrieval
            scores = score_retrieval(query_results, q.get("expected_keywords", []))
            metrics.query_recalls.append(scores["recall"])

            if not query_benchmark.success:
                metrics.errors.append(f"Query {i} failed: {query_benchmark.error}")

            # Progress indicator
            print(f"  Q{i+1}: {query_benchmark.latency_ms:6.1f}ms, "
                  f"recall={scores['recall']:.2f}, "
                  f"results={query_benchmark.result_count}")

        # Calculate aggregates
        if metrics.query_latencies_ms:
            metrics.query_avg_latency_ms = statistics.mean(metrics.query_latencies_ms)
            metrics.query_cold_latency_ms = metrics.query_latencies_ms[0]
            if len(metrics.query_latencies_ms) > 1:
                metrics.query_warm_latency_ms = statistics.mean(metrics.query_latencies_ms[1:])

        if metrics.query_recalls:
            metrics.avg_recall = statistics.mean(metrics.query_recalls)

        results[adapter.name] = metrics

    return results


# =============================================================================
# RESULTS FORMATTING
# =============================================================================

def format_results_table(results: dict[str, SystemMetrics]) -> str:
    """Format benchmark results as human-readable table."""
    lines = []
    lines.append("\n" + "=" * 85)
    lines.append("MEMORY SYSTEMS BENCHMARK RESULTS")
    lines.append("=" * 85)
    lines.append(f"Timestamp: {datetime.now().isoformat()}")
    lines.append(f"Systems tested: {len(results)}")
    lines.append("")

    # Summary table
    header = f"{'System':<12} {'Avail':<6} {'Store(ms)':<12} {'Query Avg':<12} {'Cold':<10} {'Warm':<10} {'Recall':<8}"
    lines.append(header)
    lines.append("-" * 85)

    for name, m in results.items():
        avail = "Yes" if m.available else "No"
        store = f"{m.store_latency_ms:.1f}" if m.store_success else "FAIL"
        q_avg = f"{m.query_avg_latency_ms:.1f}" if m.query_avg_latency_ms else "N/A"
        cold = f"{m.query_cold_latency_ms:.1f}" if m.query_cold_latency_ms else "N/A"
        warm = f"{m.query_warm_latency_ms:.1f}" if m.query_warm_latency_ms else "N/A"
        recall = f"{m.avg_recall:.2f}" if m.avg_recall else "N/A"

        lines.append(f"{name:<12} {avail:<6} {store:<12} {q_avg:<12} {cold:<10} {warm:<10} {recall:<8}")

    lines.append("")
    lines.append("Legend:")
    lines.append("  Store(ms)  = Time to store all observations")
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
        if m.available and m.store_success:
            lines.append(f"  Store: {m.store_latency_ms:.1f}ms ({m.records_stored} records)")
            lines.append(f"  Queries: avg={m.query_avg_latency_ms:.1f}ms, cold={m.query_cold_latency_ms:.1f}ms, warm={m.query_warm_latency_ms:.1f}ms")
            lines.append(f"  Retrieval: avg recall={m.avg_recall:.3f}")
            if m.query_recalls:
                lines.append(f"  Per-query recalls: {[f'{r:.2f}' for r in m.query_recalls]}")
            if m.errors:
                lines.append(f"  Errors: {len(m.errors)}")
                for e in m.errors[:3]:
                    lines.append(f"    - {e[:80]}")
        elif not m.available:
            lines.append("  Status: NOT AVAILABLE (service not running)")
        else:
            lines.append(f"  Status: STORE FAILED")
            if m.errors:
                lines.append(f"  Error: {m.errors[0][:100]}")

    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run the complete benchmark."""
    print("=" * 60)
    print("Memory Systems Benchmark")
    print("=" * 60)
    print("""
Comparing 4 memory systems using learning observations:
1. JSON (baseline) - Keyword search
2. ChromaDB - Vector semantic search
3. Graphiti MCP - Knowledge graph (localhost:8000)
4. OpenMemory - 5-sector cognitive model (localhost:8080)
""")

    # Load data
    print("[Loading observations...]")
    observations = load_observations()
    print(f"  Loaded {len(observations)} observations")

    # Count categories
    patterns = len([o for o in observations if o.cat == "pattern"])
    insights = len([o for o in observations if o.cat == "insight"])
    mistakes = len([o for o in observations if o.cat == "mistake"])
    print(f"  Categories: {patterns} patterns, {insights} insights, {mistakes} mistakes")

    # Check availability
    print("\n[Checking system availability...]")

    adapters = [
        JSONAdapter(),
        ChromaDBAdapter() if CHROMADB_AVAILABLE else None,
        GraphitiAdapter(),
        OpenMemoryAdapter()
    ]
    adapters = [a for a in adapters if a is not None]

    for adapter in adapters:
        avail = adapter.is_available()
        status = "OK" if avail else "NOT AVAILABLE"
        print(f"  {adapter.name}: {status}")

    # Run benchmark
    results = run_benchmark(adapters, observations, TEST_QUERIES)

    # Format and print results
    output = format_results_table(results)
    print(output)

    # Cleanup
    print("\n[Cleanup...]")
    for d in ["./benchmark_json", "./benchmark_chroma"]:
        shutil.rmtree(d, ignore_errors=True)
    print("Done.")

    return results


if __name__ == "__main__":
    main()

"""
Memory Systems Benchmark - Phase 1: Store
==========================================
Store observations to all 6 memory backends.
Saves state to benchmark_state.json for Phase 2 (query).

Systems:
1. JSON (baseline) - Keyword search, local files
2. ChromaDB - Vector similarity, embeddings
3. Graphiti MCP - Knowledge graph (ASYNC - takes ~24 min for 112 records)
4. OpenMemory - 5-sector cognitive model
5. LanceDB_Local - Vector similarity, local embeddings (384-dim)
6. LanceDB_API - Vector similarity, API embeddings (1536-dim)

Run: uv run python 06_memory/benchmark_store.py
Then wait ~25-30 min, then: uv run python 06_memory/benchmark_query.py
"""

import sys
import json
import os
import time
import shutil
from datetime import datetime
from dataclasses import dataclass, field, asdict

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
OBSERVATIONS_FILE = ".claude/learnings/observations.jsonl"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Observation:
    """Single learning observation record."""
    ts: str
    level: int
    cat: str
    topic: str
    obs: str
    ctx: str
    repo: str = ""
    entities: list = field(default_factory=list)

    def to_searchable_text(self) -> str:
        return f"{self.obs}. Context: {self.ctx}. Topic: {self.topic}"

    def to_metadata(self) -> dict:
        return {
            "level": self.level,
            "category": self.cat,
            "topic": self.topic,
            "timestamp": self.ts
        }


@dataclass
class BenchmarkState:
    """Shared state between store and query phases."""
    timestamp: str
    observations_count: int
    systems: dict = field(default_factory=dict)  # system_name -> {group_id, records_stored, store_time_ms}


def load_observations() -> list[Observation]:
    """Load observations from JSONL file."""
    observations = []
    with open(OBSERVATIONS_FILE, "r") as f:
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
# STORE FUNCTIONS
# =============================================================================

def store_json(observations: list[Observation], storage_dir: str = "./benchmark_json") -> dict:
    """Store to JSON backend."""
    if os.path.exists(storage_dir):
        shutil.rmtree(storage_dir)
    os.makedirs(storage_dir, exist_ok=True)

    episodic = EpisodicMemoryJSON(storage_dir=storage_dir, group_id="benchmark")
    semantic = SemanticMemoryJSON(storage_dir=storage_dir, group_id="benchmark")

    start = time.perf_counter()
    for obs in observations:
        episodic.store(event=obs.obs, context=f"Level {obs.level}: {obs.ctx}")
        semantic.store(entity=obs.topic, fact_type=obs.cat, value=obs.obs[:200])
    elapsed_ms = (time.perf_counter() - start) * 1000

    return {
        "storage_dir": storage_dir,
        "records_stored": len(observations) * 2,
        "store_time_ms": elapsed_ms
    }


def store_chromadb(observations: list[Observation], storage_dir: str = "./benchmark_chroma") -> dict:
    """Store to ChromaDB backend."""
    if not CHROMADB_AVAILABLE:
        return {"error": "ChromaDB not available"}

    if os.path.exists(storage_dir):
        shutil.rmtree(storage_dir)
    os.makedirs(storage_dir, exist_ok=True)

    episodic = EpisodicMemoryChroma(storage_dir=storage_dir, collection_name="benchmark_episodes", in_memory=False)
    semantic = SemanticMemoryChroma(storage_dir=storage_dir, collection_name="benchmark_facts", in_memory=False)

    start = time.perf_counter()
    for obs in observations:
        episodic.store(event=obs.obs, context=f"Level {obs.level}: {obs.ctx}")
        semantic.store(entity=obs.topic, fact_type=obs.cat, value=obs.obs[:200])
    elapsed_ms = (time.perf_counter() - start) * 1000

    return {
        "storage_dir": storage_dir,
        "records_stored": len(observations) * 2,
        "store_time_ms": elapsed_ms
    }


def store_graphiti(observations: list[Observation]) -> dict:
    """Store to Graphiti MCP (async - processing happens in background)."""
    if not MCP_AVAILABLE:
        return {"error": "MCP client not available"}

    # Check health first
    try:
        response = requests.get("http://localhost:8000/health", timeout=2)
        if response.status_code != 200:
            return {"error": "Graphiti not healthy"}
    except Exception as e:
        return {"error": f"Graphiti connection failed: {e}"}

    # Generate unique group_id for this benchmark
    group_id = f"benchmark-{datetime.now().strftime('%H%M%S')}"

    try:
        client = MCPClient(lambda: streamablehttp_client("http://localhost:8000/mcp"))
        client.__enter__()

        start = time.perf_counter()
        count = 0

        import uuid
        for obs in observations:
            tool_use_id = f"store-{uuid.uuid4().hex[:8]}"
            client.call_tool_sync(
                tool_use_id,
                "add_memory",
                {
                    "name": f"L{obs.level}-{obs.topic}",
                    "episode_body": obs.to_searchable_text(),
                    "group_id": group_id,
                    "source": "text",
                    "source_description": f"Learning observation L{obs.level}"
                }
            )
            count += 1

        elapsed_ms = (time.perf_counter() - start) * 1000
        client.__exit__(None, None, None)

        return {
            "group_id": group_id,
            "records_stored": count,
            "store_time_ms": elapsed_ms,
            "note": "Async processing - wait ~24 min before querying"
        }

    except Exception as e:
        return {"error": str(e)}


def store_openmemory(observations: list[Observation]) -> dict:
    """Store to OpenMemory (sync - immediately queryable)."""
    # Check health first
    try:
        response = requests.get("http://localhost:8080/health", timeout=2)
        if response.status_code != 200:
            return {"error": "OpenMemory not healthy"}
    except Exception as e:
        return {"error": f"OpenMemory connection failed: {e}"}

    session = requests.Session()
    session.headers.update({
        "Authorization": "Bearer benchmark-test-key-2025",
        "Content-Type": "application/json"
    })

    # Clear existing benchmark memories
    try:
        response = session.get("http://localhost:8080/memory/all", timeout=5)
        if response.status_code == 200:
            data = response.json()
            memories = data.get("memories", data) if isinstance(data, dict) else data
            if isinstance(memories, list):
                for m in memories[:200]:
                    if isinstance(m, dict) and "id" in m:
                        session.delete(f"http://localhost:8080/memory/{m['id']}", timeout=2)
    except Exception:
        pass

    start = time.perf_counter()
    count = 0

    for obs in observations:
        payload = {
            "content": obs.to_searchable_text(),
            "metadata": obs.to_metadata()
        }
        try:
            response = session.post("http://localhost:8080/memory/add", json=payload, timeout=5)
            if response.status_code in (200, 201):
                count += 1
        except Exception:
            pass

    elapsed_ms = (time.perf_counter() - start) * 1000

    return {
        "records_stored": count,
        "store_time_ms": elapsed_ms
    }


def store_lancedb(observations: list[Observation], storage_path: str, embedding_type: str) -> dict:
    """
    Store to LanceDB with specified embedding type.

    Args:
        observations: List of observations to store
        storage_path: Base path for LanceDB storage
        embedding_type: "local" (384-dim) or "api" (1536-dim)

    Returns:
        dict with storage_path, embedding_type, records_stored, store_time_ms
    """
    try:
        from unified_memory import EpisodicMemoryLanceDB, SemanticMemoryLanceDB, LANCEDB_AVAILABLE
        if not LANCEDB_AVAILABLE:
            return {"error": "LanceDB not installed"}
    except ImportError as e:
        return {"error": f"Failed to import LanceDB classes: {e}"}

    full_path = f"{storage_path}_{embedding_type}"

    # Clean existing data
    if os.path.exists(full_path):
        shutil.rmtree(full_path)

    try:
        episodic = EpisodicMemoryLanceDB(full_path, embedding_type)
        semantic = SemanticMemoryLanceDB(full_path, embedding_type)
    except Exception as e:
        return {"error": f"Failed to initialize LanceDB: {e}"}

    start = time.perf_counter()
    count = 0

    for obs in observations:
        try:
            # Store as episodic event
            episodic.store(event=obs.obs, context=f"Level {obs.level}: {obs.ctx}")
            # Store as semantic fact
            semantic.store(entity=obs.topic, fact_type=obs.cat, value=obs.obs[:200])
            count += 2  # Count both episodic and semantic records
        except Exception as e:
            print(f"    Warning: Failed to store obs: {e}")
            continue

    elapsed_ms = (time.perf_counter() - start) * 1000

    return {
        "storage_path": full_path,
        "embedding_type": embedding_type,
        "records_stored": count,
        "store_time_ms": elapsed_ms
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("Memory Systems Benchmark - Phase 1: STORE")
    print("=" * 60)

    # Load observations
    print("\n[1/7] Loading observations...")
    observations = load_observations()
    print(f"  Loaded {len(observations)} observations")

    state = BenchmarkState(
        timestamp=datetime.now().isoformat(),
        observations_count=len(observations)
    )

    # Store to each system
    print("\n[2/7] Storing to JSON...")
    result = store_json(observations)
    state.systems["JSON"] = result
    print(f"  {result.get('records_stored', 0)} records in {result.get('store_time_ms', 0):.1f}ms")

    print("\n[3/7] Storing to ChromaDB...")
    result = store_chromadb(observations)
    state.systems["ChromaDB"] = result
    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  {result.get('records_stored', 0)} records in {result.get('store_time_ms', 0):.1f}ms")

    print("\n[4/7] Storing to Graphiti (async)...")
    result = store_graphiti(observations)
    state.systems["Graphiti"] = result
    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  {result.get('records_stored', 0)} records in {result.get('store_time_ms', 0):.1f}ms")
        print(f"  group_id: {result.get('group_id')}")
        print(f"  NOTE: {result.get('note', '')}")

    print("\n[5/7] Storing to OpenMemory...")
    result = store_openmemory(observations)
    state.systems["OpenMemory"] = result
    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  {result.get('records_stored', 0)} records in {result.get('store_time_ms', 0):.1f}ms")

    print("\n[6/7] Storing to LanceDB (local embeddings, 384-dim)...")
    result = store_lancedb(observations, "./benchmark_lancedb", "local")
    state.systems["LanceDB_Local"] = result
    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  {result.get('records_stored', 0)} records in {result.get('store_time_ms', 0):.1f}ms")

    print("\n[7/7] Storing to LanceDB (API embeddings, 1536-dim)...")
    result = store_lancedb(observations, "./benchmark_lancedb", "api")
    state.systems["LanceDB_API"] = result
    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  {result.get('records_stored', 0)} records in {result.get('store_time_ms', 0):.1f}ms")

    # Save state
    with open(STATE_FILE, "w") as f:
        json.dump(asdict(state), f, indent=2)
    print(f"\n[State saved to {STATE_FILE}]")

    # Summary
    print("\n" + "=" * 60)
    print("STORAGE COMPLETE")
    print("=" * 60)
    print(f"Timestamp: {state.timestamp}")
    print(f"Observations: {state.observations_count}")
    print("\nPer-system results:")
    for name, data in state.systems.items():
        if "error" in data:
            print(f"  {name}: ERROR - {data['error']}")
        else:
            print(f"  {name}: {data.get('records_stored', 0)} records, {data.get('store_time_ms', 0):.1f}ms")

    print("\n" + "=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print("1. Wait ~25-30 minutes for Graphiti to finish processing")
    print("   Monitor: docker logs graphiti-mcp-server -f")
    print("\n2. Run query phase:")
    print("   uv run python 06_memory/benchmark_query.py")


if __name__ == "__main__":
    main()

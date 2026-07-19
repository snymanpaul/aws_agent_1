"""
Level 14: Long-term Memory
==========================
Memory that persists across agent sessions.

Three Memory Layers:
1. Working: Current conversation (SessionManager) - from Level 5
2. Episodic: Specific interactions/events - NEW
3. Semantic: Extracted facts/knowledge - NEW

Iteration Progression:
1. Local JSON: Keyword-based search (foundation)
2. ChromaDB: Semantic vector search (meaning-based)
3. Graphiti: Graph + temporal facts (relationships)
4. Mem0: SOTA comparison (benchmarking)
5. Memory-Augmented Agent: Combined patterns
6. Cross-Session Demo: Persistence proof

Key Concepts:
- Episodic vs semantic memory distinction
- Search evolution: keyword -> vector -> graph
- Memory persistence across sessions
- Memory retrieval for agent context

Prerequisites:
- LiteLLM proxy running at localhost:4000
- Graphiti MCP server at localhost:8000 (for Iteration 3)

Run: uv run python 06_memory/longterm_memory.py
"""

import sys
import json
import os
import shutil
from datetime import datetime
from typing import Optional

sys.path.insert(0, ".")

from strands import Agent, tool
from strands.session.file_session_manager import FileSessionManager
from tools import get_model

# MCP client for Graphiti (real implementation)
try:
    from strands.tools.mcp import MCPClient
    from mcp.client.streamable_http import streamablehttp_client
    import uuid
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("Warning: MCP client not available. Graphiti features will be simulated.")

# Use sonnet for reliable memory operations
model = get_model("claude-sonnet-4")

# =============================================================================
# Configuration
# =============================================================================
SESSION_DIR = "./memory_sessions"
LOCAL_MEMORY_DIR = "./local_memory"
CHROMA_MEMORY_DIR = "./chroma_memory"
GRAPHITI_GROUP_ID = "level14-demo"

# =============================================================================
# ITERATION 1: Local JSON Memory (Foundation)
# =============================================================================

class EpisodicMemoryJSON:
    """
    Episodic memory with local JSON storage and keyword search.

    Plain English: Like a diary - records WHAT happened, WHEN, with WHOM.
    Search: Simple keyword matching (case-insensitive).

    Limitation: Can't find semantically similar content, only exact keywords.
    """

    def __init__(self, storage_dir: str = LOCAL_MEMORY_DIR, group_id: str = "default"):
        self.storage_dir = storage_dir
        self.group_id = group_id
        os.makedirs(storage_dir, exist_ok=True)

    @property
    def filepath(self) -> str:
        return os.path.join(self.storage_dir, f"{self.group_id}_episodes.jsonl")

    def store(self, event: str, context: str = "") -> dict:
        """Store a specific interaction/event."""
        episode = {
            "event": event,
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "group_id": self.group_id
        }

        with open(self.filepath, "a") as f:
            f.write(json.dumps(episode) + "\n")

        return episode

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Search episodes by keyword matching."""
        if not os.path.exists(self.filepath):
            return []

        query_lower = query.lower()
        matches = []

        with open(self.filepath, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                episode = json.loads(line)
                # Keyword search in event and context
                if (query_lower in episode.get("event", "").lower() or
                    query_lower in episode.get("context", "").lower()):
                    matches.append(episode)

        return matches[:max_results]

    def get_all(self) -> list[dict]:
        """Get all episodes."""
        if not os.path.exists(self.filepath):
            return []

        episodes = []
        with open(self.filepath, "r") as f:
            for line in f:
                if line.strip():
                    episodes.append(json.loads(line))
        return episodes


class SemanticMemoryJSON:
    """
    Semantic memory with local JSON storage.

    Plain English: Like an encyclopedia - stores WHAT is true about entities.
    Structure: entity -> {fact_type: value}
    Search: Keyword matching on entity names and fact values.
    """

    def __init__(self, storage_dir: str = LOCAL_MEMORY_DIR, group_id: str = "default"):
        self.storage_dir = storage_dir
        self.group_id = group_id
        os.makedirs(storage_dir, exist_ok=True)
        self.facts: dict = self._load()

    @property
    def filepath(self) -> str:
        return os.path.join(self.storage_dir, f"{self.group_id}_facts.json")

    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            with open(self.filepath, "r") as f:
                return json.load(f)
        return {}

    def _save(self):
        with open(self.filepath, "w") as f:
            json.dump(self.facts, f, indent=2)

    def store(self, entity: str, fact_type: str, value: str) -> dict:
        """Store a fact about an entity."""
        if entity not in self.facts:
            self.facts[entity] = {}

        self.facts[entity][fact_type] = {
            "value": value,
            "learned_at": datetime.now().isoformat()
        }
        self._save()

        return {"entity": entity, "fact_type": fact_type, "value": value}

    def get_facts(self, entity: str) -> dict:
        """Get all facts about an entity."""
        return self.facts.get(entity, {})

    def search(self, query: str) -> list[dict]:
        """Search facts by keyword."""
        results = []
        query_lower = query.lower()

        for entity, facts in self.facts.items():
            if query_lower in entity.lower():
                results.append({"entity": entity, "facts": facts})
            else:
                for fact_type, fact_data in facts.items():
                    val = str(fact_data.get("value", "")).lower()
                    if query_lower in fact_type.lower() or query_lower in val:
                        results.append({
                            "entity": entity,
                            "fact_type": fact_type,
                            "value": fact_data.get("value")
                        })

        return results


# Iteration 1 tools
episodic_json = EpisodicMemoryJSON(group_id="iter1")
semantic_json = SemanticMemoryJSON(group_id="iter1")


@tool
def remember_event_json(event: str, context: str = "") -> str:
    """
    Store an interaction in episodic memory (JSON, keyword search).
    Use for recording specific events worth remembering.

    Args:
        event: What happened (the interaction to remember)
        context: Additional context about the situation

    Returns:
        Confirmation of stored memory
    """
    ep = episodic_json.store(event, context)
    return f"Remembered: {event[:80]}... (stored at {ep['timestamp']})"


@tool
def recall_events_json(query: str) -> str:
    """
    Search episodic memory using keyword matching (JSON backend).

    Args:
        query: Keywords to search for

    Returns:
        Matching past events
    """
    episodes = episodic_json.search(query)
    if not episodes:
        return f"No events found matching: {query}"

    results = [f"[{e['timestamp']}] {e['event'][:200]}" for e in episodes]
    return "Past events:\n" + "\n".join(results)


@tool
def learn_fact_json(entity: str, fact_type: str, value: str) -> str:
    """
    Store a fact in semantic memory (JSON backend).

    Args:
        entity: Subject (e.g., "user", "Python", "project_x")
        fact_type: Type of fact (e.g., "preference", "definition")
        value: The fact value

    Returns:
        Confirmation of learned fact
    """
    semantic_json.store(entity, fact_type, value)
    return f"Learned: {entity} - {fact_type}: {value}"


@tool
def recall_facts_json(query: str) -> str:
    """
    Search semantic memory using keyword matching (JSON backend).

    Args:
        query: Entity or keyword to search for

    Returns:
        Matching facts
    """
    results = semantic_json.search(query)
    if not results:
        return f"No facts found for: {query}"

    output = []
    for r in results:
        if "facts" in r:
            output.append(f"{r['entity']}: {json.dumps(r['facts'], indent=2)}")
        else:
            output.append(f"{r['entity']} - {r.get('fact_type', '?')}: {r.get('value', '?')}")

    return "Known facts:\n" + "\n".join(output)


# =============================================================================
# ITERATION 2: ChromaDB Vector Memory (Semantic Search)
# =============================================================================

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("ChromaDB not available. Install with: uv add chromadb")


class EpisodicMemoryChroma:
    """
    Episodic memory with ChromaDB vector storage.

    Improvement over JSON: Semantic search finds MEANING, not just keywords.
    "user mentioned Python" will match "they discussed programming languages"
    """

    def __init__(self, storage_dir: str = CHROMA_MEMORY_DIR, collection_name: str = "episodes", in_memory: bool = False):
        if not CHROMADB_AVAILABLE:
            raise RuntimeError("ChromaDB not installed")

        self.storage_dir = storage_dir
        if in_memory:
            self.client = chromadb.Client()
        else:
            self.client = chromadb.PersistentClient(path=storage_dir)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def store(self, event: str, context: str = "") -> dict:
        """Store an episode with automatic embedding."""
        episode_id = f"ep_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        timestamp = datetime.now().isoformat()

        # Combine event and context for better embedding
        full_text = f"{event}. Context: {context}" if context else event

        self.collection.add(
            documents=[full_text],
            ids=[episode_id],
            metadatas=[{
                "event": event[:500],  # Truncate for metadata
                "context": context[:500],
                "timestamp": timestamp
            }]
        )

        return {"id": episode_id, "event": event, "timestamp": timestamp}

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Semantic search - finds meaning, not just keywords."""
        if self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=min(max_results, self.collection.count())
        )

        episodes = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else None

                episodes.append({
                    "event": metadata.get("event", doc[:200]),
                    "context": metadata.get("context", ""),
                    "timestamp": metadata.get("timestamp", "unknown"),
                    "relevance": round(1 - distance, 3) if distance else None
                })

        return episodes


class SemanticMemoryChroma:
    """
    Semantic memory with ChromaDB vector storage.

    Improvement: Can search for facts by meaning.
    "user's coding language" finds facts about "programming preference"
    """

    def __init__(self, storage_dir: str = CHROMA_MEMORY_DIR, collection_name: str = "facts", in_memory: bool = False):
        if not CHROMADB_AVAILABLE:
            raise RuntimeError("ChromaDB not installed")

        self.storage_dir = storage_dir
        if in_memory:
            self.client = chromadb.Client()
        else:
            self.client = chromadb.PersistentClient(path=storage_dir)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def store(self, entity: str, fact_type: str, value: str) -> dict:
        """Store a fact with automatic embedding."""
        fact_id = f"fact_{entity}_{fact_type}".replace(" ", "_").lower()
        timestamp = datetime.now().isoformat()

        # Create searchable document
        document = f"{entity} {fact_type}: {value}"

        # Upsert (update if exists, insert if not)
        try:
            self.collection.delete(ids=[fact_id])
        except Exception:
            pass

        self.collection.add(
            documents=[document],
            ids=[fact_id],
            metadatas=[{
                "entity": entity,
                "fact_type": fact_type,
                "value": value,
                "learned_at": timestamp
            }]
        )

        return {"entity": entity, "fact_type": fact_type, "value": value}

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Semantic search for facts."""
        if self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=min(max_results, self.collection.count())
        )

        facts = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else None

                facts.append({
                    "entity": metadata.get("entity", "unknown"),
                    "fact_type": metadata.get("fact_type", "unknown"),
                    "value": metadata.get("value", doc),
                    "relevance": round(1 - distance, 3) if distance else None
                })

        return facts


# Iteration 2 tools (conditional on ChromaDB)
# Note: Tools use in-memory instances created on demand to avoid filesystem issues
episodic_chroma = None
semantic_chroma = None

def get_chroma_instances():
    """Lazily create ChromaDB instances."""
    global episodic_chroma, semantic_chroma
    if episodic_chroma is None and CHROMADB_AVAILABLE:
        episodic_chroma = EpisodicMemoryChroma(collection_name="tool_episodes", in_memory=True)
        semantic_chroma = SemanticMemoryChroma(collection_name="tool_facts", in_memory=True)
    return episodic_chroma, semantic_chroma


if CHROMADB_AVAILABLE:

    @tool
    def remember_event_chroma(event: str, context: str = "") -> str:
        """
        Store an interaction in episodic memory (ChromaDB, semantic search).
        Use for recording specific events worth remembering.

        Args:
            event: What happened
            context: Additional context

        Returns:
            Confirmation with relevance capability
        """
        ep_store, _ = get_chroma_instances()
        ep = ep_store.store(event, context)
        return f"Remembered (vector): {event[:80]}... (id: {ep['id']})"

    @tool
    def recall_events_chroma(query: str) -> str:
        """
        Search episodic memory using semantic similarity (ChromaDB).
        Finds events by MEANING, not just exact keywords.

        Args:
            query: What to search for (meaning-based)

        Returns:
            Semantically similar past events with relevance scores
        """
        ep_store, _ = get_chroma_instances()
        episodes = ep_store.search(query)
        if not episodes:
            return f"No events found for: {query}"

        results = []
        for e in episodes:
            rel = f" (relevance: {e['relevance']})" if e.get('relevance') else ""
            results.append(f"[{e['timestamp']}]{rel} {e['event'][:200]}")

        return "Past events (semantic):\n" + "\n".join(results)

    @tool
    def learn_fact_chroma(entity: str, fact_type: str, value: str) -> str:
        """
        Store a fact in semantic memory (ChromaDB).

        Args:
            entity: Subject of the fact
            fact_type: Type of fact
            value: The fact value

        Returns:
            Confirmation
        """
        _, sem_store = get_chroma_instances()
        sem_store.store(entity, fact_type, value)
        return f"Learned (vector): {entity} - {fact_type}: {value}"

    @tool
    def recall_facts_chroma(query: str) -> str:
        """
        Search semantic memory using semantic similarity (ChromaDB).
        Finds facts by MEANING - "coding language" finds "programming preference".

        Args:
            query: What to search for

        Returns:
            Semantically similar facts
        """
        _, sem_store = get_chroma_instances()
        facts = sem_store.search(query)
        if not facts:
            return f"No facts found for: {query}"

        results = []
        for f in facts:
            rel = f" (relevance: {f['relevance']})" if f.get('relevance') else ""
            results.append(f"{f['entity']} - {f['fact_type']}: {f['value']}{rel}")

        return "Known facts (semantic):\n" + "\n".join(results)


# =============================================================================
# ITERATION 3: Graphiti Graph Memory (Relationships + Temporal)
# =============================================================================
# Real MCP implementation using Graphiti server at localhost:8000

GRAPHITI_SERVER_URL = "http://localhost:8000/mcp/"


def check_graphiti_available() -> bool:
    """Check if Graphiti MCP server is available via health endpoint."""
    if not MCP_AVAILABLE:
        return False
    try:
        import requests
        response = requests.get("http://localhost:8000/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def graphiti_add_memory(name: str, episode_body: str, group_id: str = GRAPHITI_GROUP_ID) -> dict:
    """
    Add memory to Graphiti graph via MCP.

    Calls: mcp__graphiti-memory__add_memory
    """
    if not MCP_AVAILABLE:
        return {"error": "MCP client not available"}

    if not check_graphiti_available():
        return {"error": "Graphiti server not available"}

    try:
        client = MCPClient(lambda: streamablehttp_client(GRAPHITI_SERVER_URL))
        client.__enter__()

        tool_use_id = f"add-{uuid.uuid4().hex[:8]}"
        result = client.call_tool_sync(
            tool_use_id,
            "add_memory",
            {
                "name": name,
                "episode_body": episode_body,
                "group_id": group_id,
                "source": "text",
                "source_description": f"Level 14 demo: {name}"
            }
        )

        client.__exit__(None, None, None)

        return {
            "status": "stored",
            "name": name,
            "group_id": group_id,
            "result": str(result)
        }

    except Exception as e:
        return {"error": str(e)}


def graphiti_search_facts(query: str, group_ids: list = None) -> list:
    """
    Search Graphiti for facts via MCP.

    Calls: mcp__graphiti-memory__search_memory_facts
    """
    if not MCP_AVAILABLE:
        return [{"error": "MCP client not available"}]

    if not check_graphiti_available():
        return [{"error": "Graphiti server not available"}]

    try:
        client = MCPClient(lambda: streamablehttp_client(GRAPHITI_SERVER_URL))
        client.__enter__()

        tool_use_id = f"search-{uuid.uuid4().hex[:8]}"
        params = {"query": query, "max_facts": 10}
        if group_ids:
            params["group_ids"] = group_ids

        result = client.call_tool_sync(
            tool_use_id,
            "search_memory_facts",
            params
        )

        client.__exit__(None, None, None)

        # Parse result - handle multiple response formats
        import json as json_module

        # Direct dict with content key
        if isinstance(result, dict) and 'content' in result:
            for block in result['content']:
                if isinstance(block, dict) and 'text' in block:
                    data = json_module.loads(block['text'])
                    return data.get("result", {}).get("facts", [])

        # Object with content attribute
        if hasattr(result, 'content'):
            for block in result.content:
                if hasattr(block, 'text'):
                    data = json_module.loads(block.text)
                    return data.get("result", {}).get("facts", [])

        # Try to parse string result
        if isinstance(result, str):
            try:
                data = json_module.loads(result)
                return data.get("result", {}).get("facts", [])
            except:
                pass

        return [{"raw_result": str(result)[:200]}]

    except Exception as e:
        return [{"error": str(e)}]


def graphiti_search_nodes(query: str, group_ids: list = None, max_nodes: int = 10) -> list:
    """
    Search Graphiti for entity nodes via MCP.

    Calls: mcp__graphiti-memory__search_nodes
    """
    if not MCP_AVAILABLE:
        return [{"error": "MCP client not available"}]

    if not check_graphiti_available():
        return [{"error": "Graphiti server not available"}]

    try:
        client = MCPClient(lambda: streamablehttp_client(GRAPHITI_SERVER_URL))
        client.__enter__()

        tool_use_id = f"nodes-{uuid.uuid4().hex[:8]}"
        params = {"query": query, "max_nodes": max_nodes}
        if group_ids:
            params["group_ids"] = group_ids

        result = client.call_tool_sync(
            tool_use_id,
            "search_nodes",
            params
        )

        client.__exit__(None, None, None)

        # Parse result - handle multiple response formats
        import json as json_module

        # Direct dict with content key
        if isinstance(result, dict) and 'content' in result:
            for block in result['content']:
                if isinstance(block, dict) and 'text' in block:
                    data = json_module.loads(block['text'])
                    return data.get("result", {}).get("nodes", [])

        # Object with content attribute
        if hasattr(result, 'content'):
            for block in result.content:
                if hasattr(block, 'text'):
                    data = json_module.loads(block.text)
                    return data.get("result", {}).get("nodes", [])

        # Try to parse string result
        if isinstance(result, str):
            try:
                data = json_module.loads(result)
                return data.get("result", {}).get("nodes", [])
            except:
                pass

        return [{"raw_result": str(result)[:200]}]

    except Exception as e:
        return [{"error": str(e)}]


# =============================================================================
# ITERATION 4: Mem0 Exploration (SOTA Comparison)
# =============================================================================
# Note: Mem0 would require separate installation and setup
# This documents the comparison pattern

MEM0_COMPARISON = """
## Memory System Comparison (SOTA 2025)

| System | Search Type | Key Strength | Token Cost |
|--------|-------------|--------------|------------|
| Local JSON | Keyword | Simple, no deps | Lowest |
| ChromaDB | Vector semantic | Meaning-based | Low |
| Graphiti | Graph + temporal | Relationships | Medium |
| Mem0 | Hybrid vector+graph | 26% accuracy boost | Higher |

### Mem0 Key Insights:
- Hybrid approach: combines vector search with graph relationships
- 26% accuracy improvement over OpenAI memory (research benchmarks)
- 91% lower p95 latency vs full-context approaches
- 90% token cost savings vs maintaining full conversation history

### When to Use Each:
1. JSON: Prototyping, simple apps, minimal dependencies
2. ChromaDB: Semantic search needed, Python-first, <10M vectors
3. Graphiti: Relationship reasoning, temporal facts, FalkorDB
4. Mem0: Production scale, complex reasoning, budget for performance

Sources:
- https://mem0.ai/research
- https://arxiv.org/abs/2504.19413
"""


# =============================================================================
# ITERATION 5: Memory-Augmented Agent
# =============================================================================

def create_memory_agent_json(session_id: str) -> Agent:
    """
    Create agent with JSON-based memory (Iteration 1 pattern).
    Three memory layers: working (session) + episodic + semantic.
    """
    return Agent(
        model=model,
        session_manager=FileSessionManager(
            session_id=session_id,
            storage_dir=SESSION_DIR
        ),
        tools=[
            remember_event_json,
            recall_events_json,
            learn_fact_json,
            recall_facts_json
        ],
        system_prompt="""You are an assistant with long-term memory capabilities.

You have THREE types of memory:

1. WORKING MEMORY (automatic): Current conversation - I naturally remember what we've discussed.

2. EPISODIC MEMORY (remember_event_json / recall_events_json):
   - Stores SPECIFIC EVENTS: "User asked about Python on Dec 10"
   - Use when something notable happens
   - Search: keyword matching

3. SEMANTIC MEMORY (learn_fact_json / recall_facts_json):
   - Stores FACTS: "User prefers Python", "Project uses PostgreSQL"
   - Use when you learn a fact about the user or topic
   - Search: keyword matching

GUIDELINES:
- When user shares a preference, use learn_fact_json to store it
- When something notable happens, use remember_event_json
- At conversation start, use recall_facts_json to check for known info
- Distinguish: events are WHAT HAPPENED, facts are WHAT IS TRUE""",
        callback_handler=None
    )


def create_memory_agent_chroma(session_id: str) -> Agent:
    """
    Create agent with ChromaDB-based memory (Iteration 2 pattern).
    Semantic search for better recall.
    """
    if not CHROMADB_AVAILABLE:
        raise RuntimeError("ChromaDB not available")

    return Agent(
        model=model,
        session_manager=FileSessionManager(
            session_id=session_id,
            storage_dir=SESSION_DIR
        ),
        tools=[
            remember_event_chroma,
            recall_events_chroma,
            learn_fact_chroma,
            recall_facts_chroma
        ],
        system_prompt="""You are an assistant with advanced long-term memory.

You have THREE types of memory:

1. WORKING MEMORY (automatic): Current conversation context.

2. EPISODIC MEMORY (remember_event_chroma / recall_events_chroma):
   - Stores specific events/interactions
   - Semantic search: finds events by MEANING, not just keywords
   - "programming discussion" finds "talked about Python"

3. SEMANTIC MEMORY (learn_fact_chroma / recall_facts_chroma):
   - Stores facts about entities
   - Semantic search: "coding language" finds "programming preference"

GUIDELINES:
- Use semantic memory for user preferences and domain knowledge
- Use episodic memory for notable events and conversations
- Recall tools find related content even with different wording
- The relevance score shows how well results match your query""",
        callback_handler=None
    )


# =============================================================================
# DEMO FUNCTIONS
# =============================================================================

def demo_iteration_1():
    """Demo: JSON memory with keyword search."""
    print("\n" + "=" * 60)
    print("ITERATION 1: Local JSON Memory (Keyword Search)")
    print("=" * 60)

    # Clear previous demo data
    if os.path.exists(LOCAL_MEMORY_DIR):
        shutil.rmtree(LOCAL_MEMORY_DIR)

    # Reinitialize
    global episodic_json, semantic_json
    episodic_json = EpisodicMemoryJSON(group_id="iter1")
    semantic_json = SemanticMemoryJSON(group_id="iter1")

    # Store episodes
    print("\n[Storing episodes...]")
    episodic_json.store("User introduced themselves as Paul", "First conversation")
    episodic_json.store("Discussed Python vs Kotlin for backend", "Tech stack chat")
    episodic_json.store("Helped debug variable shadowing issue", "Debugging session")
    print("  -> 3 episodes stored")

    # Store facts
    print("\n[Storing facts...]")
    semantic_json.store("user", "name", "Paul")
    semantic_json.store("user", "primary_language", "Kotlin")
    semantic_json.store("user", "learning", "AI agents with Strands")
    print("  -> 3 facts stored")

    # Search episodes
    print("\n[Searching episodes for 'Python'...]")
    results = episodic_json.search("Python")
    for r in results:
        print(f"  FOUND: [{r['timestamp'][:10]}] {r['event'][:60]}...")

    # Search for something NOT in keywords
    print("\n[Searching episodes for 'programming'...]")
    results = episodic_json.search("programming")
    if not results:
        print("  NOT FOUND: 'programming' not in any episode keywords")
        print("  (This is a limitation of keyword search)")

    # Search facts
    print("\n[Searching facts for 'user'...]")
    results = semantic_json.search("user")
    for r in results:
        print(f"  FOUND: {r}")

    print("\n[Key Learning: JSON + keyword search is simple but limited]")
    print("- Exact keyword matching only")
    print("- 'programming' won't find 'Python' discussion")
    print("- Good for: simple use cases, no dependencies")


def demo_iteration_2():
    """Demo: ChromaDB memory with semantic search."""
    if not CHROMADB_AVAILABLE:
        print("\n[SKIPPED] Iteration 2 requires ChromaDB: uv add chromadb")
        return

    print("\n" + "=" * 60)
    print("ITERATION 2: ChromaDB Memory (Semantic Search)")
    print("=" * 60)

    # Use in-memory client for demo to avoid filesystem permission issues
    print("\n[Using in-memory ChromaDB for demo...]")

    # Create fresh in-memory instances
    episodic_demo = EpisodicMemoryChroma(collection_name="demo_episodes", in_memory=True)
    semantic_demo = SemanticMemoryChroma(collection_name="demo_facts", in_memory=True)

    # Store same episodes as Iteration 1
    print("\n[Storing episodes (same as Iteration 1)...]")
    episodic_demo.store("User introduced themselves as Paul", "First conversation")
    episodic_demo.store("Discussed Python vs Kotlin for backend", "Tech stack chat")
    episodic_demo.store("Helped debug variable shadowing issue", "Debugging session")
    print("  -> 3 episodes stored with embeddings")

    # Store same facts
    print("\n[Storing facts...]")
    semantic_demo.store("user", "name", "Paul")
    semantic_demo.store("user", "primary_language", "Kotlin")
    semantic_demo.store("user", "learning", "AI agents with Strands")
    print("  -> 3 facts stored with embeddings")

    # Search with exact keyword (should still work)
    print("\n[Searching episodes for 'Python' (exact keyword)...]")
    results = episodic_demo.search("Python")
    for r in results:
        rel = f"(relevance: {r['relevance']})" if r.get('relevance') else ""
        print(f"  FOUND: {rel} {r['event'][:60]}...")

    # Search with semantic meaning (NOT in keywords!)
    print("\n[Searching episodes for 'programming languages' (semantic)...]")
    results = episodic_demo.search("programming languages")
    for r in results:
        rel = f"(relevance: {r['relevance']})" if r.get('relevance') else ""
        print(f"  FOUND: {rel} {r['event'][:60]}...")

    # Another semantic search
    print("\n[Searching for 'code bugs' (semantic)...]")
    results = episodic_demo.search("code bugs")
    for r in results:
        rel = f"(relevance: {r['relevance']})" if r.get('relevance') else ""
        print(f"  FOUND: {rel} {r['event'][:60]}...")

    print("\n[Key Learning: ChromaDB enables MEANING-based search]")
    print("- 'programming languages' finds 'Python vs Kotlin' discussion")
    print("- 'code bugs' finds 'variable shadowing' debugging")
    print("- Embeddings capture semantic similarity")


def demo_iteration_3():
    """Demo: Graphiti graph memory with REAL MCP calls."""
    print("\n" + "=" * 60)
    print("ITERATION 3: Graphiti Graph Memory (REAL MCP)")
    print("=" * 60)

    # Check availability
    print("\n[1. Checking Graphiti availability...]")
    available = check_graphiti_available()
    print(f"  Graphiti available: {available}")

    if not available:
        print("\n  ERROR: Graphiti server not available at localhost:8000")
        print("  Please ensure Docker container 'graphiti-mcp-server' is running.")
        return

    # Store some test memories
    print("\n[2. Storing test memories to Graphiti...]")
    test_memories = [
        ("L14-demo-preference", "User prefers Kotlin over Python for backend development."),
        ("L14-demo-project", "PayrollProject uses PostgreSQL database and Spring WebFlux."),
        ("L14-demo-learning", "Learned that semantic search finds meaning, not just keywords."),
    ]

    for name, body in test_memories:
        result = graphiti_add_memory(name, body, group_id=GRAPHITI_GROUP_ID)
        status = result.get("status", result.get("error", "unknown"))
        print(f"  Stored '{name}': {status}")

    # Search for facts
    print("\n[3. Searching Graphiti for facts...]")
    queries = ["programming language preference", "database technology"]

    for query in queries:
        print(f"\n  Query: '{query}'")
        facts = graphiti_search_facts(query, group_ids=[GRAPHITI_GROUP_ID])
        if facts:
            for i, fact in enumerate(facts[:3], 1):
                if isinstance(fact, dict):
                    if "error" in fact:
                        print(f"    Error: {fact['error']}")
                    elif "fact" in fact:
                        print(f"    {i}. {fact.get('fact', str(fact))[:100]}...")
                    else:
                        print(f"    {i}. {str(fact)[:100]}...")
                else:
                    print(f"    {i}. {str(fact)[:100]}...")
        else:
            print("    No facts found")

    # Search for nodes (entities) - also check benchmark data
    print("\n[4. Searching Graphiti for entity nodes...]")
    print(f"  (Searching in group: {GRAPHITI_GROUP_ID})")

    nodes = graphiti_search_nodes("Kotlin Python programming", group_ids=[GRAPHITI_GROUP_ID], max_nodes=5)
    if nodes and not any("raw_result" in str(n) for n in nodes):
        for i, node in enumerate(nodes[:5], 1):
            if isinstance(node, dict):
                name = node.get("name", "unknown")
                summary = node.get("summary", "")[:60]
                print(f"    {i}. {name}: {summary}...")
            else:
                print(f"    {i}. {str(node)[:80]}...")
    else:
        print("    (Data still processing - Graphiti is async)")
        print("    Tip: Query directly via MCP tools to see results")

    # Summary
    print("\n[5. Comparison: ChromaDB vs Graphiti]")
    print("""
| Capability    | ChromaDB        | Graphiti         |
|---------------|-----------------|------------------|
| Storage       | Vector store    | FalkorDB graph   |
| Semantic      | Yes             | Yes              |
| Relationships | No              | Yes              |
| Temporal      | No              | Yes              |
| Query type    | Similarity      | Graph traversal  |
""")
    print("  NOTE: Graphiti extracts entities and relationships automatically!")
    print("  Low 'recall' doesn't mean failure - it returns structured knowledge.")


def demo_iteration_4():
    """Demo: SOTA comparison with Mem0."""
    print("\n" + "=" * 60)
    print("ITERATION 4: Mem0 SOTA Comparison")
    print("=" * 60)

    print(MEM0_COMPARISON)


def demo_iteration_5():
    """Demo: Memory-augmented agent."""
    print("\n" + "=" * 60)
    print("ITERATION 5: Memory-Augmented Agent")
    print("=" * 60)

    # Clear data
    if os.path.exists(LOCAL_MEMORY_DIR):
        shutil.rmtree(LOCAL_MEMORY_DIR)
    if os.path.exists(SESSION_DIR):
        shutil.rmtree(SESSION_DIR)

    # Reinitialize
    global episodic_json, semantic_json
    episodic_json = EpisodicMemoryJSON(group_id="agent_demo")
    semantic_json = SemanticMemoryJSON(group_id="agent_demo")

    print("\n[Creating memory-augmented agent...]")
    agent = create_memory_agent_json("agent-demo-session")

    print("\n[Turn 1: User shares information]")
    print("-" * 40)
    response = agent("Hi! My name is Alice. I'm a data scientist who loves Python and works on ML projects.")
    print(f"Agent: {response}")

    print("\n[Turn 2: Ask agent to recall]")
    print("-" * 40)
    response = agent("What do you know about me?")
    print(f"Agent: {response}")

    print("\n[Key Pattern: Agent uses memory tools to persist info]")
    print("- learn_fact_json for preferences")
    print("- remember_event_json for notable interactions")
    print("- recall_* tools to retrieve")


def demo_iteration_6():
    """Demo: Cross-session persistence."""
    print("\n" + "=" * 60)
    print("ITERATION 6: Cross-Session Persistence")
    print("=" * 60)

    # Clear previous
    if os.path.exists(LOCAL_MEMORY_DIR):
        shutil.rmtree(LOCAL_MEMORY_DIR)
    if os.path.exists(SESSION_DIR):
        shutil.rmtree(SESSION_DIR)

    # Reinitialize with fresh storage
    global episodic_json, semantic_json
    episodic_json = EpisodicMemoryJSON(group_id="persistence_demo")
    semantic_json = SemanticMemoryJSON(group_id="persistence_demo")

    print("\n[SESSION A: First-time user]")
    print("-" * 40)
    agent_a = create_memory_agent_json("session-A")
    response = agent_a("I'm Bob, a Rust developer. I'm building a CLI tool for DevOps.")
    print(f"Agent A: {response}")

    print("\n[...simulating application restart...]")
    print("(New agent instance, different session ID, but SAME memory storage)")

    print("\n[SESSION B: Returning user (different session)]")
    print("-" * 40)
    # Note: different session_id means different WORKING memory
    # But episodic_json and semantic_json share the same storage
    agent_b = create_memory_agent_json("session-B")
    response = agent_b("Do you remember anything about me or my work?")
    print(f"Agent B: {response}")

    print("\n[Key Learning: Memory layers persist independently]")
    print("- Working memory: per-session (FileSessionManager)")
    print("- Episodic/Semantic: shared storage, survives restarts")
    print("- Different session IDs = different conversations")
    print("- Same memory storage = persistent knowledge")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Level 14: Long-term Memory")
    print("=" * 60)
    print("""
Three Memory Layers:
1. Working: Current conversation (SessionManager)
2. Episodic: Specific events (what happened when)
3. Semantic: Facts/knowledge (what is true)

6 Iterations:
1. Local JSON (keyword search)
2. ChromaDB (semantic search)
3. Graphiti (graph + temporal)
4. Mem0 (SOTA comparison)
5. Memory-Augmented Agent
6. Cross-Session Persistence
""")

    # Run demos
    demo_iteration_1()
    demo_iteration_2()
    demo_iteration_3()
    demo_iteration_4()
    demo_iteration_5()
    demo_iteration_6()

    # Summary
    print("\n" + "=" * 60)
    print("Summary: Memory Search Evolution")
    print("=" * 60)
    print("""
| Iteration | Backend    | Search      | Finds                    |
|-----------|------------|-------------|--------------------------|
| 1         | JSON       | Keyword     | Exact word matches only  |
| 2         | ChromaDB   | Semantic    | Meaning-based similarity |
| 3         | Graphiti   | Graph       | Relationships + temporal |
| 4         | Mem0       | Hybrid      | SOTA accuracy (26% boost)|

Key Patterns:

1. Episodic vs Semantic:
   - Episodic: WHAT happened (events, diary)
   - Semantic: WHAT is true (facts, encyclopedia)

2. Search Evolution:
   - Keyword: Simple, fast, limited
   - Semantic: Meaning-based, requires embeddings
   - Graph: Relationship traversal, temporal validity

3. Three-Layer Architecture:
   - Working: Current session (FileSessionManager)
   - Episodic: Event log (shared storage)
   - Semantic: Fact store (shared storage)

4. Persistence:
   - Working memory: per-session
   - Long-term memory: survives restarts
""")

    # Cleanup
    print("\n[Cleanup...]")
    shutil.rmtree(LOCAL_MEMORY_DIR, ignore_errors=True)
    shutil.rmtree(SESSION_DIR, ignore_errors=True)
    shutil.rmtree(CHROMA_MEMORY_DIR, ignore_errors=True)
    print("Done.")

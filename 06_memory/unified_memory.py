"""
Level 16: Unified Memory Architecture
=====================================
Unified memory system integrating all memory layers from L5, L13, L14, L15
into a cohesive architecture with a simple API.

Four Memory Layers:
1. Working: Current session (FileSessionManager from L5)
2. Episodic: Past events (from L14)
3. Semantic: Facts/knowledge (from L14)
4. Document: RAG knowledge base (from L13)

10 Iterations:
1. Memory Facade - manual routing, MemoryConfig
2. Intelligent Router - auto-classify store/recall
3. Context-Aware Retrieval - multi-layer search with token budget
4. Automatic Compression - 40% rule enforcement
5. Unified Memory Agent - complete tool set
6. Cross-Session Persistence - lifecycle demo
7. Graphiti MCP Integration - REAL MCP calls to graph database
8. Document Memory Layer - RAG integration completing 4-layer architecture
9. NLP Entity Extraction - spaCy-based extraction replacing regex
10. LanceDB Backend - BYOE with local (384-dim) vs API (1536-dim) embedding comparison

Key Concepts:
- Unified facade hides complexity of multiple backends
- Intelligent routing auto-classifies content to correct layer
- Token-budget-aware retrieval prevents context bloat
- Automatic compression maintains quality (40% rule)

Prerequisites:
- LiteLLM proxy running at localhost:4000
- ChromaDB: uv add chromadb
- Graphiti MCP server at localhost:8000 (for Iteration 7)

Run: uv run python 06_memory/unified_memory.py
"""

import sys
import json
import os
import shutil
import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

sys.path.insert(0, ".")

from strands import Agent, tool
from strands.session.file_session_manager import FileSessionManager
from tools import get_model

# Import L14 memory classes
from longterm_memory import (
    EpisodicMemoryJSON,
    SemanticMemoryJSON,
    EpisodicMemoryChroma,
    SemanticMemoryChroma,
    CHROMADB_AVAILABLE,
)

# Import L15 context management
from context_management import (
    TokenBudget,
    RollingSummarizer,
    HierarchicalSummarizer,
    MODEL_LIMITS,
    TARGET_UTILIZATION,
)

# =============================================================================
# Configuration
# =============================================================================

UNIFIED_SESSION_DIR = "./unified_sessions"
UNIFIED_MEMORY_DIR = "./unified_memory"
UNIFIED_CHROMA_DIR = "./unified_chroma"
DEFAULT_GROUP_ID = "unified-default"

# Default model for operations
model = get_model("claude-sonnet-4")


# =============================================================================
# ITERATION 1: Memory Facade with Manual Routing
# =============================================================================


@dataclass
class MemoryConfig:
    """
    Configuration for the unified memory system.

    Plain English: All the knobs to configure how memory works.

    Attributes:
        session_id: Unique identifier for the current session (working memory)
        session_dir: Directory for session storage
        ltm_backend: Backend for long-term memory ("chromadb" or "json")
        ltm_storage_dir: Directory for long-term memory files
        group_id: Group identifier for memory isolation
        target_utilization: Context window target (40% = Horthy rule)
        model_id: Model for main operations
        compression_model: Model for summarization (use cheaper model)
        default_budget_tokens: Default token budget for retrieval
        episodic_weight: Weight for episodic results in recall
        semantic_weight: Weight for semantic results in recall
        document_weight: Weight for document results in recall
    """
    session_id: str = "default"
    session_dir: str = UNIFIED_SESSION_DIR
    ltm_backend: str = "chromadb"  # "chromadb" or "json"
    ltm_storage_dir: str = UNIFIED_MEMORY_DIR
    chroma_storage_dir: str = UNIFIED_CHROMA_DIR
    group_id: str = DEFAULT_GROUP_ID
    target_utilization: float = TARGET_UTILIZATION
    model_id: str = "claude-sonnet-4"
    compression_model: str = "claude-3-5-haiku"
    default_budget_tokens: int = 2000
    episodic_weight: float = 0.30
    semantic_weight: float = 0.40
    document_weight: float = 0.30


class UnifiedMemoryV1:
    """
    Iteration 1: Memory Facade with Manual Routing.

    Plain English: Single interface to store/recall from any memory layer.
    You explicitly specify which layer to use.

    Pseudocode:
        memory = UnifiedMemoryV1(config)
        memory.store("User likes Python", layer="semantic")
        memory.recall("Python", layer="semantic")
    """

    def __init__(self, config: MemoryConfig = None):
        self.config = config or MemoryConfig()
        self._init_storage()

    def _init_storage(self):
        """Initialize storage backends based on config."""
        # Working memory (session)
        os.makedirs(self.config.session_dir, exist_ok=True)
        self.session_manager = FileSessionManager(
            session_id=self.config.session_id,
            storage_dir=self.config.session_dir
        )

        # Long-term memory (episodic + semantic)
        if self.config.ltm_backend == "chromadb" and CHROMADB_AVAILABLE:
            os.makedirs(self.config.chroma_storage_dir, exist_ok=True)
            self.episodic = EpisodicMemoryChroma(
                storage_dir=self.config.chroma_storage_dir,
                collection_name=f"{self.config.group_id}_episodes",
                in_memory=False
            )
            self.semantic = SemanticMemoryChroma(
                storage_dir=self.config.chroma_storage_dir,
                collection_name=f"{self.config.group_id}_facts",
                in_memory=False
            )
            self.backend_type = "chromadb"
        else:
            os.makedirs(self.config.ltm_storage_dir, exist_ok=True)
            self.episodic = EpisodicMemoryJSON(
                storage_dir=self.config.ltm_storage_dir,
                group_id=self.config.group_id
            )
            self.semantic = SemanticMemoryJSON(
                storage_dir=self.config.ltm_storage_dir,
                group_id=self.config.group_id
            )
            self.backend_type = "json"

        # Token budget tracker
        self.budget = TokenBudget(
            model_id=self.config.model_id,
            target_utilization=self.config.target_utilization
        )

    def store(self, content: str, layer: str, **kwargs) -> dict:
        """
        Store content in the specified memory layer.

        Args:
            content: Content to store
            layer: "episodic", "semantic", or "working"
            **kwargs: Layer-specific arguments
                - episodic: context (str)
                - semantic: entity (str), fact_type (str) - content becomes value

        Returns:
            dict with storage result
        """
        if layer == "episodic":
            context = kwargs.get("context", "")
            result = self.episodic.store(content, context)
            return {"layer": "episodic", "stored": result}

        elif layer == "semantic":
            entity = kwargs.get("entity", "general")
            fact_type = kwargs.get("fact_type", "fact")
            result = self.semantic.store(entity, fact_type, content)
            return {"layer": "semantic", "stored": result}

        elif layer == "working":
            # Working memory is managed by session_manager automatically
            # This is just for explicit storage needs
            return {"layer": "working", "note": "Working memory is automatic via session"}

        else:
            raise ValueError(f"Unknown layer: {layer}. Use 'episodic', 'semantic', or 'working'")

    def recall(self, query: str, layer: str, max_results: int = 5) -> list[dict]:
        """
        Recall content from the specified memory layer.

        Args:
            query: Search query
            layer: "episodic" or "semantic"
            max_results: Maximum number of results

        Returns:
            List of matching items
        """
        if layer == "episodic":
            return self.episodic.search(query, max_results)

        elif layer == "semantic":
            return self.semantic.search(query)[:max_results]

        else:
            raise ValueError(f"Unknown layer: {layer}. Use 'episodic' or 'semantic'")

    def get_stats(self) -> dict:
        """Get memory system statistics."""
        return {
            "backend": self.backend_type,
            "session_id": self.config.session_id,
            "group_id": self.config.group_id,
        }


# Iteration 1 tools (manual routing)
_memory_v1: Optional[UnifiedMemoryV1] = None


def get_memory_v1() -> UnifiedMemoryV1:
    """Get or create the V1 memory instance."""
    global _memory_v1
    if _memory_v1 is None:
        _memory_v1 = UnifiedMemoryV1()
    return _memory_v1


@tool
def store_memory_v1(content: str, layer: str, entity: str = "", fact_type: str = "", context: str = "") -> str:
    """
    Store content in a specific memory layer (manual routing).

    Args:
        content: The content to store
        layer: Memory layer - "episodic" for events, "semantic" for facts
        entity: (semantic only) Subject of the fact, e.g., "user", "project"
        fact_type: (semantic only) Type of fact, e.g., "preference", "skill"
        context: (episodic only) Additional context about the event

    Returns:
        Confirmation of storage
    """
    memory = get_memory_v1()

    if layer == "episodic":
        result = memory.store(content, layer="episodic", context=context)
        return f"Stored in EPISODIC memory: {content[:80]}..."

    elif layer == "semantic":
        entity = entity or "general"
        fact_type = fact_type or "fact"
        result = memory.store(content, layer="semantic", entity=entity, fact_type=fact_type)
        return f"Stored in SEMANTIC memory: {entity}.{fact_type} = {content[:60]}..."

    else:
        return f"Error: Unknown layer '{layer}'. Use 'episodic' or 'semantic'."


@tool
def recall_memory_v1(query: str, layer: str) -> str:
    """
    Recall content from a specific memory layer (manual routing).

    Args:
        query: Search query
        layer: Memory layer to search - "episodic" or "semantic"

    Returns:
        Matching memories formatted as text
    """
    memory = get_memory_v1()
    results = memory.recall(query, layer=layer)

    if not results:
        return f"No results found in {layer} memory for: {query}"

    if layer == "episodic":
        formatted = [f"[{r.get('timestamp', '?')[:10]}] {r.get('event', '')[:100]}" for r in results]
        return f"EPISODIC memories ({len(results)} found):\n" + "\n".join(formatted)

    elif layer == "semantic":
        formatted = []
        for r in results:
            if "entity" in r:
                formatted.append(f"{r.get('entity', '?')}.{r.get('fact_type', '?')} = {r.get('value', '')}")
            else:
                formatted.append(str(r)[:100])
        return f"SEMANTIC facts ({len(results)} found):\n" + "\n".join(formatted)

    return f"Results from {layer}:\n" + json.dumps(results, indent=2)[:500]


# =============================================================================
# ITERATION 2: Intelligent Memory Router
# =============================================================================


class MemoryRouter:
    """
    Intelligent routing of content to appropriate memory layer.

    Plain English: Automatically determines WHERE to store content based on patterns.
    "User prefers Python" -> semantic (it's a fact)
    "We discussed the bug fix" -> episodic (it's an event)

    Pseudocode:
        router = MemoryRouter()
        layer, confidence = router.classify_store("User prefers Python")
        # -> ("semantic", 0.85)
    """

    # Patterns that suggest EPISODIC memory (events, interactions)
    EPISODIC_PATTERNS = [
        r"\b(happened|occurred|discussed|talked|met|saw|heard)\b",
        r"\b(yesterday|today|earlier|last week|just now)\b",
        r"\b(we|they|user|i)\s+(asked|said|mentioned|shared|told)\b",
        r"\b(meeting|conversation|discussion|session|call)\b",
        r"^\[.*\]",  # Timestamp-like patterns
    ]

    # Patterns that suggest SEMANTIC memory (facts, knowledge)
    SEMANTIC_PATTERNS = [
        r"\b(is|are|prefers?|likes?|uses?|works?\s+with|knows?)\b",
        r"\b(always|never|usually|typically|generally)\b",
        r"\b(name|preference|skill|role|location|language)\b",
        r"\b(fact|true|false|definition|meaning)\b",
        r":\s*",  # Key-value like patterns
    ]

    def __init__(self):
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for efficiency."""
        self.episodic_re = [re.compile(p, re.IGNORECASE) for p in self.EPISODIC_PATTERNS]
        self.semantic_re = [re.compile(p, re.IGNORECASE) for p in self.SEMANTIC_PATTERNS]

    def classify_store(self, content: str) -> tuple[str, float]:
        """
        Classify content for storage.

        Args:
            content: The content to classify

        Returns:
            (layer, confidence) tuple
        """
        episodic_score = sum(1 for p in self.episodic_re if p.search(content))
        semantic_score = sum(1 for p in self.semantic_re if p.search(content))

        total = episodic_score + semantic_score
        if total == 0:
            # Default to semantic for standalone facts
            return ("semantic", 0.5)

        if episodic_score > semantic_score:
            confidence = episodic_score / total
            return ("episodic", round(confidence, 2))
        else:
            confidence = semantic_score / total
            return ("semantic", round(confidence, 2))

    def classify_query(self, query: str) -> list[str]:
        """
        Classify a query to determine which layers to search.

        Args:
            query: The search query

        Returns:
            List of layers to search, ordered by relevance
        """
        episodic_score = sum(1 for p in self.episodic_re if p.search(query))
        semantic_score = sum(1 for p in self.semantic_re if p.search(query))

        # Default to searching both
        if episodic_score == semantic_score:
            return ["semantic", "episodic"]
        elif episodic_score > semantic_score:
            return ["episodic", "semantic"]
        else:
            return ["semantic", "episodic"]

    def extract_entity_fact(self, content: str) -> tuple[str, str, str]:
        """
        Extract entity, fact_type, and value from content.

        Patterns recognized:
        - "User prefers Python" -> (user, preference, Python)
        - "Project uses PostgreSQL" -> (project, technology, PostgreSQL)
        - "Name is Alice" -> (user, name, Alice)

        Returns:
            (entity, fact_type, value) tuple
        """
        content_lower = content.lower()

        # Pattern: "X prefers/likes Y"
        match = re.search(r"(\w+)\s+(prefers?|likes?)\s+(.+)", content, re.IGNORECASE)
        if match:
            return (match.group(1).lower(), "preference", match.group(3).strip())

        # Pattern: "X uses/works with Y"
        match = re.search(r"(\w+)\s+(uses?|works?\s+with)\s+(.+)", content, re.IGNORECASE)
        if match:
            return (match.group(1).lower(), "technology", match.group(3).strip())

        # Pattern: "X is Y" (name is, role is, etc.)
        match = re.search(r"(\w+)\s+is\s+(.+)", content, re.IGNORECASE)
        if match:
            subject = match.group(1).lower()
            if subject in ["name", "my name", "their name"]:
                return ("user", "name", match.group(2).strip())
            return (subject, "value", match.group(2).strip())

        # Pattern: "X: Y" (key-value)
        match = re.search(r"(\w+):\s*(.+)", content)
        if match:
            return ("general", match.group(1).lower(), match.group(2).strip())

        # Default
        return ("general", "fact", content)


class UnifiedMemoryV2(UnifiedMemoryV1):
    """
    Iteration 2: Memory with Intelligent Routing.

    Plain English: Automatically routes content to the right layer.
    You can still override with explicit layer parameter.
    """

    def __init__(self, config: MemoryConfig = None):
        super().__init__(config)
        self.router = MemoryRouter()

    def store_auto(self, content: str, **kwargs) -> dict:
        """
        Store content with automatic layer classification.

        Args:
            content: Content to store
            **kwargs: Optional overrides

        Returns:
            dict with layer, confidence, and storage result
        """
        layer, confidence = self.router.classify_store(content)

        if layer == "semantic":
            entity, fact_type, value = self.router.extract_entity_fact(content)
            result = self.store(value, layer="semantic", entity=entity, fact_type=fact_type)
        else:
            result = self.store(content, layer="episodic", context=kwargs.get("context", ""))

        return {
            "layer": layer,
            "confidence": confidence,
            "result": result
        }

    def recall_auto(self, query: str, max_results: int = 5) -> dict:
        """
        Recall with automatic layer selection.

        Args:
            query: Search query
            max_results: Maximum results per layer

        Returns:
            dict with results from relevant layers
        """
        layers = self.router.classify_query(query)

        results = {
            "query": query,
            "layers_searched": layers,
            "episodic": [],
            "semantic": []
        }

        for layer in layers:
            layer_results = self.recall(query, layer=layer, max_results=max_results)
            results[layer] = layer_results

        return results


# Iteration 2 tools (auto-routing)
_memory_v2: Optional[UnifiedMemoryV2] = None


def get_memory_v2() -> UnifiedMemoryV2:
    """Get or create the V2 memory instance."""
    global _memory_v2
    if _memory_v2 is None:
        _memory_v2 = UnifiedMemoryV2()
    return _memory_v2


@tool
def remember(content: str) -> str:
    """
    Store information in long-term memory with automatic routing.

    Automatically determines whether content is:
    - An EVENT (episodic): "We discussed the Python migration"
    - A FACT (semantic): "User prefers dark mode"

    Use this when you want the system to decide where to store.

    Args:
        content: The information to remember

    Returns:
        Confirmation with layer and confidence
    """
    memory = get_memory_v2()
    result = memory.store_auto(content)

    layer = result["layer"].upper()
    conf = result["confidence"]

    return f"Remembered in {layer} memory (confidence: {conf:.0%}): {content[:80]}..."


@tool
def recall(query: str, max_results: int = 5) -> str:
    """
    Search all memory layers for relevant information.

    Automatically searches both episodic (events) and semantic (facts) memory,
    prioritizing layers based on query type.

    Args:
        query: What to search for
        max_results: Maximum results per layer (default: 5)

    Returns:
        Combined results from all relevant layers
    """
    memory = get_memory_v2()
    results = memory.recall_auto(query, max_results)

    output_parts = [f"Search: '{query}'", f"Layers: {', '.join(results['layers_searched'])}"]

    if results["episodic"]:
        eps = [f"  [{r.get('timestamp', '?')[:10]}] {r.get('event', '')[:80]}" for r in results["episodic"]]
        output_parts.append("EPISODIC (events):\n" + "\n".join(eps))

    if results["semantic"]:
        facts = [f"  {r.get('entity', '?')}.{r.get('fact_type', '?')} = {r.get('value', '')}" for r in results["semantic"]]
        output_parts.append("SEMANTIC (facts):\n" + "\n".join(facts))

    if not results["episodic"] and not results["semantic"]:
        output_parts.append("No memories found.")

    return "\n\n".join(output_parts)


# =============================================================================
# ITERATION 3: Context-Aware Retrieval
# =============================================================================


class UnifiedMemoryV3(UnifiedMemoryV2):
    """
    Iteration 3: Context-Aware Retrieval with Token Budget.

    Plain English: Retrieve from all layers, merge results, stay within token budget.
    Uses importance scoring: score = relevance * recency
    Formats as XML for token efficiency.
    """

    def __init__(self, config: MemoryConfig = None):
        super().__init__(config)

    def _importance_score(self, item: dict, query: str) -> float:
        """Calculate importance score for ranking results."""
        # Relevance: keyword overlap
        query_words = set(query.lower().split())
        item_text = str(item.get("event", "") or item.get("value", "")).lower()
        item_words = set(item_text.split())

        overlap = len(query_words & item_words)
        relevance = overlap / len(query_words) if query_words else 0.0

        # Use embedding relevance if available (ChromaDB)
        if "relevance" in item:
            relevance = max(relevance, item["relevance"])

        # Recency decay (24-hour half-life)
        timestamp = item.get("timestamp", "")
        if timestamp:
            try:
                age_hours = (datetime.now() - datetime.fromisoformat(timestamp)).total_seconds() / 3600
                recency = 1.0 / (1.0 + age_hours / 24)
            except Exception:
                recency = 0.5
        else:
            recency = 0.5

        return relevance * recency

    def recall_with_budget(self, query: str, budget_tokens: int = None) -> tuple[str, dict]:
        """
        Retrieve context from all layers within token budget.

        Args:
            query: Search query
            budget_tokens: Max tokens to return (default from config)

        Returns:
            (xml_formatted_context, stats_dict)
        """
        budget_tokens = budget_tokens or self.config.default_budget_tokens

        # Allocate budget by weights
        episodic_budget = int(budget_tokens * self.config.episodic_weight)
        semantic_budget = int(budget_tokens * self.config.semantic_weight)
        # document_budget = int(budget_tokens * self.config.document_weight)  # Future

        # Search all layers
        episodic_results = self.recall(query, layer="episodic", max_results=10)
        semantic_results = self.recall(query, layer="semantic", max_results=10)

        # Score and tag results
        all_candidates = []

        for item in episodic_results:
            item["_type"] = "episodic"
            item["_score"] = self._importance_score(item, query)
            all_candidates.append(item)

        for item in semantic_results:
            item["_type"] = "semantic"
            item["_score"] = self._importance_score(item, query)
            all_candidates.append(item)

        # Sort by score
        all_candidates.sort(key=lambda x: x.get("_score", 0), reverse=True)

        # Select within budget
        selected_episodic = []
        selected_semantic = []
        tokens_used = {"episodic": 0, "semantic": 0}

        for item in all_candidates:
            item_text = json.dumps(item)
            item_tokens = self.budget.count(item_text)

            if item["_type"] == "episodic" and tokens_used["episodic"] + item_tokens <= episodic_budget:
                selected_episodic.append(item)
                tokens_used["episodic"] += item_tokens
            elif item["_type"] == "semantic" and tokens_used["semantic"] + item_tokens <= semantic_budget:
                selected_semantic.append(item)
                tokens_used["semantic"] += item_tokens

        # Format as XML
        xml_parts = []

        if selected_episodic:
            eps = "\n".join(f"  - [{e.get('timestamp', '?')[:10]}] {e.get('event', '')[:100]}" for e in selected_episodic)
            xml_parts.append(f"<past_events>\n{eps}\n</past_events>")

        if selected_semantic:
            facts = "\n".join(f"  - {f.get('entity', '?')}.{f.get('fact_type', '?')}: {f.get('value', '')}" for f in selected_semantic)
            xml_parts.append(f"<known_facts>\n{facts}\n</known_facts>")

        if not xml_parts:
            xml_output = "<retrieved_context>No relevant memories found.</retrieved_context>"
        else:
            xml_output = "\n\n".join(xml_parts)

        stats = {
            "query": query,
            "budget_tokens": budget_tokens,
            "candidates": len(all_candidates),
            "selected": len(selected_episodic) + len(selected_semantic),
            "tokens_used": sum(tokens_used.values()),
            "episodic_count": len(selected_episodic),
            "semantic_count": len(selected_semantic),
        }

        return xml_output, stats


# Iteration 3 tools
_memory_v3: Optional[UnifiedMemoryV3] = None


def get_memory_v3() -> UnifiedMemoryV3:
    """Get or create the V3 memory instance."""
    global _memory_v3
    if _memory_v3 is None:
        _memory_v3 = UnifiedMemoryV3()
    return _memory_v3


@tool
def recall_with_budget(query: str, max_tokens: int = 2000) -> str:
    """
    Search all memory layers within a token budget.

    Uses importance scoring (relevance * recency) to select the most
    valuable context that fits within the token limit.
    Returns XML-formatted context for efficiency.

    Args:
        query: What to search for
        max_tokens: Maximum tokens to return (default: 2000)

    Returns:
        XML-formatted context with retrieval stats
    """
    memory = get_memory_v3()
    context, stats = memory.recall_with_budget(query, max_tokens)

    return f"""Retrieval Stats:
- Candidates: {stats['candidates']}
- Selected: {stats['selected']} (episodic: {stats['episodic_count']}, semantic: {stats['semantic_count']})
- Tokens: {stats['tokens_used']} / {stats['budget_tokens']}

{context}"""


# =============================================================================
# ITERATION 4: Automatic Context Compression
# =============================================================================


class UnifiedMemoryV4(UnifiedMemoryV3):
    """
    Iteration 4: Automatic Compression (40% Rule).

    Plain English: Monitors context window and auto-compresses when needed.
    When utilization > 40%, applies compression and extracts key facts to semantic memory.
    """

    def __init__(self, config: MemoryConfig = None):
        super().__init__(config)
        self.compressor = HierarchicalSummarizer(config.compression_model if config else "claude-3-5-haiku")
        self._compression_count = 0

    def check_utilization(self, messages: list[dict]) -> dict:
        """
        Check current context utilization.

        Args:
            messages: List of conversation messages

        Returns:
            Status dict with utilization, zone, recommendation
        """
        status = self.budget.utilization_status(messages)

        if status["zone"] == "optimal":
            status["recommendation"] = "Context is healthy. No action needed."
        elif status["zone"] == "warning":
            status["recommendation"] = "Approaching 40%. Consider compressing older context."
        else:
            status["recommendation"] = "IN DUMB ZONE! Compress immediately."

        return status

    def should_compress(self, messages: list[dict]) -> bool:
        """Check if compression is recommended."""
        return self.budget.should_compress(messages)

    def compress_and_extract(self, messages: list[str]) -> tuple[str, dict]:
        """
        Compress messages and extract key facts to semantic memory.

        Args:
            messages: List of message strings

        Returns:
            (compressed_context, stats)
        """
        # Compress using hierarchical summarizer
        compressed, stats = self.compressor.compress(messages)

        # Extract key facts from compressed content
        # (In production, this would use NLP to extract entities/facts)
        self._compression_count += 1

        stats["compression_number"] = self._compression_count
        stats["facts_extracted"] = 0  # Placeholder for actual extraction

        return compressed, stats

    def auto_compress_if_needed(self, messages: list[dict]) -> tuple[bool, Optional[str], dict]:
        """
        Automatically compress if utilization exceeds threshold.

        Args:
            messages: List of conversation messages

        Returns:
            (compressed, compressed_content, stats)
        """
        if not self.should_compress(messages):
            return False, None, {"compressed": False, "reason": "Below threshold"}

        # Extract text content
        message_texts = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                message_texts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        message_texts.append(part["text"])

        compressed, stats = self.compress_and_extract(message_texts)
        stats["compressed"] = True

        return True, compressed, stats


# Iteration 4 tools
_memory_v4: Optional[UnifiedMemoryV4] = None


def get_memory_v4() -> UnifiedMemoryV4:
    """Get or create the V4 memory instance."""
    global _memory_v4
    if _memory_v4 is None:
        _memory_v4 = UnifiedMemoryV4()
    return _memory_v4


@tool
def check_memory_status() -> str:
    """
    Check current memory system status and context utilization.

    Shows:
    - Context window utilization (working memory)
    - Zone (optimal/warning/dumb_zone)
    - Long-term memory stats
    - Recommendation

    Returns:
        Detailed status report
    """
    memory = get_memory_v4()

    # Simulate some messages for demo
    # In real use, would get from session_manager
    sample_messages = [{"content": "Sample conversation context for status check."}]
    status = memory.check_utilization(sample_messages)

    return f"""Memory System Status:

<working_memory>
  Tokens: {status['tokens']:,} / {status['max_tokens']:,}
  Utilization: {status['utilization']}%
  Target: <{status['target']}%
  Zone: {status['zone'].upper()}
</working_memory>

<long_term_memory>
  Backend: {memory.backend_type}
  Group: {memory.config.group_id}
</long_term_memory>

Recommendation: {status['recommendation']}"""


@tool
def compress_context(conversation_history: str) -> str:
    """
    Compress conversation history using hierarchical summarization.

    Applies age-based compression:
    - Recent (<10 turns): Verbatim
    - Medium (10-30 turns): Paragraph summaries
    - Old (>30 turns): Key facts only

    Args:
        conversation_history: Full conversation as text

    Returns:
        Compressed context with stats
    """
    memory = get_memory_v4()
    messages = conversation_history.strip().split("\n\n")

    compressed, stats = memory.compress_and_extract(messages)

    levels = stats.get("levels", {})
    level_info = ", ".join(f"{k}: {v}" for k, v in levels.items())

    return f"""Compression Complete:
- Original: {len(messages)} messages
- Levels: {level_info}
- Ratio: {stats.get('ratio', 1.0)}
- Compression #{stats.get('compression_number', 1)}

{compressed}"""


# =============================================================================
# ITERATION 5: Unified Memory Agent
# =============================================================================

UNIFIED_MEMORY_PROMPT = """You are an assistant with a sophisticated unified memory system.

## YOUR MEMORY ARCHITECTURE

You have FOUR types of memory:

1. **WORKING MEMORY** (automatic)
   - Current conversation - tracked automatically
   - Limited capacity - follows the 40% rule
   - Check with: check_memory_status()

2. **EPISODIC MEMORY** (events)
   - Stores WHAT HAPPENED: meetings, discussions, interactions
   - Cross-session: survives after conversation ends
   - Auto-routed with: remember()
   - Explicit: store_event()

3. **SEMANTIC MEMORY** (facts)
   - Stores WHAT IS TRUE: preferences, knowledge, relationships
   - Cross-session: persists permanently
   - Auto-routed with: remember()
   - Explicit: store_fact()

4. **DOCUMENT MEMORY** (knowledge base)
   - For reference materials, uploaded docs
   - Searchable with: search_documents() (if available)

## MEMORY TOOLS

### Auto-Routed (Recommended):
- **remember(content)**: Auto-routes to episodic or semantic
- **recall(query)**: Searches all layers
- **recall_with_budget(query, max_tokens)**: Budget-aware retrieval

### Explicit (Power User):
- **store_event(event, context)**: Force episodic storage
- **store_fact(entity, fact_type, value)**: Force semantic storage

### Context Management:
- **check_memory_status()**: View utilization
- **compress_context(history)**: Compress older context

## GUIDELINES

### When to STORE:
- User shares a preference -> remember() (auto-routes to semantic)
- Something notable happens -> remember() (auto-routes to episodic)
- Need precise control -> use explicit store_event() or store_fact()

### When to RECALL:
- Start of conversation -> recall("user preferences")
- User asks about past -> recall("relevant topic")
- Token-conscious -> recall_with_budget("query", 1500)

### Context Management (40% Rule):
- Periodically check with check_memory_status()
- If utilization > 40%, use compress_context()
- Quality degrades in "Dumb Zone" (>60%)
- Compress proactively, not reactively

## DECISION GUIDE

| Content Type | Where | Tool |
|--------------|-------|------|
| "User prefers X" | Semantic | remember() |
| "We discussed X" | Episodic | remember() |
| "User's name is X" | Semantic | store_fact("user", "name", "X") |
| Task context | Working | (automatic) |
"""


def create_unified_memory_agent(config: MemoryConfig = None) -> Agent:
    """
    Create an agent with full unified memory capabilities.

    Args:
        config: Memory configuration (optional)

    Returns:
        Agent with memory tools and system prompt
    """
    config = config or MemoryConfig()

    # Initialize memory system
    global _memory_v4
    _memory_v4 = UnifiedMemoryV4(config)

    return Agent(
        model=get_model(config.model_id),
        session_manager=_memory_v4.session_manager,
        tools=[
            # Auto-routed
            remember,
            recall,
            recall_with_budget,
            # Explicit
            store_event,
            store_fact,
            # Context management
            check_memory_status,
            compress_context,
        ],
        system_prompt=UNIFIED_MEMORY_PROMPT,
        callback_handler=None
    )


# Iteration 5 explicit tools
@tool
def store_event(event: str, context: str = "") -> str:
    """
    Explicitly store an event in EPISODIC memory.

    Use when you want to force storage as an event, not a fact.

    Args:
        event: What happened
        context: Additional context about the situation

    Returns:
        Confirmation
    """
    memory = get_memory_v4()
    result = memory.store(event, layer="episodic", context=context)
    return f"Stored EVENT: {event[:80]}..."


@tool
def store_fact(entity: str, fact_type: str, value: str) -> str:
    """
    Explicitly store a fact in SEMANTIC memory.

    Use when you want precise control over how a fact is stored.

    Args:
        entity: Subject (e.g., "user", "project", "Python")
        fact_type: Type of fact (e.g., "preference", "skill", "uses")
        value: The fact value

    Returns:
        Confirmation
    """
    memory = get_memory_v4()
    result = memory.store(value, layer="semantic", entity=entity, fact_type=fact_type)
    return f"Stored FACT: {entity}.{fact_type} = {value}"


# =============================================================================
# ITERATION 6: Cross-Session Persistence Demo
# =============================================================================


def demo_cross_session():
    """
    Demo: Cross-session memory persistence.

    Session A: User shares information
    Session B: Different session_id, but recalls from shared long-term memory
    """
    # Shared config (same group_id, same storage)
    base_config = MemoryConfig(
        ltm_backend="json",  # Use JSON for demo (no ChromaDB needed)
        group_id="cross-session-demo",
        ltm_storage_dir="./demo_memory"
    )

    # Clean previous demo
    if os.path.exists(base_config.ltm_storage_dir):
        shutil.rmtree(base_config.ltm_storage_dir)
    if os.path.exists(base_config.session_dir):
        shutil.rmtree(base_config.session_dir)

    print("\n[SESSION A: First-time user]")
    print("-" * 40)

    config_a = MemoryConfig(
        session_id="session-A",
        ltm_backend="json",
        group_id="cross-session-demo",
        ltm_storage_dir="./demo_memory"
    )
    agent_a = create_unified_memory_agent(config_a)

    response_a = agent_a("Hi! My name is Alice and I'm a machine learning engineer. I work with Python and PyTorch mostly. Please remember this about me.")
    print(f"Agent A response:\n{response_a}")

    print("\n[...simulating application restart...]")
    print("(New session ID, but same memory storage)")

    print("\n[SESSION B: Returning user (different session)]")
    print("-" * 40)

    config_b = MemoryConfig(
        session_id="session-B",  # Different session!
        ltm_backend="json",
        group_id="cross-session-demo",  # Same group = same memory
        ltm_storage_dir="./demo_memory"
    )
    agent_b = create_unified_memory_agent(config_b)

    response_b = agent_b("What do you know about me from previous conversations? Please recall any information you have.")
    print(f"Agent B response:\n{response_b}")

    print("\n[Key Learning: Memory persists across sessions]")
    print("- Working memory: per-session (different for A and B)")
    print("- Long-term memory: shared via group_id")
    print("- Different session_id = fresh conversation context")
    print("- Same group_id = shared facts and events")

    # Cleanup
    shutil.rmtree(base_config.ltm_storage_dir, ignore_errors=True)
    shutil.rmtree(base_config.session_dir, ignore_errors=True)


# =============================================================================
# ITERATION 7: Graphiti MCP Integration (REAL CALLS)
# =============================================================================

# Import MCP client for Graphiti
try:
    from strands.tools.mcp import MCPClient
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


class GraphitiMemoryAdapter:
    """
    Adapter for Graphiti MCP memory operations using ACTUAL MCP calls.

    Connects to the running Graphiti MCP server at localhost:8000.
    """

    def __init__(self, group_id: str = "level16-graphiti-demo", server_url: str = "http://localhost:8000"):
        self.group_id = group_id
        self.server_url = server_url
        self.mcp_client = None
        self.tools = {}
        self._connected = False

    def connect(self) -> bool:
        """Connect to Graphiti MCP server via Streamable HTTP."""
        if not MCP_AVAILABLE:
            print("  [!] MCP client not available")
            return False

        try:
            # Connect to running Graphiti MCP server via Streamable HTTP at /mcp endpoint
            self.mcp_client = MCPClient(
                lambda: streamablehttp_client(f"{self.server_url}/mcp")
            )

            self.mcp_client.__enter__()
            tool_list = self.mcp_client.list_tools_sync()
            self.tools = {t.tool_name: t for t in tool_list}
            self._connected = True

            print(f"  [✓] Connected to Graphiti MCP at {self.server_url}")
            print(f"  [✓] Available tools: {list(self.tools.keys())}")
            return True

        except Exception as e:
            print(f"  [!] Failed to connect: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from Graphiti MCP server."""
        if self.mcp_client and self._connected:
            try:
                self.mcp_client.__exit__(None, None, None)
            except Exception:
                pass
            self._connected = False

    def store(self, name: str, content: str, source: str = "unified-memory") -> dict:
        """Store memory via Graphiti MCP."""
        if not self._connected:
            return {"error": "Not connected"}

        try:
            import uuid
            tool_use_id = f"store-{uuid.uuid4().hex[:8]}"
            result = self.mcp_client.call_tool_sync(
                tool_use_id,
                "add_memory",
                {
                    "name": name,
                    "episode_body": content,
                    "group_id": self.group_id,
                    "source": "text",
                    "source_description": source
                }
            )
            return {"status": "stored", "name": name, "result": str(result)}
        except Exception as e:
            return {"error": str(e)}

    def search_facts(self, query: str, max_facts: int = 10) -> list[dict]:
        """Search facts via Graphiti MCP."""
        if not self._connected:
            return [{"error": "Not connected"}]

        try:
            import uuid
            tool_use_id = f"search-facts-{uuid.uuid4().hex[:8]}"
            result = self.mcp_client.call_tool_sync(
                tool_use_id,
                "search_memory_facts",
                {"query": query, "group_ids": [self.group_id], "max_facts": max_facts}
            )
            return [{"facts": str(result)}]
        except Exception as e:
            return [{"error": str(e)}]

    def search_nodes(self, query: str, max_nodes: int = 10) -> list[dict]:
        """Search nodes via Graphiti MCP."""
        if not self._connected:
            return [{"error": "Not connected"}]

        try:
            import uuid
            tool_use_id = f"search-nodes-{uuid.uuid4().hex[:8]}"
            result = self.mcp_client.call_tool_sync(
                tool_use_id,
                "search_nodes",
                {"query": query, "group_ids": [self.group_id], "max_nodes": max_nodes}
            )
            return [{"nodes": str(result)}]
        except Exception as e:
            return [{"error": str(e)}]

    def get_status(self) -> dict:
        """Check server status."""
        if not self._connected:
            return {"status": "disconnected"}
        try:
            import uuid
            tool_use_id = f"status-{uuid.uuid4().hex[:8]}"
            result = self.mcp_client.call_tool_sync(tool_use_id, "get_status", {})
            return {"status": "connected", "result": str(result)}
        except Exception as e:
            return {"error": str(e)}


def demo_graphiti_comparison():
    """
    Demo: Compare ChromaDB vs Graphiti with ACTUAL Graphiti MCP calls.

    Shows the different capabilities and demonstrates real graph operations.
    """
    print("\n" + "=" * 60)
    print("ITERATION 7: Graphiti MCP Integration (REAL CALLS)")
    print("=" * 60)

    print("""
ChromaDB vs Graphiti Comparison:

| Capability      | ChromaDB          | Graphiti              |
|-----------------|-------------------|-----------------------|
| Storage         | Vector embeddings | Knowledge graph       |
| Search          | Semantic similarity | Graph + semantic     |
| Relationships   | No                | Yes (edges)           |
| Temporal        | No (manual)       | Yes (fact validity)   |
| Query type      | "Find similar"    | "Find connected"      |
| Setup           | Python library    | MCP server + FalkorDB |

When to use ChromaDB:
- Simple semantic search
- Python-first environment
- <10M vectors
- Don't need relationship reasoning

When to use Graphiti:
- Complex relationship queries
- Temporal validity of facts
- "What technologies connect to user's projects?"
- Enterprise knowledge graphs
""")

    # Demo ChromaDB search
    print("\n[ChromaDB Search - Vector Similarity]")
    print("-" * 40)

    if CHROMADB_AVAILABLE:
        # Clean previous chroma data for fresh demo
        chroma_demo_dir = "./chroma_comparison_demo"
        if os.path.exists(chroma_demo_dir):
            shutil.rmtree(chroma_demo_dir)

        config = MemoryConfig(
            ltm_backend="chromadb",
            chroma_storage_dir=chroma_demo_dir,
            group_id="chroma-comparison"
        )
        chroma_memory = UnifiedMemoryV3(config)

        # Store test data
        print("  Storing test data in ChromaDB...")
        chroma_memory.store("User prefers Python for ML work", layer="semantic", entity="user", fact_type="preference")
        chroma_memory.store("User knows PyTorch and TensorFlow", layer="semantic", entity="user", fact_type="skills")
        chroma_memory.store("Discussed using PyTorch for the project", layer="episodic", context="Tech discussion")

        # Search
        context, stats = chroma_memory.recall_with_budget("user programming languages", budget_tokens=1000)
        print(f"  Query: 'user programming languages'")
        print(f"  Results: {stats['selected']} items in {stats['tokens_used']} tokens")
        print(f"  Output:\n{context}")

        # Cleanup
        shutil.rmtree(chroma_demo_dir, ignore_errors=True)
    else:
        print("  (ChromaDB not available - skipping)")

    # Demo Graphiti - ACTUAL MCP CALLS
    print("\n[Graphiti Search - Graph + Semantic (ACTUAL MCP CALLS)]")
    print("-" * 40)

    graphiti = GraphitiMemoryAdapter(group_id="level16-comparison-demo")

    if graphiti.connect():
        try:
            # Check status
            status = graphiti.get_status()
            print(f"  Server status: {status}")

            # Store test data via MCP
            print("\n  Storing test data in Graphiti...")
            result1 = graphiti.store(
                "user-python-preference",
                "User prefers Python for machine learning work. They have experience with data science.",
                source="comparison-demo"
            )
            print(f"    Store result: {result1.get('status', result1.get('error', 'unknown'))}")

            result2 = graphiti.store(
                "user-pytorch-skill",
                "User is skilled in PyTorch and uses it for deep learning projects.",
                source="comparison-demo"
            )
            print(f"    Store result: {result2.get('status', result2.get('error', 'unknown'))}")

            # Search facts
            print("\n  Searching for 'user programming' in Graphiti...")
            facts = graphiti.search_facts("user programming", max_facts=5)
            print(f"  Facts found: {json.dumps(facts, indent=2)[:500]}")

            # Search nodes
            print("\n  Searching nodes for 'Python'...")
            nodes = graphiti.search_nodes("Python", max_nodes=5)
            print(f"  Nodes found: {json.dumps(nodes, indent=2)[:500]}")

        finally:
            graphiti.disconnect()
            print("\n  [✓] Disconnected from Graphiti MCP")
    else:
        print("  [!] Could not connect to Graphiti MCP server")
        print("  [!] Ensure graphiti-mcp is running (uvx graphiti-mcp)")
        print("  [!] Or check Docker: docker ps | grep graphiti")

    print("\n[Key Insight: Choose based on query complexity]")
    print("- Simple similarity search: ChromaDB (fast, local)")
    print("- Relationship reasoning: Graphiti (graph traversal)")
    print("- Temporal queries: Graphiti (fact validity tracking)")
    print("- Can use BOTH: ChromaDB for fast lookup, Graphiti for complex queries")


# =============================================================================
# ITERATION 8: Document Memory Layer (RAG Integration)
# =============================================================================


class DocumentMemoryAdapter:
    """
    Document Memory Layer using ChromaDB for RAG.

    Plain English: Stores and retrieves documents (PDFs, markdown, text files)
    using semantic search. Completes the four-layer memory architecture.

    Integrates L13 RAG patterns into the unified memory system.
    """

    def __init__(self, storage_dir: str = "./document_memory", collection_name: str = "documents"):
        self.storage_dir = storage_dir
        self.collection_name = collection_name
        self.collection = None
        self._initialized = False

        if CHROMADB_AVAILABLE:
            self._init_collection()

    def _init_collection(self):
        """Initialize ChromaDB collection for documents."""
        import chromadb

        os.makedirs(self.storage_dir, exist_ok=True)

        try:
            client = chromadb.PersistentClient(path=self.storage_dir)
            self.collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            self._initialized = True
        except Exception as e:
            print(f"  [!] Failed to initialize document storage: {e}")
            # Fallback to in-memory
            client = chromadb.Client()
            self.collection = client.get_or_create_collection(name=self.collection_name)
            self._initialized = True

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """Split text into overlapping chunks."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start = end - overlap
        return chunks

    def ingest(self, documents: list[dict]) -> dict:
        """
        Ingest documents into the document memory.

        Args:
            documents: List of {"content": str, "metadata": dict} dicts

        Returns:
            Stats about ingestion
        """
        if not self._initialized:
            return {"error": "Document storage not initialized"}

        total_chunks = 0
        for doc in documents:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})

            chunks = self._chunk_text(content)

            for i, chunk in enumerate(chunks):
                chunk_id = f"{metadata.get('source', 'doc')}_{datetime.now().isoformat()}_{i}"
                chunk_meta = {**metadata, "chunk_index": i}

                self.collection.add(
                    documents=[chunk],
                    ids=[chunk_id],
                    metadatas=[chunk_meta]
                )
                total_chunks += 1

        return {
            "documents_processed": len(documents),
            "chunks_created": total_chunks
        }

    def search(self, query: str, num_results: int = 3) -> list[dict]:
        """
        Search documents using semantic similarity.

        Args:
            query: Search query
            num_results: Number of results to return

        Returns:
            List of matching chunks with metadata
        """
        if not self._initialized:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=num_results
        )

        matches = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                match = {
                    "content": doc,
                    "metadata": results.get("metadatas", [[]])[0][i] if results.get("metadatas") else {},
                    "distance": results.get("distances", [[]])[0][i] if results.get("distances") else None
                }
                matches.append(match)

        return matches

    def get_stats(self) -> dict:
        """Get document memory statistics."""
        if not self._initialized:
            return {"status": "not_initialized", "chunks": 0}

        return {
            "status": "initialized",
            "chunks": self.collection.count() if self.collection else 0
        }


class UnifiedMemoryV5(UnifiedMemoryV4):
    """
    Iteration 8: Unified Memory with Document Layer.

    Adds the fourth memory layer - document storage for RAG.
    """

    def __init__(self, config: MemoryConfig = None):
        super().__init__(config)
        self.documents = DocumentMemoryAdapter(
            storage_dir=os.path.join(self.config.ltm_storage_dir, "documents"),
            collection_name=f"{self.config.group_id}_docs"
        )

    def ingest_documents(self, documents: list[dict]) -> dict:
        """Ingest documents into document memory."""
        return self.documents.ingest(documents)

    def search_documents(self, query: str, num_results: int = 3) -> list[dict]:
        """Search document memory."""
        return self.documents.search(query, num_results)

    def recall_all_layers(self, query: str, budget_tokens: int = None) -> tuple[str, dict]:
        """
        Retrieve from ALL four memory layers within token budget.

        Returns XML-formatted context from:
        - Episodic memory (events)
        - Semantic memory (facts)
        - Document memory (RAG)
        """
        budget_tokens = budget_tokens or self.config.default_budget_tokens

        # Get base results from episodic/semantic (parent method)
        base_context, base_stats = self.recall_with_budget(query, budget_tokens=int(budget_tokens * 0.7))

        # Add document results
        doc_budget = int(budget_tokens * self.config.document_weight)
        doc_results = self.search_documents(query, num_results=5)

        # Format document results
        if doc_results:
            doc_tokens = 0
            selected_docs = []
            for doc in doc_results:
                doc_text = doc.get("content", "")[:200]
                doc_tokens_count = self.budget.count(doc_text)
                if doc_tokens + doc_tokens_count <= doc_budget:
                    selected_docs.append(doc_text)
                    doc_tokens += doc_tokens_count

            if selected_docs:
                doc_xml = "<documents>\n" + "\n".join(f"  - {d}" for d in selected_docs) + "\n</documents>"
                base_context = base_context + "\n\n" + doc_xml
                base_stats["document_count"] = len(selected_docs)
                base_stats["document_tokens"] = doc_tokens

        return base_context, base_stats


# Iteration 8 tools
@tool
def search_documents(query: str, num_results: int = 3) -> str:
    """
    Search the document knowledge base (RAG).

    Use for technical documentation, reference materials, uploaded docs.

    Args:
        query: Search query
        num_results: Number of results (default: 3)

    Returns:
        Matching document excerpts
    """
    memory = get_memory_v5()
    results = memory.search_documents(query, num_results)

    if not results:
        return "No documents found matching your query."

    output = f"Found {len(results)} document excerpts:\n\n"
    for i, r in enumerate(results, 1):
        output += f"{i}. {r.get('content', '')[:200]}...\n"
        if r.get("metadata"):
            output += f"   Source: {r['metadata'].get('source', 'unknown')}\n"
    return output


@tool
def ingest_document(content: str, source: str = "manual") -> str:
    """
    Add a document to the knowledge base.

    Args:
        content: Document text content
        source: Source identifier (filename, URL, etc.)

    Returns:
        Confirmation with stats
    """
    memory = get_memory_v5()
    result = memory.ingest_documents([{"content": content, "metadata": {"source": source}}])
    return f"Ingested document: {result['chunks_created']} chunks created from '{source}'"


_memory_v5: Optional[UnifiedMemoryV5] = None


def get_memory_v5() -> UnifiedMemoryV5:
    """Get or create the V5 memory instance."""
    global _memory_v5
    if _memory_v5 is None:
        _memory_v5 = UnifiedMemoryV5()
    return _memory_v5


def demo_document_layer():
    """Demo: Document Memory Layer (RAG Integration)."""
    print("\n" + "=" * 60)
    print("ITERATION 8: Document Memory Layer (RAG)")
    print("=" * 60)

    if not CHROMADB_AVAILABLE:
        print("  [!] ChromaDB not available - skipping demo")
        return

    # Clean previous demo
    demo_dir = "./doc_layer_demo"
    if os.path.exists(demo_dir):
        shutil.rmtree(demo_dir)

    config = MemoryConfig(
        ltm_backend="chromadb",
        ltm_storage_dir=demo_dir,
        group_id="doc-layer-demo"
    )
    memory = UnifiedMemoryV5(config)

    # Ingest sample documents
    print("\n[Ingesting sample documents...]")
    sample_docs = [
        {
            "content": """
            Strands Agents SDK Quick Start Guide

            Installation: pip install strands-agents
            Basic usage: from strands import Agent, tool

            Creating an agent:
            agent = Agent(model=model, tools=[my_tool])
            response = agent("Hello, how are you?")

            Tools are Python functions decorated with @tool.
            """,
            "metadata": {"source": "strands-quickstart.md", "type": "documentation"}
        },
        {
            "content": """
            Memory Patterns for AI Agents

            Three types of memory:
            1. Working Memory - current conversation context
            2. Episodic Memory - past events and interactions
            3. Semantic Memory - facts and knowledge

            Best practice: Use episodic for WHAT happened,
            semantic for WHAT is true.
            """,
            "metadata": {"source": "memory-patterns.md", "type": "guide"}
        }
    ]

    result = memory.ingest_documents(sample_docs)
    print(f"  Ingested: {result['documents_processed']} docs, {result['chunks_created']} chunks")

    # Also add some episodic/semantic for comparison
    print("\n[Adding episodic/semantic memories...]")
    memory.store("User asked about Strands SDK installation", layer="episodic", context="Support query")
    memory.store("Python", layer="semantic", entity="user", fact_type="primary_language")

    # Search all layers
    print("\n[Searching all four layers...]")
    context, stats = memory.recall_all_layers("how to create agents with tools", budget_tokens=1500)

    print(f"Stats: {stats}")
    print(f"\nCombined context:\n{context}")

    # Cleanup
    shutil.rmtree(demo_dir, ignore_errors=True)

    print("\n[Key Learning: Document layer completes four-layer architecture]")
    print("- Working: Current conversation (automatic)")
    print("- Episodic: Past events (remember/store_event)")
    print("- Semantic: Facts (remember/store_fact)")
    print("- Document: Reference materials (ingest_document/search_documents)")


# =============================================================================
# ITERATION 9: NLP Entity Extraction
# =============================================================================

# Try to import spaCy for NLP
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False


class NLPEntityExtractor:
    """
    NLP-based entity extraction using spaCy.

    Plain English: Uses proper NLP instead of regex to extract entities,
    relationships, and fact types from natural language text.

    Improves on MemoryRouter's regex-based extract_entity_fact().
    """

    def __init__(self):
        self.nlp = None
        self._initialized = False

        if SPACY_AVAILABLE:
            self._init_nlp()

    def _init_nlp(self):
        """Initialize spaCy model."""
        try:
            # Try to load the small English model
            self.nlp = spacy.load("en_core_web_sm")
            self._initialized = True
        except OSError:
            print("  [!] spaCy model not found. Install with: python -m spacy download en_core_web_sm")
            self._initialized = False

    def extract_entities(self, text: str) -> list[dict]:
        """
        Extract named entities from text.

        Returns list of {"text": str, "label": str, "start": int, "end": int}
        """
        if not self._initialized:
            return []

        doc = self.nlp(text)
        entities = []

        for ent in doc.ents:
            entities.append({
                "text": ent.text,
                "label": ent.label_,
                "start": ent.start_char,
                "end": ent.end_char
            })

        return entities

    def extract_entity_fact_nlp(self, text: str) -> tuple[str, str, str]:
        """
        Extract (entity, fact_type, value) using NLP.

        Improvements over regex:
        - Recognizes named entities (PERSON, ORG, GPE, etc.)
        - Identifies subject-verb-object patterns
        - Handles more complex sentence structures

        Returns:
            (entity, fact_type, value) tuple
        """
        if not self._initialized:
            # Fall back to regex method
            router = MemoryRouter()
            return router.extract_entity_fact(text)

        doc = self.nlp(text)

        # Extract named entities
        entities = {ent.label_: ent.text for ent in doc.ents}

        # Try to find subject-verb-object pattern
        subject = None
        verb = None
        obj = None

        for token in doc:
            if token.dep_ in ("nsubj", "nsubjpass"):
                subject = token.text.lower()
            elif token.pos_ == "VERB" and token.dep_ == "ROOT":
                verb = token.lemma_.lower()
            elif token.dep_ in ("dobj", "attr", "pobj"):
                obj = token.text

        # Map to entity/fact_type/value
        if entities.get("PERSON"):
            entity = entities["PERSON"].lower()
        elif subject:
            entity = subject
        else:
            entity = "general"

        # Determine fact type from verb
        fact_type_map = {
            "prefer": "preference",
            "like": "preference",
            "use": "technology",
            "work": "role",
            "know": "skill",
            "be": "attribute"
        }
        fact_type = fact_type_map.get(verb, "fact")

        # Value is the object or remainder
        if obj:
            value = obj
        elif entities.get("ORG"):
            value = entities["ORG"]
        elif entities.get("GPE"):
            value = entities["GPE"]
        else:
            # Extract everything after the verb
            value = text.split(verb if verb else " ")[-1].strip() if verb else text

        return (entity, fact_type, value)

    def classify_with_nlp(self, text: str) -> tuple[str, float, dict]:
        """
        Classify text for memory storage using NLP analysis.

        Returns:
            (layer, confidence, nlp_info)
        """
        if not self._initialized:
            router = MemoryRouter()
            layer, conf = router.classify_store(text)
            return (layer, conf, {"method": "regex_fallback"})

        doc = self.nlp(text)

        # Analyze sentence structure
        has_past_tense = any(token.tag_ in ("VBD", "VBN") for token in doc)
        has_temporal = any(ent.label_ in ("DATE", "TIME") for ent in doc.ents)
        has_person = any(ent.label_ == "PERSON" for ent in doc.ents)
        has_org = any(ent.label_ == "ORG" for ent in doc.ents)

        # Root verb analysis
        root_verb = None
        for token in doc:
            if token.dep_ == "ROOT" and token.pos_ == "VERB":
                root_verb = token.lemma_.lower()
                break

        # Decision logic
        episodic_signals = [has_past_tense, has_temporal, root_verb in ("discuss", "meet", "talk", "happen")]
        semantic_signals = [root_verb in ("be", "prefer", "like", "use", "know"), has_person, has_org]

        episodic_score = sum(episodic_signals)
        semantic_score = sum(semantic_signals)

        total = episodic_score + semantic_score
        if total == 0:
            return ("semantic", 0.5, {"method": "nlp", "reason": "no_signals"})

        if episodic_score > semantic_score:
            confidence = episodic_score / total
            return ("episodic", round(confidence, 2), {"method": "nlp", "signals": episodic_signals})
        else:
            confidence = semantic_score / total
            return ("semantic", round(confidence, 2), {"method": "nlp", "signals": semantic_signals})


class MemoryRouterNLP(MemoryRouter):
    """
    Enhanced Memory Router using NLP for classification.

    Falls back to regex patterns if spaCy is unavailable.
    """

    def __init__(self):
        super().__init__()
        self.nlp_extractor = NLPEntityExtractor()

    def classify_store(self, content: str) -> tuple[str, float]:
        """Classify using NLP if available, otherwise regex."""
        if self.nlp_extractor._initialized:
            layer, confidence, info = self.nlp_extractor.classify_with_nlp(content)
            return (layer, confidence)
        return super().classify_store(content)

    def extract_entity_fact(self, content: str) -> tuple[str, str, str]:
        """Extract entity/fact using NLP if available, otherwise regex."""
        if self.nlp_extractor._initialized:
            return self.nlp_extractor.extract_entity_fact_nlp(content)
        return super().extract_entity_fact(content)


def demo_nlp_extraction():
    """Demo: NLP Entity Extraction."""
    print("\n" + "=" * 60)
    print("ITERATION 9: NLP Entity Extraction")
    print("=" * 60)

    if not SPACY_AVAILABLE:
        print("  [!] spaCy not available. Install with: uv add spacy")
        print("  [!] Then download model: python -m spacy download en_core_web_sm")
        print("  [!] Falling back to regex patterns...")

    test_cases = [
        "Alice prefers Python for machine learning projects",
        "We discussed the API redesign yesterday with the team",
        "Bob works at Google as a senior engineer",
        "The project uses PostgreSQL and Redis for data storage",
        "Had a meeting about the quarterly roadmap last Tuesday",
        "Microsoft acquired GitHub in 2018",
    ]

    # Compare regex vs NLP
    regex_router = MemoryRouter()
    nlp_router = MemoryRouterNLP()

    print("\n[Comparing Regex vs NLP Classification]")
    print("-" * 70)

    for text in test_cases:
        regex_layer, regex_conf = regex_router.classify_store(text)
        regex_entity, regex_type, regex_value = regex_router.extract_entity_fact(text)

        nlp_layer, nlp_conf = nlp_router.classify_store(text)
        nlp_entity, nlp_type, nlp_value = nlp_router.extract_entity_fact(text)

        print(f"\nText: '{text[:50]}...'")
        print(f"  REGEX: {regex_layer.upper()} ({regex_conf:.0%}) -> {regex_entity}.{regex_type} = {regex_value[:20]}")
        print(f"  NLP:   {nlp_layer.upper()} ({nlp_conf:.0%}) -> {nlp_entity}.{nlp_type} = {nlp_value[:20]}")

    # Named entity extraction demo
    if SPACY_AVAILABLE:
        print("\n[Named Entity Recognition]")
        print("-" * 40)

        extractor = NLPEntityExtractor()
        sample = "Alice from Google discussed PyTorch with Bob in San Francisco last Tuesday."

        entities = extractor.extract_entities(sample)
        print(f"Text: '{sample}'")
        print("Entities found:")
        for ent in entities:
            print(f"  - {ent['text']} ({ent['label']})")

    print("\n[Key Learning: NLP improves extraction accuracy]")
    print("- Named Entity Recognition finds PERSON, ORG, GPE, DATE")
    print("- Dependency parsing identifies subject-verb-object")
    print("- Falls back gracefully to regex when spaCy unavailable")


# =============================================================================
# ITERATION 10: LanceDB Memory Backend
# =============================================================================

# Try to import LanceDB and sentence-transformers
try:
    import lancedb
    LANCEDB_AVAILABLE = True
except ImportError:
    LANCEDB_AVAILABLE = False
    print("Warning: lancedb not available. Install with: uv add lancedb")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("Warning: sentence-transformers not available. Install with: uv add sentence-transformers")

# Embedding model cache (avoid reloading)
_LOCAL_EMBEDDING_MODEL = None


def get_local_embedding_model():
    """Get or create the local embedding model (all-MiniLM-L6-v2, 384-dim)."""
    global _LOCAL_EMBEDDING_MODEL
    if _LOCAL_EMBEDDING_MODEL is None and SENTENCE_TRANSFORMERS_AVAILABLE:
        _LOCAL_EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
    return _LOCAL_EMBEDDING_MODEL


class EpisodicMemoryLanceDB:
    """
    LanceDB-backed episodic memory with semantic search.

    Plain English: Stores events/experiences in LanceDB with vector embeddings
    for semantic similarity search.

    Supports two embedding types:
    - "local": all-MiniLM-L6-v2 (384-dim, free, fast)
    - "api": text-embedding-3-small via LiteLLM (1536-dim, better quality)
    """

    def __init__(self, storage_path: str, embedding_type: str = "local"):
        """
        Initialize LanceDB episodic memory.

        Args:
            storage_path: Directory for LanceDB storage
            embedding_type: "local" (384-dim) or "api" (1536-dim)
        """
        if not LANCEDB_AVAILABLE:
            raise ImportError("lancedb required. Install with: uv add lancedb")

        self.storage_path = storage_path
        self.embedding_type = embedding_type
        self.table_name = f"episodes_{embedding_type}"

        # Determine embedding dimension
        self.embedding_dim = 384 if embedding_type == "local" else 1536

        # Connect to LanceDB
        os.makedirs(storage_path, exist_ok=True)
        self.db = lancedb.connect(storage_path)

        # Initialize table
        self._init_table()

    def _init_table(self):
        """Initialize or open the episodes table."""
        try:
            self.table = self.db.open_table(self.table_name)
        except Exception:
            # Create empty table with schema
            import pyarrow as pa
            schema = pa.schema([
                pa.field("event", pa.string()),
                pa.field("context", pa.string()),
                pa.field("document", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.embedding_dim)),
                pa.field("timestamp", pa.string()),
            ])
            self.table = self.db.create_table(self.table_name, schema=schema)

    def _get_embedding(self, text: str) -> list:
        """Get embedding for text using configured embedding type."""
        if self.embedding_type == "local":
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                raise ImportError("sentence-transformers required for local embeddings")
            model = get_local_embedding_model()
            return model.encode(text).tolist()
        else:
            # API embeddings via LiteLLM
            import openai
            client = openai.OpenAI(
                base_url="http://localhost:4000",
                api_key="sk-local"  # LiteLLM master key from .env
            )
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=[text]
            )
            return response.data[0].embedding

    def store(self, event: str, context: str = "") -> dict:
        """
        Store an episodic memory (event).

        Args:
            event: What happened
            context: Additional context

        Returns:
            dict with event and timestamp
        """
        document = f"{event}. Context: {context}" if context else event
        embedding = self._get_embedding(document)
        timestamp = datetime.now().isoformat()

        self.table.add([{
            "event": event,
            "context": context,
            "document": document,
            "vector": embedding,
            "timestamp": timestamp,
        }])

        return {"event": event, "context": context, "timestamp": timestamp}

    def search(self, query: str, max_results: int = 5) -> list:
        """
        Search episodic memory using semantic similarity.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            List of dicts with event, context, relevance
        """
        if len(self.table) == 0:
            return []

        query_vector = self._get_embedding(query)
        results = self.table.search(query_vector).limit(max_results).to_pandas()

        return [
            {
                "event": row["event"],
                "context": row["context"],
                "timestamp": row["timestamp"],
                "relevance": 1 / (1 + row["_distance"]),  # Convert distance to similarity
            }
            for _, row in results.iterrows()
        ]

    def __len__(self):
        """Return number of stored episodes."""
        return len(self.table)


class SemanticMemoryLanceDB:
    """
    LanceDB-backed semantic memory for facts/knowledge.

    Plain English: Stores entity-fact pairs with vector embeddings
    for semantic search over accumulated knowledge.
    """

    def __init__(self, storage_path: str, embedding_type: str = "local"):
        """
        Initialize LanceDB semantic memory.

        Args:
            storage_path: Directory for LanceDB storage
            embedding_type: "local" (384-dim) or "api" (1536-dim)
        """
        if not LANCEDB_AVAILABLE:
            raise ImportError("lancedb required. Install with: uv add lancedb")

        self.storage_path = storage_path
        self.embedding_type = embedding_type
        self.table_name = f"facts_{embedding_type}"

        # Determine embedding dimension
        self.embedding_dim = 384 if embedding_type == "local" else 1536

        # Connect to LanceDB
        os.makedirs(storage_path, exist_ok=True)
        self.db = lancedb.connect(storage_path)

        # Initialize table
        self._init_table()

    def _init_table(self):
        """Initialize or open the facts table."""
        try:
            self.table = self.db.open_table(self.table_name)
        except Exception:
            # Create empty table with schema
            import pyarrow as pa
            schema = pa.schema([
                pa.field("entity", pa.string()),
                pa.field("fact_type", pa.string()),
                pa.field("value", pa.string()),
                pa.field("document", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.embedding_dim)),
                pa.field("timestamp", pa.string()),
            ])
            self.table = self.db.create_table(self.table_name, schema=schema)

    def _get_embedding(self, text: str) -> list:
        """Get embedding for text using configured embedding type."""
        if self.embedding_type == "local":
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                raise ImportError("sentence-transformers required for local embeddings")
            model = get_local_embedding_model()
            return model.encode(text).tolist()
        else:
            # API embeddings via LiteLLM
            import openai
            client = openai.OpenAI(
                base_url="http://localhost:4000",
                api_key="sk-local"
            )
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=[text]
            )
            return response.data[0].embedding

    def store(self, entity: str, fact_type: str, value: str) -> dict:
        """
        Store a semantic fact.

        Args:
            entity: The entity this fact is about
            fact_type: Type of fact (e.g., "preference", "attribute")
            value: The fact value

        Returns:
            dict with entity, fact_type, value, timestamp
        """
        document = f"{entity} {fact_type}: {value}"
        embedding = self._get_embedding(document)
        timestamp = datetime.now().isoformat()

        self.table.add([{
            "entity": entity,
            "fact_type": fact_type,
            "value": value,
            "document": document,
            "vector": embedding,
            "timestamp": timestamp,
        }])

        return {"entity": entity, "fact_type": fact_type, "value": value, "timestamp": timestamp}

    def search(self, query: str, max_results: int = 5) -> list:
        """
        Search semantic memory using semantic similarity.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            List of dicts with entity, fact_type, value, relevance
        """
        if len(self.table) == 0:
            return []

        query_vector = self._get_embedding(query)
        results = self.table.search(query_vector).limit(max_results).to_pandas()

        return [
            {
                "entity": row["entity"],
                "fact_type": row["fact_type"],
                "value": row["value"],
                "timestamp": row["timestamp"],
                "relevance": 1 / (1 + row["_distance"]),
            }
            for _, row in results.iterrows()
        ]

    def __len__(self):
        """Return number of stored facts."""
        return len(self.table)


def demo_lancedb_comparison():
    """Demo: Compare local vs API embeddings in LanceDB."""
    print("\n" + "=" * 60)
    print("ITERATION 10: LanceDB Memory Backend")
    print("=" * 60)

    if not LANCEDB_AVAILABLE:
        print("  [!] LanceDB not available. Install with: uv add lancedb")
        return

    # Test data
    test_memories = [
        ("User discussed Python vs Kotlin for backend development", "Architecture meeting"),
        ("Learned about ChromaDB semantic search capabilities", "Level 13 RAG"),
        ("The 40% context utilization rule improves agent performance", "Level 15 insight"),
        ("Graphiti uses knowledge graphs for relationship reasoning", "Level 16 comparison"),
        ("Agent swarms can get stuck in ping-pong handoff loops", "Level 7 mistake"),
    ]

    test_queries = [
        "programming language comparison",
        "memory system performance",
        "multi-agent coordination issues",
    ]

    # Clean previous demo data
    for emb_type in ["local", "api"]:
        demo_path = f"./lancedb_demo_{emb_type}"
        if os.path.exists(demo_path):
            shutil.rmtree(demo_path)

    # Test both embedding types
    results = {}

    for emb_type in ["local", "api"]:
        print(f"\n--- Testing {emb_type.upper()} embeddings ---")
        dim = "384-dim" if emb_type == "local" else "1536-dim"
        print(f"  Embedding: {'all-MiniLM-L6-v2' if emb_type == 'local' else 'text-embedding-3-small'} ({dim})")

        try:
            demo_path = f"./lancedb_demo_{emb_type}"
            episodic = EpisodicMemoryLanceDB(demo_path, emb_type)
            semantic = SemanticMemoryLanceDB(demo_path, emb_type)

            # Store memories
            import time
            start = time.perf_counter()
            for event, context in test_memories:
                episodic.store(event, context)
                # Also store as fact
                semantic.store(
                    entity="Learning",
                    fact_type="observation",
                    value=event[:100]
                )
            store_time = (time.perf_counter() - start) * 1000

            print(f"  Stored: {len(episodic)} episodes, {len(semantic)} facts ({store_time:.1f}ms)")

            # Query
            query_times = []
            recalls = []

            for query in test_queries:
                start = time.perf_counter()
                ep_results = episodic.search(query, max_results=3)
                sem_results = semantic.search(query, max_results=3)
                query_time = (time.perf_counter() - start) * 1000
                query_times.append(query_time)

                print(f"\n  Query: '{query}'")
                if ep_results:
                    top = ep_results[0]
                    print(f"    Top result: '{top['event'][:50]}...' (relevance: {top['relevance']:.3f})")
                else:
                    print(f"    No results")

            results[emb_type] = {
                "store_time_ms": store_time,
                "avg_query_ms": sum(query_times) / len(query_times) if query_times else 0,
                "episodes": len(episodic),
                "facts": len(semantic),
            }

        except Exception as e:
            print(f"  [!] Error: {e}")
            results[emb_type] = {"error": str(e)}

    # Summary
    print("\n" + "-" * 60)
    print("LanceDB Embedding Comparison Summary")
    print("-" * 60)

    for emb_type, data in results.items():
        if "error" in data:
            print(f"  {emb_type.upper()}: Error - {data['error']}")
        else:
            print(f"  {emb_type.upper()}: store={data['store_time_ms']:.1f}ms, query={data['avg_query_ms']:.1f}ms")

    print("\n[Key Learning: LanceDB BYOE flexibility]")
    print("- Local embeddings: Fast, free, good for development")
    print("- API embeddings: Better quality (~15%), production use")
    print("- LanceDB requires BYOE (Bring Your Own Embeddings)")
    print("- Use same embedding model for store and query!")


# =============================================================================
# DEMO FUNCTIONS
# =============================================================================


def demo_iteration_1():
    """Demo: Memory Facade with Manual Routing."""
    print("\n" + "=" * 60)
    print("ITERATION 1: Memory Facade (Manual Routing)")
    print("=" * 60)

    # Clean
    for dir_path in [UNIFIED_MEMORY_DIR, UNIFIED_SESSION_DIR, UNIFIED_CHROMA_DIR]:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)

    config = MemoryConfig(ltm_backend="json")  # Use JSON for simple demo
    memory = UnifiedMemoryV1(config)

    print(f"\n[Created memory with backend: {memory.backend_type}]")

    # Store episodic
    print("\n[Storing episodic memory...]")
    result = memory.store("User asked about Python frameworks", layer="episodic", context="Tech discussion")
    print(f"  -> {result}")

    # Store semantic
    print("\n[Storing semantic memory...]")
    result = memory.store("Python", layer="semantic", entity="user", fact_type="primary_language")
    print(f"  -> {result}")

    # Recall
    print("\n[Recalling from episodic...]")
    results = memory.recall("Python", layer="episodic")
    for r in results:
        print(f"  -> [{r.get('timestamp', '?')[:10]}] {r.get('event', '')[:60]}")

    print("\n[Recalling from semantic...]")
    results = memory.recall("user", layer="semantic")
    for r in results:
        print(f"  -> {r}")

    print("\n[Key Learning: Manual routing gives explicit control]")
    print("- store(content, layer='episodic'|'semantic')")
    print("- recall(query, layer='episodic'|'semantic')")


def demo_iteration_2():
    """Demo: Intelligent Memory Router."""
    print("\n" + "=" * 60)
    print("ITERATION 2: Intelligent Router (Auto-Classification)")
    print("=" * 60)

    router = MemoryRouter()

    test_cases = [
        "User prefers dark mode for the IDE",
        "We discussed the Python migration yesterday",
        "Project uses PostgreSQL for the database",
        "Had a meeting about the API design",
        "Alice is a machine learning engineer",
        "The bug was fixed in the last commit",
    ]

    print("\n[Auto-Classification Results]")
    print("-" * 60)

    for content in test_cases:
        layer, confidence = router.classify_store(content)
        entity, fact_type, value = router.extract_entity_fact(content)

        print(f"Content: '{content[:50]}...'")
        print(f"  -> Layer: {layer.upper()} (confidence: {confidence:.0%})")
        if layer == "semantic":
            print(f"  -> Extracted: {entity}.{fact_type} = {value[:30]}")
        print()

    print("[Key Learning: Patterns determine storage location]")
    print("- 'prefers/likes/uses' -> semantic")
    print("- 'discussed/met/happened' -> episodic")


def demo_iteration_3():
    """Demo: Context-Aware Retrieval."""
    print("\n" + "=" * 60)
    print("ITERATION 3: Context-Aware Retrieval (Token Budget)")
    print("=" * 60)

    # Clean
    for dir_path in [UNIFIED_MEMORY_DIR, UNIFIED_SESSION_DIR]:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)

    config = MemoryConfig(ltm_backend="json")
    memory = UnifiedMemoryV3(config)

    # Populate with test data
    print("\n[Populating memory...]")
    test_data = [
        ("User prefers Python for backend work", "semantic", {"entity": "user", "fact_type": "preference"}),
        ("User knows machine learning", "semantic", {"entity": "user", "fact_type": "skill"}),
        ("Discussed API design patterns", "episodic", {"context": "Architecture meeting"}),
        ("User mentioned they use VS Code", "episodic", {"context": "Tools discussion"}),
        ("Project uses PostgreSQL", "semantic", {"entity": "project", "fact_type": "database"}),
    ]

    for content, layer, kwargs in test_data:
        memory.store(content, layer=layer, **kwargs)
        print(f"  Stored: {content[:40]}... ({layer})")

    # Retrieve with budget
    print("\n[Retrieving with budget=1000 tokens...]")
    context, stats = memory.recall_with_budget("user preferences and skills", budget_tokens=1000)

    print(f"\nStats:")
    print(f"  Candidates: {stats['candidates']}")
    print(f"  Selected: {stats['selected']}")
    print(f"  Tokens: {stats['tokens_used']} / {stats['budget_tokens']}")

    print(f"\nXML Output:\n{context}")

    print("\n[Key Learning: Budget-aware retrieval prevents bloat]")
    print("- importance = relevance * recency")
    print("- XML format for token efficiency")


def demo_iteration_4():
    """Demo: Automatic Compression."""
    print("\n" + "=" * 60)
    print("ITERATION 4: Automatic Compression (40% Rule)")
    print("=" * 60)

    config = MemoryConfig(ltm_backend="json")
    memory = UnifiedMemoryV4(config)

    # Simulate messages
    sample_messages = [{"content": f"Message {i}: Some conversation content about various topics." * 10} for i in range(5)]

    print("\n[Checking utilization...]")
    status = memory.check_utilization(sample_messages)
    print(f"  Tokens: {status['tokens']:,}")
    print(f"  Utilization: {status['utilization']}%")
    print(f"  Zone: {status['zone']}")
    print(f"  Recommendation: {status['recommendation']}")

    print("\n[Compression demonstration...]")
    messages = [f"Turn {i}: Discussion about topic {i % 5}" for i in range(40)]

    compressed, stats = memory.compress_and_extract(messages)

    print(f"  Original: {len(messages)} messages")
    print(f"  Levels: {stats.get('levels', {})}")
    print(f"  Ratio: {stats.get('ratio', 1.0)}")

    print(f"\n[Compressed preview]")
    print(compressed[:400] + "...")

    print("\n[Key Learning: Proactive compression maintains quality]")
    print("- Monitor at 40% threshold")
    print("- Hierarchical: verbatim -> paragraphs -> facts")


def demo_iteration_5():
    """Demo: Unified Memory Agent."""
    print("\n" + "=" * 60)
    print("ITERATION 5: Unified Memory Agent")
    print("=" * 60)

    # Clean
    for dir_path in [UNIFIED_MEMORY_DIR, UNIFIED_SESSION_DIR]:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)

    print("\n[Creating unified memory agent...]")
    config = MemoryConfig(
        session_id="unified-demo",
        ltm_backend="json"
    )
    agent = create_unified_memory_agent(config)

    print("\n[Turn 1: User shares information]")
    print("-" * 40)
    response = agent("Hi! My name is Bob and I'm a full-stack developer. I primarily work with TypeScript and React. Please remember this.")
    print(f"Agent: {response}")

    print("\n[Turn 2: Ask about memory]")
    print("-" * 40)
    response = agent("What do you know about me?")
    print(f"Agent: {response}")

    print("\n[Turn 3: Check memory status]")
    print("-" * 40)
    response = agent("Check your memory system status.")
    print(f"Agent: {response}")

    print("\n[Key Learning: Agent manages memory autonomously]")
    print("- Auto-routes with remember()")
    print("- Searches all layers with recall()")
    print("- Self-monitors with check_memory_status()")


def demo_iteration_6():
    """Demo: Cross-Session Persistence."""
    print("\n" + "=" * 60)
    print("ITERATION 6: Cross-Session Persistence")
    print("=" * 60)

    demo_cross_session()


def demo_iteration_7():
    """Demo: Graphiti MCP Integration."""
    demo_graphiti_comparison()


def demo_iteration_8():
    """Demo: Document Memory Layer."""
    demo_document_layer()


def demo_iteration_9():
    """Demo: NLP Entity Extraction."""
    demo_nlp_extraction()


def demo_iteration_10():
    """Demo: LanceDB Memory Backend with Embedding Comparison."""
    demo_lancedb_comparison()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Level 16: Unified Memory Architecture")
    print("=" * 60)
    print("""
Four Memory Layers:
1. Working: Current session (FileSessionManager)
2. Episodic: Past events (JSON, ChromaDB, or LanceDB)
3. Semantic: Facts/knowledge (JSON, ChromaDB, or LanceDB)
4. Document: RAG knowledge base (ChromaDB)

10 Iterations:
1. Memory Facade (manual routing)
2. Intelligent Router (auto-classification)
3. Context-Aware Retrieval (token budget)
4. Automatic Compression (40% rule)
5. Unified Memory Agent (complete)
6. Cross-Session Persistence (demo)
7. Graphiti MCP Integration (REAL calls)
8. Document Memory Layer (RAG)
9. NLP Entity Extraction (spaCy)
10. LanceDB Backend (local vs API embeddings)
""")

    # Run demos
    demo_iteration_1()
    demo_iteration_2()
    demo_iteration_3()
    demo_iteration_4()
    demo_iteration_5()
    demo_iteration_6()
    demo_iteration_7()
    demo_iteration_8()
    demo_iteration_9()
    demo_iteration_10()

    # Summary
    print("\n" + "=" * 60)
    print("Summary: Unified Memory Architecture")
    print("=" * 60)
    print("""
| Iteration | Focus                  | Key Feature                |
|-----------|------------------------|----------------------------|
| 1         | Manual Routing         | Explicit layer selection   |
| 2         | Intelligent Router     | Auto-classification        |
| 3         | Context-Aware          | Token budget retrieval     |
| 4         | Auto Compression       | 40% rule enforcement       |
| 5         | Unified Agent          | Complete tool integration  |
| 6         | Cross-Session          | Memory persistence proof   |
| 7         | Graphiti MCP           | REAL graph database calls  |
| 8         | Document Layer         | RAG completes 4 layers     |
| 9         | NLP Extraction         | spaCy replaces regex       |
| 10        | LanceDB Backend        | BYOE local vs API compare  |

Key Patterns:

1. Unified Facade:
   - Single interface for all memory operations
   - Backend-agnostic (JSON, ChromaDB, Graphiti)
   - Config-driven behavior

2. Intelligent Routing:
   - Pattern matching for auto-classification
   - Entity/fact extraction for semantic storage
   - Query classification for multi-layer search

3. Token Budget Management:
   - Importance scoring (relevance * recency)
   - Budget allocation by layer weights
   - XML output for efficiency

4. Automatic Context Management:
   - 40% rule enforcement
   - Hierarchical compression
   - Proactive, not reactive

5. Cross-Session Persistence:
   - Working memory: per-session
   - Long-term memory: shared via group_id
   - Same storage, different sessions

6. Backend Options:
   - JSON: Simple, no dependencies
   - ChromaDB: Semantic search
   - Graphiti: Graph relationships, temporal facts
""")

    # Cleanup
    print("\n[Cleanup...]")
    for dir_path in [UNIFIED_MEMORY_DIR, UNIFIED_SESSION_DIR, UNIFIED_CHROMA_DIR, "./demo_memory"]:
        shutil.rmtree(dir_path, ignore_errors=True)
    print("Done.")

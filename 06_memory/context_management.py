"""
Level 15: Context Management
============================
Efficient context window usage via recursive summarization, selective retrieval,
and hierarchical context - applying Dexter Horthy's 40% rule.

Key Insight (Horthy/HumanLayer):
- Agents perform better when using <40% of context window
- 40-60% utilization = "Dumb Zone" (hallucinations, forgotten constraints)
- XML is more token-efficient than JSON for structured data

5 Iterations:
1. Token Budget Tracker - tiktoken-based counting, utilization monitoring
2. Rolling Summarization - sliding window + summary of older context
3. Hierarchical Summarization - multi-level compression (verbatim->paragraphs->facts)
4. Selective Context Retrieval - importance scoring, token-budget-aware retrieval
5. Context-Aware Agent - combined demo with automatic compression

Prerequisites:
- LiteLLM proxy running at localhost:4000
- Level 14 memory classes (for Iteration 4-5)

Run: uv run python 06_memory/context_management.py
"""

import sys
import json
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

sys.path.insert(0, ".")

import tiktoken
from strands import Agent, tool
from strands.session.file_session_manager import FileSessionManager
from tools import get_model

# =============================================================================
# Configuration
# =============================================================================

# Model context limits (input tokens)
MODEL_LIMITS = {
    "claude-sonnet-4": 200_000,
    "claude-opus-4": 200_000,
    "claude-3-5-haiku": 200_000,
    "gemini-2.0-flash": 1_000_000,
}

# Cost per 1K tokens (USD) - updated Dec 2025
MODEL_COSTS = {
    "claude-sonnet-4": {"input": 0.003, "output": 0.015},
    "claude-opus-4": {"input": 0.015, "output": 0.075},
    "claude-3-5-haiku": {"input": 0.00025, "output": 0.00125},
    "gemini-2.0-flash": {"input": 0.000075, "output": 0.0003},
}

# Horthy's 40% rule - target utilization
TARGET_UTILIZATION = 0.40
WARNING_UTILIZATION = 0.60  # "Dumb Zone" threshold

SESSION_DIR = "./context_sessions"

# =============================================================================
# ITERATION 1: Token Budget Tracker
# =============================================================================


class TokenBudget:
    """
    Token budget tracker with utilization monitoring.

    Plain English: Tracks how much of the context window is being used
    and warns when approaching the "Dumb Zone" (>40% utilization).

    Key Methods:
    - count(text): Count tokens in text
    - utilization(messages): Get % of context window used
    - should_compress(): True when > target (40%)
    - estimate_cost(tokens, direction): Estimate USD cost
    """

    def __init__(
        self,
        model_id: str = "claude-sonnet-4",
        target_utilization: float = TARGET_UTILIZATION,
    ):
        self.model_id = model_id
        self.max_tokens = MODEL_LIMITS.get(model_id, 200_000)
        self.target = target_utilization
        self.costs = MODEL_COSTS.get(model_id, {"input": 0.003, "output": 0.015})

        # tiktoken encoding - cl100k_base works for Claude/GPT-4
        try:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            # Fallback if tiktoken has issues
            self.encoding = None

        # Track usage
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def count(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        if self.encoding is None:
            # Fallback: rough estimate (4 chars per token)
            return len(text) // 4

        return len(self.encoding.encode(text))

    def count_messages(self, messages: list[dict]) -> int:
        """Count total tokens in a list of messages."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count(content)
            elif isinstance(content, list):
                # Handle multi-part messages
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += self.count(part["text"])
            # Add overhead for role, etc.
            total += 4  # ~4 tokens overhead per message
        return total

    def utilization(self, messages: list[dict]) -> float:
        """Calculate context window utilization (0.0 to 1.0)."""
        tokens = self.count_messages(messages)
        return tokens / self.max_tokens

    def utilization_status(self, messages: list[dict]) -> dict:
        """Get detailed utilization status."""
        tokens = self.count_messages(messages)
        util = tokens / self.max_tokens

        if util < self.target:
            zone = "optimal"
        elif util < WARNING_UTILIZATION:
            zone = "warning"
        else:
            zone = "dumb_zone"

        return {
            "tokens": tokens,
            "max_tokens": self.max_tokens,
            "utilization": round(util * 100, 2),
            "target": round(self.target * 100, 2),
            "zone": zone,
            "should_compress": util > self.target,
        }

    def should_compress(self, messages: list[dict]) -> bool:
        """Check if compression is recommended (> target utilization)."""
        return self.utilization(messages) > self.target

    def estimate_cost(self, tokens: int, direction: str = "input") -> float:
        """Estimate cost in USD for given tokens."""
        rate = self.costs.get(direction, 0.003)
        return (tokens / 1000) * rate

    def track_usage(self, input_tokens: int, output_tokens: int):
        """Track cumulative token usage."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def get_total_cost(self) -> dict:
        """Get total cost so far."""
        input_cost = self.estimate_cost(self.total_input_tokens, "input")
        output_cost = self.estimate_cost(self.total_output_tokens, "output")
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(input_cost + output_cost, 6),
        }


# Iteration 1 tool
budget_tracker = TokenBudget()


@tool
def check_context_budget(conversation_text: str) -> str:
    """
    Check current context window utilization.

    Use this to monitor how much of the context window is being used.
    When utilization exceeds 40%, consider compressing older context.

    Args:
        conversation_text: The full conversation text to analyze

    Returns:
        Status including utilization %, zone (optimal/warning/dumb_zone), and recommendation
    """
    # Simulate messages format
    messages = [{"content": conversation_text}]
    status = budget_tracker.utilization_status(messages)

    if status["zone"] == "optimal":
        recommendation = "Context is healthy. No action needed."
    elif status["zone"] == "warning":
        recommendation = "Approaching Dumb Zone. Consider summarizing older context."
    else:
        recommendation = "IN DUMB ZONE! Compress context immediately to maintain quality."

    return f"""Context Budget Status:
- Tokens: {status['tokens']:,} / {status['max_tokens']:,}
- Utilization: {status['utilization']}%
- Target: <{status['target']}%
- Zone: {status['zone'].upper()}
- Recommendation: {recommendation}"""


# =============================================================================
# ITERATION 2: Rolling Summarization
# =============================================================================


class RollingSummarizer:
    """
    Rolling summarization - keep recent messages verbatim, summarize older ones.

    Pattern: "sliding window + summary"
    - Recent N messages: kept verbatim
    - Older messages: compressed into XML-wrapped summary

    Horthy insight: Use XML wrapping for token efficiency.
    """

    def __init__(self, model_id: str = "claude-3-5-haiku", keep_recent: int = 5):
        self.model = get_model(model_id)
        self.keep_recent = keep_recent
        self.budget = TokenBudget(model_id)

        # Track compression stats
        self.compressions = 0
        self.tokens_saved = 0

    def _create_summary_agent(self) -> Agent:
        """Create a lightweight agent for summarization."""
        return Agent(
            model=self.model,
            system_prompt="""You are a concise summarizer. Given conversation history,
create a brief summary preserving:
1. Key facts learned
2. Important decisions made
3. User preferences expressed
4. Unresolved questions

Output format: Plain text, 2-3 sentences max. Be specific, not generic.""",
            callback_handler=None,
        )

    def summarize_older(self, messages: list[str]) -> tuple[str, dict]:
        """
        Summarize older messages using LLM.

        Returns: (summary_text, stats_dict)
        """
        if not messages:
            return "", {"original_tokens": 0, "summary_tokens": 0, "ratio": 1.0}

        # Count original tokens
        original_text = "\n".join(messages)
        original_tokens = self.budget.count(original_text)

        # Use agent to summarize
        agent = self._create_summary_agent()
        response = agent(f"Summarize this conversation history:\n\n{original_text}")
        summary = str(response)

        # Count summary tokens
        summary_tokens = self.budget.count(summary)

        # Track stats
        self.compressions += 1
        self.tokens_saved += original_tokens - summary_tokens

        return summary, {
            "original_tokens": original_tokens,
            "summary_tokens": summary_tokens,
            "ratio": round(summary_tokens / original_tokens, 3) if original_tokens > 0 else 1.0,
            "cost": self.budget.estimate_cost(original_tokens + summary_tokens, "input"),
        }

    def rolling_context(self, messages: list[str]) -> tuple[str, dict]:
        """
        Apply rolling summarization to message list.

        Returns: (compressed_context, stats_dict)
        """
        if len(messages) <= self.keep_recent:
            return "\n".join(messages), {"compressed": False, "reason": "Below threshold"}

        recent = messages[-self.keep_recent :]
        older = messages[: -self.keep_recent]

        summary, stats = self.summarize_older(older)

        # XML-wrapped format (Horthy recommendation)
        compressed = f"""<context_summary>
{summary}
</context_summary>

<recent_messages>
{chr(10).join(recent)}
</recent_messages>"""

        stats["compressed"] = True
        stats["recent_count"] = len(recent)
        stats["summarized_count"] = len(older)

        return compressed, stats

    def get_stats(self) -> dict:
        """Get compression statistics."""
        return {
            "compressions": self.compressions,
            "tokens_saved": self.tokens_saved,
            "estimated_cost_saved": self.budget.estimate_cost(self.tokens_saved, "input"),
        }


# Iteration 2 tool
rolling_summarizer = RollingSummarizer()


@tool
def compress_history(conversation_history: str, keep_recent: int = 5) -> str:
    """
    Compress older conversation history while keeping recent messages verbatim.

    Uses rolling summarization: older messages are summarized, recent kept intact.
    This maintains quality while reducing context window usage.

    Args:
        conversation_history: Full conversation as newline-separated messages
        keep_recent: Number of recent messages to keep verbatim (default: 5)

    Returns:
        Compressed context with summary of older content + recent messages
    """
    messages = conversation_history.strip().split("\n\n")
    rolling_summarizer.keep_recent = keep_recent

    compressed, stats = rolling_summarizer.rolling_context(messages)

    result = f"""Compression Result:
- Original messages: {len(messages)}
- Summarized: {stats.get('summarized_count', 0)}
- Kept verbatim: {stats.get('recent_count', len(messages))}
- Compression ratio: {stats.get('ratio', 1.0)}
- Estimated cost: ${stats.get('cost', 0):.6f}

Compressed Context:
{compressed}"""

    return result


# =============================================================================
# ITERATION 3: Hierarchical Summarization
# =============================================================================


@dataclass
class CompressionLevel:
    """Configuration for a compression level."""

    name: str
    max_age_turns: int  # Messages older than this get this compression
    compression_type: str  # "verbatim", "paragraph", "facts"


class HierarchicalSummarizer:
    """
    Multi-level compression based on message age.

    Three levels (Claude Code's auto-compact pattern):
    - Level 1: Verbatim (recent, < 10 turns)
    - Level 2: Paragraph summaries (older, 10-30 turns)
    - Level 3: Key facts only (oldest, > 30 turns)

    Plain English: Recent stuff stays detailed, older stuff gets more compressed.
    """

    LEVELS = [
        CompressionLevel("verbatim", 10, "verbatim"),
        CompressionLevel("paragraph", 30, "paragraph"),
        CompressionLevel("facts", 999, "facts"),
    ]

    def __init__(self, model_id: str = "claude-3-5-haiku"):
        self.model = get_model(model_id)
        self.budget = TokenBudget(model_id)

    def _get_level(self, age_turns: int) -> CompressionLevel:
        """Determine compression level based on message age."""
        for level in self.LEVELS:
            if age_turns < level.max_age_turns:
                return level
        return self.LEVELS[-1]

    def _compress_to_paragraphs(self, messages: list[str]) -> str:
        """Compress messages to paragraph summary."""
        agent = Agent(
            model=self.model,
            system_prompt="Summarize into 1-2 paragraphs. Preserve key details and decisions.",
            callback_handler=None,
        )
        response = agent(f"Summarize:\n{chr(10).join(messages)}")
        return str(response)

    def _compress_to_facts(self, messages: list[str]) -> str:
        """Extract only key facts from messages."""
        agent = Agent(
            model=self.model,
            system_prompt="""Extract ONLY key facts as bullet points. Format:
- [FACT]: specific fact
- [PREF]: user preference
- [DECISION]: decision made
Maximum 5 bullets.""",
            callback_handler=None,
        )
        response = agent(f"Extract facts:\n{chr(10).join(messages)}")
        return str(response)

    def compress(self, messages: list[str]) -> tuple[str, dict]:
        """
        Apply hierarchical compression to messages.

        Messages are grouped by age and compressed accordingly:
        - Recent: verbatim
        - Medium: paragraph summaries
        - Old: key facts only

        Returns: (compressed_context, stats_dict)
        """
        total = len(messages)
        if total == 0:
            return "", {"levels": {}}

        # Group messages by compression level
        groups = {"verbatim": [], "paragraph": [], "facts": []}

        for i, msg in enumerate(messages):
            age = total - i  # Oldest = highest age
            level = self._get_level(age)
            groups[level.compression_type].append(msg)

        # Build compressed output
        parts = []
        stats = {"levels": {}, "original_tokens": 0, "compressed_tokens": 0}

        # Level 3: Facts (oldest)
        if groups["facts"]:
            facts = self._compress_to_facts(groups["facts"])
            parts.append(f"<historical_facts>\n{facts}\n</historical_facts>")
            stats["levels"]["facts"] = len(groups["facts"])

        # Level 2: Paragraphs (medium age)
        if groups["paragraph"]:
            paragraphs = self._compress_to_paragraphs(groups["paragraph"])
            parts.append(f"<context_summary>\n{paragraphs}\n</context_summary>")
            stats["levels"]["paragraph"] = len(groups["paragraph"])

        # Level 1: Verbatim (recent)
        if groups["verbatim"]:
            parts.append(f"<recent_context>\n{chr(10).join(groups['verbatim'])}\n</recent_context>")
            stats["levels"]["verbatim"] = len(groups["verbatim"])

        compressed = "\n\n".join(parts)

        # Calculate compression stats
        original = "\n".join(messages)
        stats["original_tokens"] = self.budget.count(original)
        stats["compressed_tokens"] = self.budget.count(compressed)
        stats["ratio"] = (
            round(stats["compressed_tokens"] / stats["original_tokens"], 3)
            if stats["original_tokens"] > 0
            else 1.0
        )

        return compressed, stats


# Iteration 3 tool
hierarchical_summarizer = HierarchicalSummarizer()


@tool
def hierarchical_compress(conversation_history: str) -> str:
    """
    Apply hierarchical compression based on message age.

    Three compression levels:
    - Recent (<10 turns): Kept verbatim
    - Medium (10-30 turns): Paragraph summaries
    - Old (>30 turns): Key facts only

    This preserves important context while aggressively compressing old content.

    Args:
        conversation_history: Full conversation as newline-separated messages

    Returns:
        Hierarchically compressed context with level breakdown
    """
    messages = conversation_history.strip().split("\n\n")
    compressed, stats = hierarchical_summarizer.compress(messages)

    level_breakdown = "\n".join(
        f"  - {level}: {count} messages" for level, count in stats.get("levels", {}).items()
    )

    return f"""Hierarchical Compression Result:
- Total messages: {len(messages)}
- Levels applied:
{level_breakdown}
- Original tokens: {stats.get('original_tokens', 0):,}
- Compressed tokens: {stats.get('compressed_tokens', 0):,}
- Compression ratio: {stats.get('ratio', 1.0)}

Compressed Context:
{compressed}"""


# =============================================================================
# ITERATION 4: Selective Context Retrieval
# =============================================================================


class SelectiveRetriever:
    """
    Token-budget-aware context retrieval from memory.

    Integrates with Level 14's memory systems to retrieve only relevant
    context that fits within a token budget.

    Pattern:
    1. Search memory for candidates
    2. Score by importance (relevance * recency)
    3. Fill budget with highest-ranked
    """

    def __init__(self, model_id: str = "claude-sonnet-4"):
        self.budget = TokenBudget(model_id)

        # Import Level 14 memory (if available)
        try:
            from longterm_memory import EpisodicMemoryJSON, SemanticMemoryJSON

            self.episodic = EpisodicMemoryJSON(group_id="selective")
            self.semantic = SemanticMemoryJSON(group_id="selective")
            self.has_memory = True
        except ImportError:
            self.has_memory = False

    def importance_score(self, item: dict, query: str) -> float:
        """
        Calculate importance score for a memory item.

        Score = relevance * recency_decay

        - relevance: keyword overlap (simple) or embedding similarity (advanced)
        - recency_decay: exponential decay based on age
        """
        # Simple relevance: keyword overlap
        query_words = set(query.lower().split())
        item_text = str(item.get("event", "") or item.get("value", "")).lower()
        item_words = set(item_text.split())

        overlap = len(query_words & item_words)
        relevance = overlap / len(query_words) if query_words else 0.0

        # Recency decay (simple: newer = higher)
        timestamp = item.get("timestamp", "")
        if timestamp:
            try:
                age_hours = (
                    datetime.now() - datetime.fromisoformat(timestamp)
                ).total_seconds() / 3600
                recency = 1.0 / (1.0 + age_hours / 24)  # Half-life of 24 hours
            except Exception:
                recency = 0.5
        else:
            recency = 0.5

        return relevance * recency

    def retrieve(self, query: str, budget_tokens: int = 2000) -> tuple[list[dict], dict]:
        """
        Retrieve context that fits within token budget.

        Args:
            query: Search query
            budget_tokens: Maximum tokens to retrieve

        Returns: (items, stats)
        """
        if not self.has_memory:
            return [], {"error": "Level 14 memory not available"}

        # Get candidates from both memory types
        candidates = []

        # Episodic memory
        episodes = self.episodic.search(query, max_results=10)
        for ep in episodes:
            ep["_type"] = "episodic"
            ep["_score"] = self.importance_score(ep, query)
            candidates.append(ep)

        # Semantic memory
        facts = self.semantic.search(query)
        for fact in facts:
            fact["_type"] = "semantic"
            fact["_score"] = self.importance_score(fact, query)
            candidates.append(fact)

        # Sort by score (descending)
        candidates.sort(key=lambda x: x.get("_score", 0), reverse=True)

        # Fill budget
        selected = []
        tokens_used = 0

        for item in candidates:
            item_text = json.dumps(item)
            item_tokens = self.budget.count(item_text)

            if tokens_used + item_tokens <= budget_tokens:
                selected.append(item)
                tokens_used += item_tokens

        stats = {
            "candidates": len(candidates),
            "selected": len(selected),
            "tokens_used": tokens_used,
            "budget": budget_tokens,
            "utilization": round(tokens_used / budget_tokens * 100, 2) if budget_tokens > 0 else 0,
        }

        return selected, stats

    def format_as_xml(self, items: list[dict]) -> str:
        """Format retrieved items as XML (Horthy recommendation)."""
        if not items:
            return "<retrieved_context>No relevant context found.</retrieved_context>"

        episodic = [i for i in items if i.get("_type") == "episodic"]
        semantic = [i for i in items if i.get("_type") == "semantic"]

        parts = []

        if episodic:
            eps = "\n".join(f"  - [{e.get('timestamp', '?')[:10]}] {e.get('event', '')[:100]}" for e in episodic)
            parts.append(f"<past_events>\n{eps}\n</past_events>")

        if semantic:
            facts = "\n".join(f"  - {f.get('entity', '?')}: {f.get('value', '')}" for f in semantic)
            parts.append(f"<known_facts>\n{facts}\n</known_facts>")

        return "\n".join(parts)


# Iteration 4 tool
selective_retriever = SelectiveRetriever()


@tool
def retrieve_relevant(query: str, max_tokens: int = 2000) -> str:
    """
    Retrieve relevant context from long-term memory within a token budget.

    Uses importance scoring (relevance * recency) to select the most
    valuable context that fits within the specified token limit.

    Args:
        query: What to search for in memory
        max_tokens: Maximum tokens to retrieve (default: 2000)

    Returns:
        XML-formatted relevant context with retrieval stats
    """
    items, stats = selective_retriever.retrieve(query, max_tokens)
    context = selective_retriever.format_as_xml(items)

    return f"""Retrieval Stats:
- Candidates found: {stats.get('candidates', 0)}
- Selected (within budget): {stats.get('selected', 0)}
- Tokens used: {stats.get('tokens_used', 0)} / {stats.get('budget', 0)}
- Budget utilization: {stats.get('utilization', 0)}%

{context}"""


# =============================================================================
# ITERATION 5: Context-Aware Agent
# =============================================================================


def create_context_aware_agent(session_id: str = "context-demo") -> Agent:
    """
    Create an agent that manages its own context efficiently.

    Combines:
    - Token budget tracking
    - Automatic compression at 40% threshold
    - Selective memory retrieval
    - XML formatting for efficiency

    The agent has tools to monitor and manage its context window.
    """
    model = get_model("claude-sonnet-4")

    return Agent(
        model=model,
        session_manager=FileSessionManager(session_id=session_id, storage_dir=SESSION_DIR),
        tools=[
            # Context management tools (L15)
            check_context_budget,
            compress_history,
            hierarchical_compress,
            retrieve_relevant,
        ],
        system_prompt="""You are an assistant with advanced context management capabilities.

CONTEXT RULES (Horthy's 40% Rule):
1. Periodically check context budget with check_context_budget
2. When utilization exceeds 40%, use compress_history or hierarchical_compress
3. For questions about past conversations, use retrieve_relevant
4. Prefer XML formatting for any structured data you output

WORKFLOW:
- At the start of complex tasks, check your context budget
- If context is getting full, proactively compress before continuing
- For memory-heavy tasks, retrieve only what's needed

Remember: Quality degrades in the "Dumb Zone" (>40% utilization).
Keep context lean and focused for best performance.""",
        callback_handler=None,
    )


# =============================================================================
# DEMO FUNCTIONS
# =============================================================================


def demo_iteration_1():
    """Demo: Token Budget Tracker."""
    print("\n" + "=" * 60)
    print("ITERATION 1: Token Budget Tracker")
    print("=" * 60)

    budget = TokenBudget("claude-sonnet-4")

    # Test token counting
    test_texts = [
        "Hello, world!",
        "This is a longer message with more tokens to count.",
        "A" * 1000,  # 1000 characters
    ]

    print("\n[Token Counting Tests]")
    for text in test_texts:
        tokens = budget.count(text)
        print(f"  '{text[:30]}...' ({len(text)} chars) = {tokens} tokens")

    # Test utilization
    print("\n[Utilization Status]")
    messages = [{"content": "User: Hello!\nAssistant: Hi there! How can I help you today?"}]
    status = budget.utilization_status(messages)
    print(f"  Tokens: {status['tokens']:,}")
    print(f"  Utilization: {status['utilization']}%")
    print(f"  Zone: {status['zone']}")
    print(f"  Should compress: {status['should_compress']}")

    # Test cost estimation
    print("\n[Cost Estimation]")
    for tokens in [1000, 10000, 100000]:
        input_cost = budget.estimate_cost(tokens, "input")
        output_cost = budget.estimate_cost(tokens, "output")
        print(f"  {tokens:,} tokens: input=${input_cost:.4f}, output=${output_cost:.4f}")

    print("\n[Key Learning: tiktoken provides accurate token counts]")
    print("- Use cl100k_base encoding for Claude/GPT-4 models")
    print("- Track utilization against 40% target (Horthy rule)")
    print("- Cost estimation enables budget awareness")


def demo_iteration_2():
    """Demo: Rolling Summarization."""
    print("\n" + "=" * 60)
    print("ITERATION 2: Rolling Summarization")
    print("=" * 60)

    # Simulate a conversation
    messages = [
        "User: Hi, I'm working on a Python project.",
        "Assistant: Great! What kind of project?",
        "User: It's a web scraper using BeautifulSoup.",
        "Assistant: Nice choice. Do you need help with parsing or requests?",
        "User: I'm stuck on handling pagination.",
        "Assistant: For pagination, you'll want to identify the 'next' link pattern.",
        "User: The site uses JavaScript to load more content.",
        "Assistant: Ah, you'll need Selenium or Playwright for JS-rendered content.",
        "User: Is Playwright better than Selenium?",
        "Assistant: Playwright is faster and has better API, but Selenium has more community support.",
        "User: I'll try Playwright then. How do I install it?",
        "Assistant: Run 'pip install playwright' then 'playwright install' for browsers.",
    ]

    print(f"\n[Original: {len(messages)} messages]")
    for i, msg in enumerate(messages[:3]):
        print(f"  {i + 1}. {msg[:60]}...")
    print("  ...")

    print("\n[Applying Rolling Summarization (keep_recent=5)...]")
    summarizer = RollingSummarizer(keep_recent=5)
    compressed, stats = summarizer.rolling_context(messages)

    print(f"\n[Result]")
    print(f"  Summarized: {stats.get('summarized_count', 0)} messages")
    print(f"  Kept verbatim: {stats.get('recent_count', 0)} messages")
    print(f"  Compression ratio: {stats.get('ratio', 1.0)}")

    print("\n[Compressed Context Preview]")
    print(compressed[:500] + "...")

    print("\n[Key Learning: Rolling summarization preserves recent detail]")
    print("- XML wrapping improves token efficiency")
    print("- Older context compressed but key info preserved")


def demo_iteration_3():
    """Demo: Hierarchical Summarization."""
    print("\n" + "=" * 60)
    print("ITERATION 3: Hierarchical Summarization")
    print("=" * 60)

    # Simulate a longer conversation (40 messages)
    messages = []
    topics = [
        ("Python basics", 10),
        ("Web development", 10),
        ("Database design", 10),
        ("API development", 10),
    ]

    for topic, count in topics:
        for i in range(count):
            messages.append(f"[{topic}] Message {i + 1}: Discussion about {topic.lower()}...")

    print(f"\n[Original: {len(messages)} messages across 4 topics]")
    print(f"  Expected levels:")
    print(f"  - Verbatim (recent <10): last 10 messages")
    print(f"  - Paragraph (medium 10-30): 20 messages")
    print(f"  - Facts (old >30): 10 messages")

    print("\n[Applying Hierarchical Compression...]")
    summarizer = HierarchicalSummarizer()
    compressed, stats = summarizer.compress(messages)

    print(f"\n[Result]")
    for level, count in stats.get("levels", {}).items():
        print(f"  {level}: {count} messages")
    print(f"  Compression ratio: {stats.get('ratio', 1.0)}")

    print("\n[Compressed Context Preview]")
    print(compressed[:600] + "...")

    print("\n[Key Learning: Hierarchical compression matches human memory]")
    print("- Recent: full detail (like short-term memory)")
    print("- Medium: summaries (like recent memory)")
    print("- Old: key facts (like long-term memory)")


def demo_iteration_4():
    """Demo: Selective Context Retrieval."""
    print("\n" + "=" * 60)
    print("ITERATION 4: Selective Context Retrieval")
    print("=" * 60)

    print("\n[Selective Retrieval Concept]")
    print("""
Pattern:
1. Search memory for candidates matching query
2. Score each by: importance = relevance * recency
3. Fill token budget with highest-scored items
4. Format as XML for efficiency

Integration with Level 14:
- Episodic memory: past events/interactions
- Semantic memory: facts and knowledge
- ChromaDB: semantic similarity search (if available)
""")

    # Demo without actual memory (show the pattern)
    retriever = SelectiveRetriever()

    # Mock some items for demonstration
    mock_items = [
        {
            "event": "User mentioned they prefer Python over JavaScript",
            "timestamp": datetime.now().isoformat(),
            "_type": "episodic",
            "_score": 0.8,
        },
        {
            "entity": "user",
            "fact_type": "preference",
            "value": "Python",
            "_type": "semantic",
            "_score": 0.9,
        },
    ]

    xml_output = retriever.format_as_xml(mock_items)
    print("[XML Output Format]")
    print(xml_output)

    print("\n[Key Learning: Budget-aware retrieval prevents context bloat]")
    print("- Only retrieve what's needed for the current query")
    print("- Importance scoring prioritizes relevant + recent")
    print("- Token budget ensures context stays lean")


def demo_iteration_5():
    """Demo: Context-Aware Agent."""
    print("\n" + "=" * 60)
    print("ITERATION 5: Context-Aware Agent")
    print("=" * 60)

    print("\n[Creating context-aware agent...]")
    agent = create_context_aware_agent("demo-session")

    print("\n[Agent has these context management tools:]")
    print("  1. check_context_budget - Monitor utilization")
    print("  2. compress_history - Rolling summarization")
    print("  3. hierarchical_compress - Multi-level compression")
    print("  4. retrieve_relevant - Budget-aware memory retrieval")

    print("\n[Testing agent with context check...]")
    response = agent("Check your current context budget and tell me about your context management capabilities.")
    print(f"\nAgent Response:\n{response}")

    print("\n[Key Learning: Agents can manage their own context]")
    print("- Proactive compression before quality degrades")
    print("- Self-aware of Horthy's 40% rule")
    print("- Tools enable autonomous context optimization")


# =============================================================================
# MAIN
# =============================================================================

# =============================================================================
# Iteration 6: SDK-Native Sliding Window (SDK v1.35 — replaces Iteration 2)
# =============================================================================
# SlidingWindowConversationManager with per_turn replaces hand-rolled
# RollingSummarizer. The SDK handles message trimming, user-first
# enforcement, and tool result truncation automatically.

from strands.agent.conversation_manager import SlidingWindowConversationManager


def demo_iteration_6():
    """SDK-native sliding window replaces RollingSummarizer."""
    print("\n" + "=" * 60)
    print("Iteration 6: SDK-Native Sliding Window (v1.35)")
    print("  Replaces: Iteration 2 (hand-rolled RollingSummarizer)")
    print("=" * 60)

    # Iteration 2 used: RollingSummarizer(keep_recent=5)
    # with custom LLM-based summarization of older messages.
    #
    # SDK v1.35 provides this out of the box:
    cm = SlidingWindowConversationManager(
        window_size=10,    # keep last 10 messages
        per_turn=3,        # trim every 3 model calls
    )

    model = get_model("haiku")
    agent = Agent(
        model=model,
        conversation_manager=cm,
        system_prompt="You are a helpful assistant. Be concise (1 sentence).",
        callback_handler=None,
    )

    # Multi-turn conversation
    turns = [
        "My name is Alice and I work at Acme Corp.",
        "I'm interested in machine learning.",
        "What frameworks do you recommend?",
        "Tell me about PyTorch specifically.",
        "How does it compare to JAX?",
        "What about deployment options?",
    ]

    print()
    for i, msg in enumerate(turns, 1):
        result = agent(msg)
        trim_note = " ← trim" if i % 3 == 0 else ""
        print(f"  Turn {i}: {len(agent.messages)} msgs | {str(result)[:60]}...{trim_note}")

    print(f"\n  Final: {len(agent.messages)} messages (window_size=10, per_turn=3)")
    print("""
  Comparison:
  ┌───────────────────────┬───────────────────┬────────────────────────┐
  │ Aspect                │ RollingSummarizer │ SlidingWindowCM        │
  ├───────────────────────┼───────────────────┼────────────────────────┤
  │ Code needed           │ ~80 lines         │ 3 lines (config)       │
  │ Summarization         │ LLM call (Haiku)  │ Truncation (no LLM)    │
  │ Token cost            │ Extra LLM calls   │ Zero overhead          │
  │ User-first enforce    │ Manual            │ Automatic              │
  │ Tool result handling  │ Manual            │ Auto-truncates large   │
  │ per_turn control      │ N/A               │ False/True/N           │
  └───────────────────────┴───────────────────┴────────────────────────┘
  """)
    print("  ✓ SDK handles what took 80 lines of custom code")


# =============================================================================
# Iteration 7: SDK Token Tracking (SDK v1.35 — replaces tiktoken in Iter 1)
# =============================================================================
# EventLoopMetrics provides actual token counts from the model provider,
# replacing the tiktoken approximation in TokenBudget.

def demo_iteration_7():
    """SDK token tracking replaces tiktoken-based TokenBudget."""
    print("\n" + "=" * 60)
    print("Iteration 7: SDK Token Tracking (v1.35)")
    print("  Replaces: Iteration 1 (tiktoken-based TokenBudget)")
    print("=" * 60)

    # Iteration 1 used: TokenBudget with tiktoken cl100k_base encoding
    # to ESTIMATE token counts. But:
    #  - tiktoken is an approximation (GPT tokenizer, not Claude's)
    #  - Doesn't account for system prompt, tool schemas, formatting
    #  - No cache metrics
    #
    # SDK v1.35 provides ACTUAL token counts via EventLoopMetrics:

    model = get_model("haiku")
    agent = Agent(
        model=model,
        system_prompt="You are a helpful assistant. Be concise (1 sentence).",
        callback_handler=None,
    )

    # Also create a tiktoken estimate for comparison
    budget = TokenBudget("claude-3-5-haiku")

    print()
    print(f"  {'Turn':<6} {'tiktoken est':<14} {'SDK actual':<14} {'Diff':<10} {'Response':<40}")
    print(f"  {'-'*6} {'-'*14} {'-'*14} {'-'*10} {'-'*40}")

    turns = [
        "What is Python?",
        "What about Rust?",
        "Compare them briefly.",
    ]

    for i, msg in enumerate(turns, 1):
        # tiktoken estimate (Iteration 1 approach)
        all_text = " ".join(msg for msg in turns[:i])
        tiktoken_est = budget.count(all_text)

        # SDK actual (v1.35 approach)
        result = agent(msg)
        metrics = result.metrics
        invocation = metrics.latest_agent_invocation
        sdk_input = 0
        if invocation and invocation.cycles:
            sdk_input = invocation.cycles[-1].usage.get("inputTokens", 0)

        diff = sdk_input - tiktoken_est
        resp_short = str(result)[:37] + "..."
        print(f"  {i:<6} {tiktoken_est:<14} {sdk_input:<14} {'+' + str(diff) if diff > 0 else diff:<10} {resp_short:<40}")

    print("""
  Why SDK actual > tiktoken estimate:
  - tiktoken counts MESSAGE TEXT only
  - SDK counts: system prompt + message history + formatting overhead
  - System prompt alone can be 20-50 tokens
  - Each message has role/formatting tokens

  For Horthy's 40% rule, SDK actual tokens give you the REAL number.
  """)
    print("  ✓ Actual tokens from provider — no approximation needed")


# =============================================================================
# Iteration 8: Context-Aware Sub-Agents (SDK v1.35 — extends Iter 5)
# =============================================================================
# Agent.as_tool(preserve_context=True) lets sub-agents share context
# with the orchestrator, reducing redundant context transmission.

def demo_iteration_8():
    """Context-aware sub-agents via preserve_context."""
    print("\n" + "=" * 60)
    print("Iteration 8: Context-Aware Sub-Agents (v1.35)")
    print("  Extends: Iteration 5 (Context-Aware Agent)")
    print("=" * 60)

    model = get_model("haiku")

    # Stateless sub-agent (default): gets NO context from prior calls
    researcher = Agent(
        model=model,
        name="researcher",
        description="Researches topics and returns findings",
        system_prompt="You are a researcher. Be very concise (1-2 sentences).",
        callback_handler=None,
    )

    # Stateful sub-agent: REMEMBERS prior calls
    stateful_researcher = Agent(
        model=model,
        name="stateful_researcher",
        description="Researches topics with memory of prior findings",
        system_prompt="You are a researcher who builds on prior findings. Be very concise (1-2 sentences).",
        callback_handler=None,
    )

    # Wrap with different preserve_context settings
    stateless_tool = researcher.as_tool(preserve_context=False)
    stateful_tool = stateful_researcher.as_tool(preserve_context=True)

    orchestrator = Agent(
        model=get_model("claude-sonnet-4"),
        tools=[stateless_tool, stateful_tool],
        system_prompt="""You have two research assistants:
- researcher: forgets between calls (stateless)
- stateful_researcher: remembers prior calls (stateful)

Use stateful_researcher when building on prior findings.
Use researcher for independent lookups.
Be concise in your synthesis.""",
        callback_handler=None,
    )

    print()
    result = orchestrator("""Research plan:
1. Ask stateful_researcher about Python's GIL
2. Then ask stateful_researcher how asyncio works around the GIL
   (it should remember the GIL context from step 1)
3. Ask researcher about Rust's concurrency model
   (independent lookup, no prior context needed)
4. Synthesize all findings.""")

    print(f"\n  Result:\n  {str(result)[:500]}")
    print("""
  Context efficiency:
  - stateful_researcher: 2 calls, context grows (GIL → asyncio builds on GIL)
  - researcher: 1 call, fresh context (independent Rust lookup)

  preserve_context=True is useful when:
  - Sub-agent calls are sequential and build on each other
  - You want the sub-agent to accumulate knowledge across calls
  - The orchestrator delegates a multi-step research workflow

  preserve_context=False (default) is better when:
  - Sub-agent calls are independent
  - You want deterministic, isolated behavior
  - Thread safety matters (state reset prevents cross-invocation leaks)
  """)
    print("  ✓ preserve_context gives sub-agents conversational memory")


# =============================================================================
# Iteration 9: Proactive Compression (SDK v1.42 — compress BEFORE the model call)
# =============================================================================
# SummarizingConversationManager(proactive_compression={"compression_threshold": 0.8})
# registers a BeforeModelCallEvent hook: when projected_input_tokens exceed
# threshold x model.context_window_limit, it summarizes older turns BEFORE the
# model is called — preemptive, not reactive.
#
# Contrast across this lesson:
#   Iter 1-5  hand-rolled token tracking + summarization
#   Iter 6    SlidingWindowConversationManager  — REACTIVE trim on overflow error
#   Iter 9    SummarizingConversationManager + proactive_compression — PREEMPTIVE
#
# Caveat (validated by running this lesson 2026-06-02): the hook reads
# model.context_window_limit. LiteLLM/OpenAI and Gemini do NOT auto-populate it,
# so you MUST set it explicitly (get_model(..., context_window_limit=N)) — else
# it falls back to a large default and proactive compression never fires.
import logging  # noqa: E402
from strands.agent.conversation_manager import SummarizingConversationManager  # noqa: E402


def demo_iteration_9():
    print("\n" + "=" * 70)
    print("Iteration 9: Proactive Compression (v1.42 — compress before the call)")
    print("=" * 70)
    print("  Extends: reactive trimming (Iter 6) -> preemptive summarization")

    # Capture the conversation-manager DEBUG log so we can SEE the hook fire.
    captured: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    cm_logger = logging.getLogger(
        "strands.agent.conversation_manager.conversation_manager"
    )
    cm_logger.setLevel(logging.DEBUG)
    handler = _Capture()
    cm_logger.addHandler(handler)

    # Small EXPLICIT context window so a modest conversation crosses 80%.
    CTX = 3000
    model = get_model("gemini-2.5-flash", context_window_limit=CTX)
    print(f"  model.context_window_limit = {model.context_window_limit} (set explicitly)")

    cm = SummarizingConversationManager(
        summary_ratio=0.5,
        preserve_recent_messages=2,
        proactive_compression={"compression_threshold": 0.8},
    )
    agent = Agent(model=model, conversation_manager=cm, callback_handler=None)

    # Preload history well past 0.8 * 3000 = 2400 tokens with bulky prior turns.
    filler = "Background detail: " + ("context " * 300)  # ~300 tokens each
    for i in range(10):
        agent.messages.append({"role": "user", "content": [{"text": f"Note {i}: {filler}"}]})
        agent.messages.append({"role": "assistant", "content": [{"text": f"Acknowledged note {i}."}]})
    before = len(agent.messages)
    print(f"  preloaded history: {before} messages (well over the {int(0.8 * CTX)}-token threshold)")

    # One real call — the proactive hook should summarize BEFORE the model call.
    result = agent("Given everything above, reply in one short sentence.")
    after = len(agent.messages)

    fired = any("compression threshold exceeded" in m for m in captured)
    cm_logger.removeHandler(handler)

    print(f"  messages after the call: {after}")
    print(f"  proactive-compression hook fired (DEBUG log): {fired}")
    print(f"  reply: {str(result)[:100]!r}")
    if fired or after < before:
        print("  ✓ context compressed PROACTIVELY (before the model call), not after an overflow")
    else:
        print("  (threshold not crossed — increase filler or lower CTX)")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Level 15: Context Management")
    print("=" * 60)
    print("""
Applying Dexter Horthy's Context Engineering principles:
- 40% Rule: Keep utilization under 40% for optimal performance
- Dumb Zone: 40-60% causes hallucinations and forgotten constraints
- XML > JSON: More token-efficient for structured data
- Own Your Context: Treat it as core architecture

8 Iterations:
1. Token Budget Tracker (tiktoken)
2. Rolling Summarization (sliding window)
3. Hierarchical Summarization (age-based)
4. Selective Context Retrieval (budget-aware)
5. Context-Aware Agent (combined)
6. SDK-Native Sliding Window (v1.35 — replaces Iter 2)
7. SDK Token Tracking (v1.35 — replaces Iter 1)
8. Context-Aware Sub-Agents (v1.35 — extends Iter 5)
""")

    # Original iterations
    demo_iteration_1()
    demo_iteration_2()
    demo_iteration_3()
    demo_iteration_4()
    demo_iteration_5()

    # SDK v1.35 iterations
    demo_iteration_6()
    demo_iteration_7()
    demo_iteration_8()

    # SDK v1.42 iteration
    demo_iteration_9()

    # Summary
    print("\n" + "=" * 60)
    print("Summary: Context Management Patterns")
    print("=" * 60)
    print("""
| Iteration | Pattern                | Key Benefit               | SDK v1.35       |
|-----------|------------------------|---------------------------|-----------------|
| 1         | Token Budget Tracker   | Accurate utilization      | → Iter 7 native |
| 2         | Rolling Summarization  | Preserve recent context   | → Iter 6 native |
| 3         | Hierarchical Summary   | Age-based compression     |                 |
| 4         | Selective Retrieval    | Budget-aware memory       |                 |
| 5         | Context-Aware Agent    | Autonomous management     | → Iter 8 extend |
| 6         | SlidingWindowCM        | SDK-native windowing      | ✓ per_turn      |
| 7         | EventLoopMetrics       | Actual token counts       | ✓ no tiktoken   |
| 8         | preserve_context       | Sub-agent memory          | ✓ as_tool()     |

Key evolution (Iter 1-5 → 6-8):
  Hand-rolled code → SDK-native features
  tiktoken estimates → actual provider token counts
  Custom summarization → built-in truncation + windowing
  Isolated sub-agents → preserve_context for shared memory
""")

    # Cleanup
    import shutil

    shutil.rmtree(SESSION_DIR, ignore_errors=True)
    print("\n[Cleanup complete]")

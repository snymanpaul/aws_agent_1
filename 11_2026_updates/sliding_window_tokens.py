"""
Level 58: Sliding Window Per-Turn Control & Token Tracking
===========================================================
Strands SDK v1.35 — conversation management and cost observability.

Goal: Master SlidingWindowConversationManager's per_turn parameter and
      understand token usage tracking including prompt cache metrics.

Depends on: L5 (Sessions), L15 (Context Management)
Unlocks:    L15 Enhanced (SDK-native context mgmt), L59 (Service Tiers)

Iterations:
  1. SlidingWindow Baseline  — default behavior (apply at end only)
  2. per_turn=True           — apply after every model call
  3. per_turn=N              — apply every N calls (balanced)
  4. Token Usage Tracking    — extract Usage TypedDict from responses
  5. Combined                — per_turn + token tracking for cost visibility

Key insight:
    SlidingWindowConversationManager.per_turn controls WHEN context
    trimming happens. Default (False) only trims at overflow. per_turn=True
    trims after every model call, keeping context compact for long-running
    agents. per_turn=N is the sweet spot for production.

Usage:
    uv run python 11_2026_updates/sliding_window_tokens.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands.agent.conversation_manager import SlidingWindowConversationManager
from tools import get_model

model = get_model("haiku")


# Shared tool for generating multi-turn conversations
@tool
def lookup_fact(topic: str) -> str:
    """Look up a fact about the given topic.

    Args:
        topic: Subject to look up
    """
    facts = {
        "python": "Python was created by Guido van Rossum in 1991.",
        "rust": "Rust was first released in 2015 by Mozilla Research.",
        "go": "Go was designed at Google by Robert Griesemer, Rob Pike, and Ken Thompson.",
        "java": "Java was created by James Gosling at Sun Microsystems in 1995.",
        "javascript": "JavaScript was created by Brendan Eich in 10 days in 1995.",
    }
    return facts.get(topic.lower(), f"No facts available for {topic}.")


# =============================================================================
# Iteration 1: SlidingWindow Baseline — End-Only Trimming
# =============================================================================
# Default: per_turn=False. Context only trimmed when it overflows window_size.
# Messages accumulate freely during the conversation.

def demo_baseline():
    """Show default sliding window — messages accumulate until overflow."""
    print("\n" + "=" * 60)
    print("Iteration 1: SlidingWindow Baseline (per_turn=False)")
    print("=" * 60)

    cm = SlidingWindowConversationManager(window_size=20, per_turn=False)

    agent = Agent(
        model=model,
        tools=[lookup_fact],
        conversation_manager=cm,
        system_prompt="You are a concise assistant. Answer in 1 sentence. Use lookup_fact when asked about programming languages.",
        callback_handler=None,
    )

    questions = [
        "Tell me about Python",
        "What about Rust?",
        "And Go?",
        "Compare Python and Rust briefly",
    ]

    for i, q in enumerate(questions, 1):
        agent(q)
        print(f"  Turn {i}: {len(agent.messages)} messages in context")

    print(f"\nFinal message count: {len(agent.messages)}")
    print("✓ Messages grow freely — trimmed only if > window_size")


# =============================================================================
# Iteration 2: per_turn=True — Trim After Every Call
# =============================================================================
# With per_turn=True, the conversation manager applies its window after
# every model call. Context stays compact even across many turns.

def demo_per_turn_true():
    """Show per_turn=True — trim after every model call."""
    print("\n" + "=" * 60)
    print("Iteration 2: per_turn=True — Trim After Every Call")
    print("=" * 60)

    cm = SlidingWindowConversationManager(window_size=10, per_turn=True)

    agent = Agent(
        model=model,
        tools=[lookup_fact],
        conversation_manager=cm,
        system_prompt="You are a concise assistant. Answer in 1 sentence. Use lookup_fact when asked about programming languages.",
        callback_handler=None,
    )

    questions = [
        "Tell me about Python",
        "What about Rust?",
        "And Go?",
        "What about Java?",
        "And JavaScript?",
        "Compare Python and Rust briefly",
    ]

    for i, q in enumerate(questions, 1):
        agent(q)
        print(f"  Turn {i}: {len(agent.messages)} messages in context")

    print(f"\nFinal message count: {len(agent.messages)} (window_size=10)")
    print("✓ Context stays compact — trimmed after each turn")


# =============================================================================
# Iteration 3: per_turn=N — Trim Every N Calls
# =============================================================================
# per_turn=3 means: trim every 3rd model call. This is the production
# sweet spot — less frequent trimming than per_turn=True, but prevents
# unbounded growth.

def demo_per_turn_n():
    """Show per_turn=N — trim every N model calls."""
    print("\n" + "=" * 60)
    print("Iteration 3: per_turn=3 — Trim Every 3rd Call")
    print("=" * 60)

    cm = SlidingWindowConversationManager(window_size=10, per_turn=3)

    agent = Agent(
        model=model,
        tools=[lookup_fact],
        conversation_manager=cm,
        system_prompt="You are a concise assistant. Answer in 1 sentence. Use lookup_fact when asked about programming languages.",
        callback_handler=None,
    )

    questions = [
        "Tell me about Python",
        "What about Rust?",
        "And Go?",          # trim happens here (3rd call)
        "What about Java?",
        "And JavaScript?",
        "Compare all languages",  # trim happens here (6th call)
    ]

    for i, q in enumerate(questions, 1):
        agent(q)
        msg_count = len(agent.messages)
        trim_marker = " ← trim" if i % 3 == 0 else ""
        print(f"  Turn {i}: {msg_count} messages{trim_marker}")

    print(f"\nFinal message count: {len(agent.messages)}")
    print("✓ Periodic trimming — balanced between freshness and efficiency")


# =============================================================================
# Iteration 4: Token Usage Tracking
# =============================================================================
# Agent results expose token usage via the Usage TypedDict:
#   inputTokens, outputTokens, totalTokens
#   cacheReadInputTokens, cacheWriteInputTokens (when prompt caching active)

def demo_token_tracking():
    """Show extracting token usage from agent results."""
    print("\n" + "=" * 60)
    print("Iteration 4: Token Usage Tracking")
    print("=" * 60)

    agent = Agent(
        model=model,
        system_prompt="You are a concise assistant. Answer in 1 sentence.",
        callback_handler=None,
    )

    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_write = 0

    questions = [
        "What is Python?",
        "What is Rust?",
        "What is Go?",
    ]

    for i, q in enumerate(questions, 1):
        result = agent(q)

        # Token usage is on result.metrics (EventLoopMetrics object).
        # Per-invocation usage: metrics.agent_invocations[-1].cycles[-1].usage
        # Accumulated across all calls: metrics.accumulated_usage
        metrics = result.metrics
        invocation = metrics.latest_agent_invocation
        if invocation and invocation.cycles:
            usage = invocation.cycles[-1].usage
        else:
            usage = {}

        input_tokens = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)
        cache_read = usage.get("cacheReadInputTokens", 0)
        cache_write = usage.get("cacheWriteInputTokens", 0)

        total_input += input_tokens
        total_output += output_tokens
        total_cache_read += cache_read
        total_cache_write += cache_write

        print(f"  Turn {i}: in={input_tokens}, out={output_tokens}, "
              f"cache_read={cache_read}, cache_write={cache_write}")

    # Also show accumulated usage from the metrics object
    acc = metrics.accumulated_usage
    print(f"\nAccumulated (from metrics): in={acc.get('inputTokens', 0)}, "
          f"out={acc.get('outputTokens', 0)}")
    print(f"Per-turn totals:            in={total_input}, out={total_output}")
    print(f"Cache: read={total_cache_read}, write={total_cache_write}")

    if total_input > 0 and total_cache_read > 0:
        cache_rate = total_cache_read / total_input * 100
        print(f"Cache hit rate: {cache_rate:.1f}%")

    print("✓ Token tracking enables cost monitoring and cache optimization")


# =============================================================================
# Iteration 5: Combined — per_turn + Token Tracking
# =============================================================================
# Production pattern: periodic trimming with cost observability.

def demo_combined():
    """Show per_turn + token tracking together."""
    print("\n" + "=" * 60)
    print("Iteration 5: Combined — per_turn + Token Tracking")
    print("=" * 60)

    cm = SlidingWindowConversationManager(window_size=12, per_turn=3)

    agent = Agent(
        model=model,
        tools=[lookup_fact],
        conversation_manager=cm,
        system_prompt="You are a concise assistant. Answer in 1 sentence. Use lookup_fact for language facts.",
        callback_handler=None,
    )

    questions = [
        "Tell me about Python",
        "What about Rust?",
        "And Go?",
        "What about Java?",
        "And JavaScript?",
        "Summarize all languages you know about",
    ]

    print(f"{'Turn':<6} {'Messages':<10} {'Input Tok':<12} {'Output Tok':<12} {'Note':<15}")
    print("-" * 55)

    for i, q in enumerate(questions, 1):
        result = agent(q)
        msg_count = len(agent.messages)

        metrics = result.metrics
        invocation = metrics.latest_agent_invocation
        if invocation and invocation.cycles:
            usage = invocation.cycles[-1].usage
        else:
            usage = {}
        input_tok = usage.get("inputTokens", 0)
        output_tok = usage.get("outputTokens", 0)

        note = "← trim" if i % 3 == 0 else ""
        print(f"{i:<6} {msg_count:<10} {input_tok:<12} {output_tok:<12} {note:<15}")

    print("\n✓ per_turn keeps context bounded; token tracking shows the cost impact")
    print("""
    per_turn Decision Guide:
    ┌──────────────┬──────────────────────────────────────────┐
    │ Setting      │ Use When                                 │
    ├──────────────┼──────────────────────────────────────────┤
    │ False        │ Short conversations (< 20 turns)         │
    │ True         │ Streaming/real-time (every turn matters)  │
    │ N (int)      │ Production batch (balance cost/freshness) │
    └──────────────┴──────────────────────────────────────────┘
    """)


# =============================================================================
# Summary
# =============================================================================
# | Feature              | API                              | Purpose          |
# |----------------------|----------------------------------|------------------|
# | Window size          | window_size=40                   | Max messages     |
# | End-only trim        | per_turn=False (default)         | Trim at overflow |
# | Every-turn trim      | per_turn=True                    | Trim each call   |
# | Periodic trim        | per_turn=N                       | Trim every N     |
# | Token tracking       | result.metrics (Usage TypedDict) | Cost visibility  |


if __name__ == "__main__":
    print("=" * 60)
    print("Level 58: Sliding Window + Token Tracking (SDK v1.35)")
    print("=" * 60)

    demo_baseline()
    demo_per_turn_true()
    demo_per_turn_n()
    demo_token_tracking()
    demo_combined()

    print("\n" + "=" * 60)
    print("Summary: Baseline → per_turn=True → per_turn=N → Tokens → Combined")
    print("=" * 60)

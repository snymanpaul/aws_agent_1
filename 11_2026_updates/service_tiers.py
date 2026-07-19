"""
Level 59: Bedrock Service Tiers — Cost/Latency Control
=======================================================
Strands SDK v1.35 — per-request cost/latency trade-offs with service tiers.

Goal: Understand Bedrock's service tier system and build dynamic tier
      routing based on task urgency.

Depends on: L27 (AgentCore Deploy), L28 (SDK Advances), L55 (SLM Routing)
Unlocks:    Production cost optimization

Iterations:
  1. Three Tiers Explained   — default, priority, flex with BedrockModel
  2. Dynamic Tier Selection  — route by task urgency
  3. Cost Modeling           — estimate savings with flex for batch work
  4. Unified Routing         — model selection + tier selection combined

Key insight:
    Service tiers control WHERE your request runs in AWS infrastructure.
    "priority" = dedicated capacity, lowest latency, highest cost.
    "flex" = spare capacity, higher latency, lowest cost (up to 50% cheaper).
    "default" = standard behavior.
    The MODEL stays the same — only the compute tier changes.

NOTE: This lesson requires direct Bedrock access (not LiteLLM proxy).
      Iterations 1-3 use BedrockModel directly. Iteration 4 shows
      how to integrate with the LiteLLM-based routing from L55.

Usage:
    uv run python 11_2026_updates/service_tiers.py
"""

import sys
import os
import time
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Iteration 1: Three Tiers Explained
# =============================================================================
# BedrockModel accepts service_tier in its config. Valid values:
#   "default"  — standard pricing and latency
#   "priority" — premium tier, lower latency, higher cost
#   "flex"     — economy tier, higher latency, lower cost (batch-friendly)

def demo_three_tiers():
    """Show creating BedrockModel with each service tier."""
    print("\n" + "=" * 60)
    print("Iteration 1: Three Tiers Explained")
    print("=" * 60)

    try:
        from strands import Agent
        from strands.models.bedrock import BedrockModel

        model_id = "us.anthropic.claude-sonnet-4-20250514-v1:0"

        # Priority — for user-facing, latency-sensitive requests
        priority_model = BedrockModel(
            model_id=model_id,
            service_tier="priority",
        )

        # Flex — for batch processing, cost-optimized
        flex_model = BedrockModel(
            model_id=model_id,
            service_tier="flex",
        )

        # Default — standard behavior
        default_model = BedrockModel(
            model_id=model_id,
            service_tier="default",
        )

        prompt = "What is 2+2? Answer in one word."

        tiers = [
            ("default", default_model),
            ("priority", priority_model),
            ("flex", flex_model),
        ]

        for tier_name, tier_model in tiers:
            agent = Agent(
                model=tier_model,
                system_prompt="Be extremely concise.",
                callback_handler=None,
            )
            start = time.time()
            result = agent(prompt)
            elapsed = time.time() - start
            print(f"  {tier_name:10s}: {elapsed:.2f}s — {result}")

        print("\n✓ Same model, different tiers — latency/cost trade-off")

    except Exception as e:
        print(f"\n⚠️  Bedrock not available: {e}")
        print("    This iteration requires AWS credentials and Bedrock access.")
        _show_tier_reference()


def _show_tier_reference():
    """Show tier reference when Bedrock isn't available."""
    print("""
    Service Tier Reference:
    ┌──────────┬─────────────────┬──────────────┬──────────────────────┐
    │ Tier     │ Latency         │ Cost         │ Best For             │
    ├──────────┼─────────────────┼──────────────┼──────────────────────┤
    │ default  │ Standard        │ Standard     │ General use          │
    │ priority │ Lowest          │ Premium      │ User-facing, real-   │
    │          │                 │              │ time, chat UIs       │
    │ flex     │ Higher (varies) │ Up to 50%    │ Batch processing,    │
    │          │                 │ cheaper      │ evals, data extract  │
    └──────────┴─────────────────┴──────────────┴──────────────────────┘
    """)


# =============================================================================
# Iteration 2: Dynamic Tier Selection
# =============================================================================
# Route requests to different tiers based on urgency/context.

@dataclass
class TaskRequest:
    """A task with urgency metadata."""
    prompt: str
    urgency: str  # "realtime", "normal", "batch"
    source: str   # "user", "system", "scheduled"


def select_tier(task: TaskRequest) -> str:
    """Select service tier based on task urgency.

    Plain English: Real-time user requests get priority tier,
    scheduled/batch work gets flex tier, everything else gets default.

    Pseudocode:
        if task.urgency == "realtime" and task.source == "user":
            return "priority"
        elif task.urgency == "batch" or task.source == "scheduled":
            return "flex"
        else:
            return "default"
    """
    if task.urgency == "realtime" and task.source == "user":
        return "priority"
    elif task.urgency == "batch" or task.source == "scheduled":
        return "flex"
    else:
        return "default"


def demo_dynamic_routing():
    """Show dynamic tier selection based on task metadata."""
    print("\n" + "=" * 60)
    print("Iteration 2: Dynamic Tier Selection")
    print("=" * 60)

    tasks = [
        TaskRequest("What's my account balance?", "realtime", "user"),
        TaskRequest("Generate monthly report", "batch", "scheduled"),
        TaskRequest("Summarize this document", "normal", "system"),
        TaskRequest("Answer customer question", "realtime", "user"),
        TaskRequest("Run eval suite on 100 prompts", "batch", "system"),
    ]

    print(f"{'Task':<40} {'Urgency':<12} {'Source':<12} {'Tier':<10}")
    print("-" * 74)

    tier_counts = {"default": 0, "priority": 0, "flex": 0}
    for task in tasks:
        tier = select_tier(task)
        tier_counts[tier] += 1
        print(f"{task.prompt:<40} {task.urgency:<12} {task.source:<12} {tier:<10}")

    print(f"\nTier distribution: {tier_counts}")
    print("✓ Dynamic routing optimizes cost without sacrificing UX for real-time tasks")


# =============================================================================
# Iteration 3: Cost Modeling
# =============================================================================
# Flex tier can save up to 50% on batch workloads. Model the impact.

def demo_cost_modeling():
    """Model cost savings from tier-aware routing."""
    print("\n" + "=" * 60)
    print("Iteration 3: Cost Modeling")
    print("=" * 60)

    # Hypothetical pricing (per 1M tokens, input)
    # Real pricing: check AWS Bedrock pricing page
    pricing = {
        "default": {"input": 3.00, "output": 15.00},
        "priority": {"input": 3.60, "output": 18.00},  # ~20% premium
        "flex": {"input": 1.50, "output": 7.50},        # ~50% cheaper
    }

    # Simulated workload: 1000 requests
    workload = {
        "realtime_user": {"count": 200, "avg_input_tokens": 500, "avg_output_tokens": 200, "tier": "priority"},
        "normal_system": {"count": 300, "avg_input_tokens": 800, "avg_output_tokens": 300, "tier": "default"},
        "batch_evals": {"count": 500, "avg_input_tokens": 1000, "avg_output_tokens": 400, "tier": "flex"},
    }

    # Calculate costs with tier-aware routing
    tiered_cost = 0
    default_cost = 0

    print(f"{'Workload':<20} {'Count':<8} {'Tier':<10} {'Tiered $':<12} {'Default $':<12}")
    print("-" * 62)

    for name, w in workload.items():
        tier = w["tier"]
        input_cost = w["count"] * w["avg_input_tokens"] / 1_000_000 * pricing[tier]["input"]
        output_cost = w["count"] * w["avg_output_tokens"] / 1_000_000 * pricing[tier]["output"]
        total = input_cost + output_cost

        default_input = w["count"] * w["avg_input_tokens"] / 1_000_000 * pricing["default"]["input"]
        default_output = w["count"] * w["avg_output_tokens"] / 1_000_000 * pricing["default"]["output"]
        default_total = default_input + default_output

        tiered_cost += total
        default_cost += default_total

        print(f"{name:<20} {w['count']:<8} {tier:<10} ${total:<11.4f} ${default_total:<11.4f}")

    savings = default_cost - tiered_cost
    savings_pct = (savings / default_cost) * 100 if default_cost > 0 else 0

    print(f"\n{'Total':<20} {'1000':<8} {'mixed':<10} ${tiered_cost:<11.4f} ${default_cost:<11.4f}")
    print(f"\nSavings: ${savings:.4f} ({savings_pct:.1f}%)")
    print("✓ Flex tier on batch work drives significant savings")


# =============================================================================
# Iteration 4: Unified Routing — Model + Tier
# =============================================================================
# Combine model selection (which model) with tier selection (which service level)
# for a complete routing strategy.

@dataclass
class RoutingDecision:
    """Combined model + tier routing decision."""
    model_id: str
    service_tier: str
    reason: str


def unified_router(task: TaskRequest) -> RoutingDecision:
    """Select both model and tier based on task characteristics.

    Plain English: Simple batch tasks get small model + flex tier.
    Complex user tasks get large model + priority tier.
    Everything else gets medium model + default tier.

    Pseudocode:
        complexity = estimate_complexity(task.prompt)
        if task.urgency == "batch":
            model = "haiku"
            tier = "flex"
        elif task.urgency == "realtime":
            model = "sonnet"
            tier = "priority"
        else:
            model = "sonnet"
            tier = "default"
    """
    # Simple heuristic: long prompts → complex, short → simple
    is_complex = len(task.prompt) > 50

    if task.urgency == "batch":
        return RoutingDecision(
            model_id="haiku",
            service_tier="flex",
            reason="batch + simple → cheapest option",
        )
    elif task.urgency == "realtime" and is_complex:
        return RoutingDecision(
            model_id="claude-sonnet-4",
            service_tier="priority",
            reason="realtime + complex → best quality + lowest latency",
        )
    elif task.urgency == "realtime":
        return RoutingDecision(
            model_id="haiku",
            service_tier="priority",
            reason="realtime + simple → fast model + low latency",
        )
    else:
        return RoutingDecision(
            model_id="claude-sonnet-4",
            service_tier="default",
            reason="normal → standard quality + standard cost",
        )


def demo_unified_routing():
    """Show combined model + tier routing."""
    print("\n" + "=" * 60)
    print("Iteration 4: Unified Routing — Model + Tier")
    print("=" * 60)

    tasks = [
        TaskRequest("What's 2+2?", "realtime", "user"),
        TaskRequest("Analyze this 500-line codebase for security vulnerabilities and provide a detailed report", "realtime", "user"),
        TaskRequest("Extract names from CSV", "batch", "system"),
        TaskRequest("Summarize quarterly earnings", "normal", "system"),
    ]

    print(f"{'Prompt':<40} {'Model':<18} {'Tier':<10} {'Reason':<35}")
    print("-" * 103)

    for task in tasks:
        decision = unified_router(task)
        prompt_short = task.prompt[:37] + "..." if len(task.prompt) > 40 else task.prompt
        print(f"{prompt_short:<40} {decision.model_id:<18} {decision.service_tier:<10} {decision.reason:<35}")

    print("\n✓ Model + tier routing = 2D optimization (quality × cost)")
    print("""
    Routing Matrix:
    ┌───────────┬──────────────────────┬──────────────────────┐
    │           │ Simple Task          │ Complex Task         │
    ├───────────┼──────────────────────┼──────────────────────┤
    │ Realtime  │ haiku + priority     │ sonnet + priority    │
    │ Normal    │ haiku + default      │ sonnet + default     │
    │ Batch     │ haiku + flex         │ sonnet + flex        │
    └───────────┴──────────────────────┴──────────────────────┘
    """)


# =============================================================================
# Summary
# =============================================================================
# | Tier     | BedrockModel Config          | Use Case                    |
# |----------|------------------------------|-----------------------------|
# | default  | service_tier="default"       | General purpose             |
# | priority | service_tier="priority"      | User-facing, low latency    |
# | flex     | service_tier="flex"          | Batch, evals, data extract  |
# | dynamic  | select_tier(task) → tier     | Mixed workloads             |
# | unified  | model + tier → routing       | Full production routing     |


if __name__ == "__main__":
    print("=" * 60)
    print("Level 59: Bedrock Service Tiers (SDK v1.35)")
    print("=" * 60)

    demo_three_tiers()
    demo_dynamic_routing()
    demo_cost_modeling()
    demo_unified_routing()

    print("\n" + "=" * 60)
    print("Summary: Tiers → Dynamic → Cost Model → Unified Routing")
    print("=" * 60)

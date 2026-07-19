"""
Level 7: Swarm Pattern
======================
Peer-to-peer agent collaboration with autonomous handoffs.

Key Concepts:
- Agents autonomously decide when to hand off to other agents
- Shared context available to all agents in the swarm
- No single orchestrator - agents coordinate peer-to-peer
- Handoff detection prevents infinite loops
- MultiAgentPlugin (SDK v1.42): orchestrator-level lifecycle hooks
  (Before/AfterNodeCallEvent) — see MonitoringPlugin below; contrast with the
  agent-level Plugin in L30 (11_platform/skills_plugin.py)

Difference from Level 6 (Agents-as-Tools):
- Level 6: Hierarchical - orchestrator explicitly calls specialists
- Level 7: Peer-to-peer - agents autonomously hand off to each other

Run: uv run python 03_multi_agent/swarm_example.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent
from strands.multiagent import Swarm
from strands.plugins import MultiAgentPlugin, hook
from strands.hooks import AfterNodeCallEvent, BeforeNodeCallEvent

from tools import get_model

# Gemini 2.5 Flash, direct (Anthropic budget paused). The swarm coordinates via
# handoffs regardless of the underlying model; both roles use the same model.
fast_model = get_model("gemini-2.5-flash")
model = fast_model


# =============================================================================
# Orchestrator-level monitoring (SDK v1.42 — MultiAgentPlugin)
# =============================================================================
# MultiAgentPlugin is the ORCHESTRATOR-level counterpart to the agent-level
# Plugin used by L30 (11_platform/skills_plugin.py, AgentSkills):
#   * L30 AgentSkills : Plugin   -> Agent(plugins=[...]); hooks BeforeInvocationEvent;
#                       MAY register @tool methods; scope = a single agent.
#   * MonitoringPlugin: MultiAgentPlugin -> Swarm([...], plugins=[...]); hooks the
#                       NODE lifecycle (Before/AfterNodeCallEvent); NO @tool methods
#                       (orchestrators have no tool registry); scope = every node
#                       (each agent's turn) in the swarm/graph.
class MonitoringPlugin(MultiAgentPlugin):
    """Log each node's lifecycle as the swarm hands off between agents."""

    name = "swarm-monitor"

    def __init__(self) -> None:
        super().__init__()  # base discovers @hook methods into self.hooks
        self.timeline: list[str] = []

    @hook
    def on_before_node(self, event: BeforeNodeCallEvent) -> None:
        self.timeline.append(f"-> {event.node_id}")
        print(f"  [monitor] -> node '{event.node_id}' starting")

    @hook
    def on_after_node(self, event: AfterNodeCallEvent) -> None:
        self.timeline.append(f"<- {event.node_id}")
        print(f"  [monitor] <- node '{event.node_id}' completed")


monitor = MonitoringPlugin()


# =============================================================================
# Software Development Team Swarm
# =============================================================================

# Agent 1: Requirements Researcher
researcher = Agent(
    name="researcher",
    model=fast_model,
    system_prompt="""You are a requirements researcher on a software development team.

Your job is to:
1. Analyze and clarify requirements
2. Identify key features and constraints
3. Research best practices for the problem domain

When you have gathered enough requirements, hand off to the architect.
Be concise - summarize findings in bullet points."""
)

# Agent 2: Solution Architect
architect = Agent(
    name="architect",
    model=fast_model,
    system_prompt="""You are a solution architect on a software development team.

Your job is to:
1. Design the high-level solution structure
2. Choose appropriate patterns and technologies
3. Define interfaces and data flow

When the design is ready, hand off to the coder.
Be concise - use diagrams (ASCII) where helpful."""
)

# Agent 3: Implementation Coder
coder = Agent(
    name="coder",
    model=fast_model,
    system_prompt="""You are an implementation coder on a software development team.

Your job is to:
1. Implement the solution based on the architect's design
2. Write clean, well-structured code
3. Include basic error handling

When implementation is complete, hand off to the reviewer.
Output actual code, not pseudocode."""
)

# Agent 4: Code Reviewer
reviewer = Agent(
    name="reviewer",
    model=fast_model,
    system_prompt="""You are a code reviewer on a software development team.

Your job is to:
1. Review the implemented code for bugs and issues
2. Check for best practices and security concerns
3. Provide constructive feedback

IMPORTANT: You are the FINAL step in the workflow.
- Provide your review summary and conclude the task
- Do NOT hand off to other agents - complete the review yourself
- Only suggest improvements in your review, don't request implementation"""
)


# =============================================================================
# Create the Swarm
# =============================================================================

swarm = Swarm(
    [researcher, architect, coder, reviewer],  # Positional: list of agents
    entry_point=researcher,  # Start with requirements research
    max_handoffs=10,         # Limit to prevent infinite loops
    max_iterations=15,       # Cap total iterations
    execution_timeout=300.0, # 5-minute maximum
    node_timeout=60.0,       # 1-minute per-agent limit
    # Ping-pong prevention: require 3 unique agents in last 5 handoffs
    repetitive_handoff_detection_window=5,
    repetitive_handoff_min_unique_agents=3,
    plugins=[monitor],       # orchestrator-level lifecycle monitoring (v1.42)
)


# =============================================================================
# Demo
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Level 7: Swarm Pattern")
    print("=" * 60)
    print()
    print("Software Development Team Swarm:")
    print("  researcher -> architect -> coder -> reviewer")
    print()
    print("Task: Build a simple function")
    print("=" * 60)
    print()

    # Simple task to demonstrate handoffs
    result = swarm("""
Build a Python function called 'validate_email' that:
- Takes an email string as input
- Returns True if valid, False if invalid
- Uses regex for validation
- Handles edge cases

Each team member should contribute their expertise.
""")

    print()
    print("=" * 60)
    print("Swarm Execution Complete")
    print("=" * 60)

    # Show execution details
    if hasattr(result, 'node_history') and result.node_history:
        print(f"Agent sequence: {[node.node_id for node in result.node_history]}")
    if hasattr(result, 'status'):
        print(f"Status: {result.status}")
    if hasattr(result, 'execution_time'):
        print(f"Execution time: {result.execution_time}ms")

    # Orchestrator-level monitoring captured by the MultiAgentPlugin
    print(f"\n[monitor] node lifecycle ({len(monitor.timeline)} events captured by the plugin):")
    print("  " + " ".join(monitor.timeline))

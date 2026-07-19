"""
Level 8: Graph Workflow Pattern
===============================
Deterministic DAG-based agent orchestration with explicit dependencies.

Key Concepts:
- Nodes: Agents or custom executors
- Edges: Dependencies with optional conditions
- GraphBuilder: Fluent API for construction
- Deterministic: Follows defined paths, not autonomous handoffs
- MultiAgentPlugin (SDK v1.42): node-lifecycle hooks attached via
  GraphBuilder.set_plugins([...]) — see MonitoringPlugin below

Difference from Level 7 (Swarm):
- Level 7: Agents autonomously decide handoffs (peer-to-peer)
- Level 8: Developer defines explicit node dependencies (DAG)

Run: uv run python 03_multi_agent/graph_workflow.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent
from strands.multiagent import GraphBuilder
from strands.plugins import MultiAgentPlugin, hook
from strands.hooks import AfterNodeCallEvent, BeforeNodeCallEvent

from tools import get_model

# Gemini 2.5 Flash, direct (Anthropic budget paused).
fast_model = get_model("gemini-2.5-flash")
model = fast_model


# =============================================================================
# Orchestrator-level monitoring (SDK v1.42 — MultiAgentPlugin)
# =============================================================================
# Same MultiAgentPlugin contract as the Swarm in L7: @hook methods on the NODE
# lifecycle, attached to the orchestrator. For a Graph it is wired via
# GraphBuilder.set_plugins([...]) (vs Swarm(..., plugins=[...])). Contrast with
# the agent-level Plugin in L30 (11_platform/skills_plugin.py).
class MonitoringPlugin(MultiAgentPlugin):
    """Log each node's lifecycle as the graph advances through the DAG."""

    name = "graph-monitor"

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
# Document Processing Pipeline
# =============================================================================
# Graph structure:
#
#   [extractor] --> [analyzer] --> [summarizer] --> [quality_checker]
#
# Each node receives output from previous node(s)

# Node 1: Extract key information
extractor = Agent(
    name="extractor",
    model=fast_model,
    system_prompt="""You are an information extraction specialist.

Your job is to:
1. Identify and extract key facts, data points, and important information
2. Structure the extracted information clearly
3. Note any missing or unclear information

Output format: Bullet points of extracted information.
Be thorough but concise."""
)

# Node 2: Analyze extracted information
analyzer = Agent(
    name="analyzer",
    model=fast_model,
    system_prompt="""You are a data analysis specialist.

Your job is to:
1. Analyze the extracted information from the previous step
2. Identify patterns, relationships, and insights
3. Highlight any concerns or notable findings

Output format: Analysis with clear sections.
Build on the previous node's output."""
)

# Node 3: Create summary
summarizer = Agent(
    name="summarizer",
    model=fast_model,
    system_prompt="""You are a summarization specialist.

Your job is to:
1. Create a concise executive summary
2. Highlight the most important points
3. Include key recommendations if applicable

Output format: 3-5 sentence summary followed by key points.
Synthesize insights from previous nodes."""
)

# Node 4: Quality check
quality_checker = Agent(
    name="quality_checker",
    model=fast_model,
    system_prompt="""You are a quality assurance specialist.

Your job is to:
1. Review the entire pipeline output for accuracy
2. Check for completeness and consistency
3. Provide a quality score (1-10) with brief justification

Output format:
- Quality Score: X/10
- Assessment: Brief evaluation
- Final Output: The polished summary

This is the FINAL step. Provide the completed deliverable."""
)


# =============================================================================
# Build the Graph
# =============================================================================

builder = GraphBuilder()

# Add nodes
builder.add_node(extractor, "extract")
builder.add_node(analyzer, "analyze")
builder.add_node(summarizer, "summarize")
builder.add_node(quality_checker, "quality_check")

# Define edges (dependencies)
builder.add_edge("extract", "analyze")      # analyze depends on extract
builder.add_edge("analyze", "summarize")    # summarize depends on analyze
builder.add_edge("summarize", "quality_check")  # quality_check depends on summarize

# Set entry point
builder.set_entry_point("extract")

# Set safety limits (important for cyclic graphs, good practice for all)
builder.set_max_node_executions(10)   # Cap total node executions
builder.set_execution_timeout(300)    # 5-minute maximum
builder.set_node_timeout(60)          # 1-minute per-node limit

# Orchestrator-level lifecycle monitoring (v1.42) — attached to the Graph
builder.set_plugins([monitor])

# Build the graph
graph = builder.build()


# =============================================================================
# Demo
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Level 8: Graph Workflow Pattern")
    print("=" * 60)
    print()
    print("Document Processing Pipeline:")
    print("  extract --> analyze --> summarize --> quality_check")
    print()
    print("=" * 60)
    print()

    # Sample document for processing
    sample_document = """
    Q3 2024 Financial Report - TechCorp Inc.

    Revenue: $45.2M (up 23% YoY)
    Operating Expenses: $32.1M (up 15% YoY)
    Net Income: $8.7M (up 45% YoY)

    Key Highlights:
    - Cloud services revenue grew 45% to $18M
    - Enterprise clients increased from 150 to 210
    - Customer retention rate: 94%
    - New product launch planned for Q4

    Challenges:
    - Supply chain costs increased 12%
    - Hiring slower than projected (85 vs 120 target)
    - Competition intensifying in core markets

    Outlook:
    - Q4 revenue projected at $48-52M
    - Planning expansion into European markets
    - R&D investment increasing by 20%
    """

    print("Processing document...")
    print("-" * 60)
    print(sample_document)
    print("-" * 60)
    print()

    # Execute the graph
    result = graph(f"Process this document:\n{sample_document}")

    print()
    print("=" * 60)
    print("Graph Execution Complete")
    print("=" * 60)

    # Show execution details
    if hasattr(result, 'node_history') and result.node_history:
        print(f"Node sequence: {[node.node_id for node in result.node_history]}")
    if hasattr(result, 'status'):
        print(f"Status: {result.status}")
    if hasattr(result, 'execution_time'):
        print(f"Execution time: {result.execution_time}ms")

    # Orchestrator-level monitoring captured by the MultiAgentPlugin
    print(f"\n[monitor] node lifecycle ({len(monitor.timeline)} events captured by the plugin):")
    print("  " + " ".join(monitor.timeline))

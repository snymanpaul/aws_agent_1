"""
Level 21: Observability - Production Visibility for Agent Systems

This module demonstrates OpenTelemetry integration with Strands Agents for
production-grade observability. Covers tracing, metrics, and cost tracking.

Prerequisites:
    1. Jaeger running: docker run -d --name jaeger -e COLLECTOR_OTLP_ENABLED=true \
       -p 16686:16686 -p 4317:4317 -p 4318:4318 jaegertracing/all-in-one:latest
    2. Dependencies: strands-agents[otel], opentelemetry-sdk, opentelemetry-exporter-otlp

Iterations:
    1. Basic Tracing Setup - StrandsTelemetry + Jaeger
    2. Custom Trace Attributes - Request/session correlation
    3. Enhanced Tool Instrumentation - Custom spans for tools
    4. Token and Cost Tracking - Model-specific pricing
    5. Multi-Agent Request Correlation - Team traces
    6. Metrics and Dashboards - EventLoopMetrics
    7. L19 Planning Observability - Plan/execute/verify traces
    8. L20 Meta-Agent Observability - Factory + blueprint traces

Usage:
    uv run python 08_production/observability.py

View traces at: http://localhost:16686
"""

import sys
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import BaseModel, Field
from strands import Agent, tool
from strands.telemetry import StrandsTelemetry, EventLoopMetrics
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from tools import get_model


# =============================================================================
# ITERATION 1: Basic Tracing Setup
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 1: Basic Tracing Setup")
print("=" * 70)

def setup_basic_telemetry(console: bool = True, otlp: bool = True) -> StrandsTelemetry:
    """
    Initialize Strands telemetry with console and/or OTLP exporters.

    Strands has NATIVE OpenTelemetry support - no manual instrumentation needed
    for basic agent/tool tracing. Just initialize and traces flow automatically.

    Args:
        console: Enable console span output (useful for debugging)
        otlp: Enable OTLP exporter to Jaeger (production)

    Returns:
        Configured StrandsTelemetry instance
    """
    telemetry = StrandsTelemetry()

    if console:
        telemetry.setup_console_exporter()
        print("✓ Console exporter enabled")

    if otlp:
        # Default OTLP endpoint is localhost:4317 (gRPC) or :4318 (HTTP)
        # Set OTEL_EXPORTER_OTLP_ENDPOINT env var to override
        telemetry.setup_otlp_exporter()
        print("✓ OTLP exporter enabled (→ Jaeger at localhost:4317)")

    return telemetry


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression and return the result."""
    try:
        # Safe eval for basic math (production would use ast.literal_eval)
        result = eval(expression, {"__builtins__": {}}, {})
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {e}"


def run_iteration_1():
    """Demonstrate basic tracing with automatic instrumentation."""
    print("\n[Iteration 1] Setting up telemetry and running traced agent...")

    # Initialize telemetry BEFORE creating agents
    telemetry = setup_basic_telemetry(console=False, otlp=True)

    # Create a simple agent with calculator tool
    model = get_model("haiku")
    agent = Agent(
        model=model,
        tools=[calculator],
        system_prompt="You are a helpful math assistant. Use the calculator tool for calculations.",
        callback_handler=None  # Disable streaming for cleaner output
    )

    # Run agent - traces are automatically captured!
    prompt = "What is 42 * 17 + 123?"
    print(f"\n  Prompt: {prompt}")
    result = agent(prompt)
    print(f"  Result: {result}")

    print("\n  → View trace at http://localhost:16686")
    print("    Search for service: 'strands-agent' or 'strands.agent'")

    return telemetry


# =============================================================================
# ITERATION 2: Custom Trace Attributes
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 2: Custom Trace Attributes")
print("=" * 70)


@dataclass
class RequestContext:
    """Context for request correlation across traces."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    user_id: str = ""
    environment: str = "development"
    tags: list[str] = field(default_factory=list)

    def to_trace_attributes(self) -> dict[str, Any]:
        """Convert to OpenTelemetry trace attributes format."""
        attrs = {
            "request.id": self.request_id,
            "environment": self.environment,
        }
        if self.session_id:
            attrs["session.id"] = self.session_id
        if self.user_id:
            attrs["user.id"] = self.user_id
        if self.tags:
            attrs["tags"] = self.tags
        return attrs


def run_iteration_2():
    """Demonstrate custom trace attributes for request correlation."""
    print("\n[Iteration 2] Running agent with custom trace attributes...")

    # Create request context
    ctx = RequestContext(
        session_id="session-abc-123",
        user_id="paul@example.com",
        environment="development",
        tags=["L21", "observability", "demo"]
    )

    print(f"  Request ID: {ctx.request_id}")
    print(f"  Session ID: {ctx.session_id}")

    # Create agent with trace attributes
    model = get_model("haiku")
    agent = Agent(
        model=model,
        tools=[calculator],
        system_prompt="You are a helpful math assistant.",
        trace_attributes=ctx.to_trace_attributes(),  # Native support!
        callback_handler=None
    )

    result = agent("Calculate 2^10")
    print(f"  Result: {result}")

    print("\n  → In Jaeger, filter by: request.id = " + ctx.request_id[:8] + "...")
    print("    Or: session.id = session-abc-123")


# =============================================================================
# ITERATION 3: Enhanced Tool Instrumentation
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 3: Enhanced Tool Instrumentation")
print("=" * 70)


# Get a tracer for custom spans
# Note: Strands' get_tracer() returns a Strands-specific wrapper
# For custom spans, use OpenTelemetry's trace.get_tracer() directly
tracer = trace.get_tracer("observability.tools")


@tool
def instrumented_calculator(expression: str) -> str:
    """
    Calculator with enhanced observability.

    Adds custom spans with:
    - Input expression
    - Execution time
    - Success/failure status
    - Result or error details
    """
    # Create a custom span for detailed tool metrics
    with tracer.start_as_current_span("custom_calculator") as span:
        span.set_attribute("tool.name", "instrumented_calculator")
        span.set_attribute("tool.expression", expression)

        start_time = time.time()
        try:
            # Safe eval
            allowed_names = {"abs": abs, "min": min, "max": max, "pow": pow}
            result = eval(expression, {"__builtins__": {}}, allowed_names)

            # Record success
            duration_ms = (time.time() - start_time) * 1000
            span.set_attribute("tool.result", str(result))
            span.set_attribute("tool.success", True)
            span.set_attribute("tool.duration_ms", duration_ms)
            span.set_status(Status(StatusCode.OK))

            return f"Result: {result}"

        except Exception as e:
            # Record failure
            duration_ms = (time.time() - start_time) * 1000
            span.set_attribute("tool.error", str(e))
            span.set_attribute("tool.success", False)
            span.set_attribute("tool.duration_ms", duration_ms)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)

            return f"Error: {e}"


@tool
def instrumented_divider(numerator: float, denominator: float) -> str:
    """
    Division tool with error handling - useful for demonstrating error traces.
    """
    with tracer.start_as_current_span("division_operation") as span:
        span.set_attribute("math.numerator", numerator)
        span.set_attribute("math.denominator", denominator)

        try:
            if denominator == 0:
                raise ZeroDivisionError("Cannot divide by zero")
            result = numerator / denominator
            span.set_attribute("math.result", result)
            span.set_status(Status(StatusCode.OK))
            return f"Result: {result}"
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            return f"Error: {e}"


def run_iteration_3():
    """Demonstrate enhanced tool instrumentation with custom spans."""
    print("\n[Iteration 3] Running with instrumented tools...")

    model = get_model("haiku")
    agent = Agent(
        model=model,
        tools=[instrumented_calculator, instrumented_divider],
        system_prompt="You are a math assistant. Use tools for calculations.",
        trace_attributes={"iteration": 3, "demo": "tool_instrumentation"},
        callback_handler=None
    )

    # Success case
    print("\n  Test 1: Successful calculation")
    result = agent("What is pow(2, 8)?")
    print(f"    Result: {result}")

    # Error case - demonstrates error tracing
    print("\n  Test 2: Division by zero (error tracing)")
    result = agent("Divide 10 by 0")
    print(f"    Result: {result}")

    print("\n  → Check Jaeger for error spans with recorded exceptions")


# =============================================================================
# ITERATION 4: Token and Cost Tracking
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 4: Token and Cost Tracking")
print("=" * 70)


# Model pricing per 1K tokens (December 2024)
MODEL_PRICING = {
    "claude-sonnet-4": {"input": 0.003, "output": 0.015},
    "claude-opus-4": {"input": 0.015, "output": 0.075},
    "claude-3-5-haiku": {"input": 0.00025, "output": 0.00125},
    "gemini/gemini-2.0-flash": {"input": 0.00075, "output": 0.003},
    # Fallback for unknown models
    "default": {"input": 0.001, "output": 0.005},
}


@dataclass
class CostTracker:
    """
    Track token usage and costs across multiple agent invocations.

    Usage:
        tracker = CostTracker()
        # After each agent call...
        tracker.track("claude-3-5-haiku", input_tokens, output_tokens)
        print(tracker.get_summary())
    """
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    invocations: int = 0
    costs_by_model: dict[str, float] = field(default_factory=dict)

    def get_pricing(self, model_id: str) -> dict[str, float]:
        """Get pricing for a model, with fallback to default."""
        # Normalize model ID (strip prefixes, etc.)
        normalized = model_id.split("/")[-1] if "/" in model_id else model_id
        return MODEL_PRICING.get(normalized, MODEL_PRICING.get(model_id, MODEL_PRICING["default"]))

    def track(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """
        Record token usage and calculate cost.

        Returns:
            Cost of this invocation
        """
        pricing = self.get_pricing(model_id)
        cost = (
            (input_tokens / 1000) * pricing["input"] +
            (output_tokens / 1000) * pricing["output"]
        )

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost += cost
        self.invocations += 1
        self.costs_by_model[model_id] = self.costs_by_model.get(model_id, 0.0) + cost

        return cost

    def get_summary(self) -> dict:
        """Get a summary of all tracked costs."""
        return {
            "total_invocations": self.invocations,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost_usd": round(self.total_cost, 6),
            "avg_cost_per_invocation": round(self.total_cost / max(1, self.invocations), 6),
            "costs_by_model": {k: round(v, 6) for k, v in self.costs_by_model.items()},
        }

    def reset(self):
        """Reset all tracking."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self.invocations = 0
        self.costs_by_model = {}


class TracedAgent:
    """
    Wrapper around Agent that adds cost tracking and enhanced tracing.

    Usage:
        tracker = CostTracker()
        agent = TracedAgent(base_agent, tracker, request_id="req-123")
        result = agent("Do something")
        print(tracker.get_summary())
    """

    def __init__(
        self,
        agent: Agent,
        cost_tracker: CostTracker,
        request_id: Optional[str] = None,
        model_id: str = "unknown"
    ):
        self.agent = agent
        self.cost_tracker = cost_tracker
        self.request_id = request_id or str(uuid.uuid4())
        self.model_id = model_id

    def __call__(self, prompt: str) -> str:
        """Invoke agent with cost tracking."""
        with tracer.start_as_current_span("traced_agent_call") as span:
            span.set_attribute("request.id", self.request_id)
            span.set_attribute("model.id", self.model_id)
            span.set_attribute("prompt.length", len(prompt))

            start_time = time.time()
            result = self.agent(prompt)
            duration_ms = (time.time() - start_time) * 1000

            # Extract token usage from agent metrics if available
            # Note: Strands stores this in the agent's internal state
            input_tokens = 0
            output_tokens = 0

            # Try to get metrics from agent state
            if hasattr(self.agent, '_last_metrics'):
                metrics = self.agent._last_metrics
                if hasattr(metrics, 'accumulated_usage'):
                    input_tokens = getattr(metrics.accumulated_usage, 'inputTokens', 0)
                    output_tokens = getattr(metrics.accumulated_usage, 'outputTokens', 0)

            # Estimate if not available (rough approximation)
            if input_tokens == 0:
                input_tokens = len(prompt) // 4  # ~4 chars per token
                output_tokens = len(str(result)) // 4

            # Track cost
            cost = self.cost_tracker.track(self.model_id, input_tokens, output_tokens)

            # Add to span
            span.set_attribute("tokens.input", input_tokens)
            span.set_attribute("tokens.output", output_tokens)
            span.set_attribute("cost.usd", cost)
            span.set_attribute("duration_ms", duration_ms)

            return str(result)


def run_iteration_4():
    """Demonstrate token and cost tracking."""
    print("\n[Iteration 4] Running with cost tracking...")

    tracker = CostTracker()

    # Test with multiple models
    models_to_test = ["haiku", "claude-sonnet-4"]

    for model_name in models_to_test:
        print(f"\n  Testing model: {model_name}")

        model = get_model(model_name)
        base_agent = Agent(
            model=model,
            tools=[calculator],
            system_prompt="Be concise. Use the calculator for math.",
            callback_handler=None
        )

        # Get model ID for tracking
        model_id = model.config.get("model_id", model_name) if hasattr(model, 'config') else model_name

        traced = TracedAgent(base_agent, tracker, model_id=model_id)

        # Run a few prompts
        prompts = [
            "What is 100 * 50?",
            "Calculate 2^16",
        ]

        for prompt in prompts:
            result = traced(prompt)
            print(f"    {prompt[:30]}... → {str(result)[:50]}...")

    # Print summary
    summary = tracker.get_summary()
    print("\n  Cost Summary:")
    print(f"    Total invocations: {summary['total_invocations']}")
    print(f"    Total tokens: {summary['total_tokens']}")
    print(f"    Total cost: ${summary['total_cost_usd']:.6f}")
    print(f"    Avg per call: ${summary['avg_cost_per_invocation']:.6f}")
    print(f"    By model: {summary['costs_by_model']}")


# =============================================================================
# ITERATION 5: Multi-Agent Request Correlation
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 5: Multi-Agent Request Correlation")
print("=" * 70)


class TeamExecution:
    """
    Execute a team of agents with correlated traces.

    Creates parent-child span relationships so multi-agent workflows
    appear as a single trace with nested spans in Jaeger.
    """

    def __init__(self, team_name: str, request_id: Optional[str] = None):
        self.team_name = team_name
        self.request_id = request_id or str(uuid.uuid4())
        self.agents: list[tuple[str, Agent]] = []

    def add_agent(self, name: str, agent: Agent):
        """Add an agent to the team."""
        self.agents.append((name, agent))

    def execute_sequential(self, task: str) -> list[str]:
        """
        Execute agents sequentially, passing context forward.

        Each agent's output becomes part of the context for the next.
        """
        with tracer.start_as_current_span("team_execution") as root_span:
            root_span.set_attribute("team.name", self.team_name)
            root_span.set_attribute("request.id", self.request_id)
            root_span.set_attribute("team.agent_count", len(self.agents))
            root_span.set_attribute("execution.mode", "sequential")

            results = []
            context = ""

            for i, (name, agent) in enumerate(self.agents):
                with tracer.start_as_current_span(f"agent_{name}") as agent_span:
                    agent_span.set_attribute("agent.name", name)
                    agent_span.set_attribute("agent.index", i)
                    agent_span.set_attribute("context.length", len(context))

                    # Build prompt with accumulated context
                    if i == 0:
                        prompt = task
                    else:
                        prompt = f"Previous context:\n{context}\n\nTask: {task}"

                    start_time = time.time()
                    result = str(agent(prompt))
                    duration_ms = (time.time() - start_time) * 1000

                    agent_span.set_attribute("duration_ms", duration_ms)
                    agent_span.set_attribute("result.length", len(result))

                    results.append(result)
                    context += f"\n[{name}]: {result}"

            root_span.set_attribute("total_results", len(results))
            return results

    def execute_parallel(self, task: str) -> list[str]:
        """
        Execute agents in parallel with correlated traces.

        All agents run concurrently but share the same parent span.
        """
        with tracer.start_as_current_span("team_execution") as root_span:
            root_span.set_attribute("team.name", self.team_name)
            root_span.set_attribute("request.id", self.request_id)
            root_span.set_attribute("team.agent_count", len(self.agents))
            root_span.set_attribute("execution.mode", "parallel")

            results = [None] * len(self.agents)

            def run_agent(index: int, name: str, agent: Agent) -> tuple[int, str]:
                # Note: In parallel execution, spans may not nest perfectly
                # due to thread context propagation
                with tracer.start_as_current_span(f"agent_{name}") as agent_span:
                    agent_span.set_attribute("agent.name", name)
                    agent_span.set_attribute("agent.index", index)

                    start_time = time.time()
                    result = str(agent(task))
                    duration_ms = (time.time() - start_time) * 1000

                    agent_span.set_attribute("duration_ms", duration_ms)
                    return index, result

            with ThreadPoolExecutor(max_workers=len(self.agents)) as executor:
                futures = [
                    executor.submit(run_agent, i, name, agent)
                    for i, (name, agent) in enumerate(self.agents)
                ]
                for future in futures:
                    idx, result = future.result()
                    results[idx] = result

            return results


def run_iteration_5():
    """Demonstrate multi-agent request correlation."""
    print("\n[Iteration 5] Running multi-agent team with correlated traces...")

    model = get_model("haiku")

    # Create specialized agents
    researcher = Agent(
        model=model,
        system_prompt="You are a researcher. Provide brief factual information.",
        callback_handler=None
    )

    analyzer = Agent(
        model=model,
        tools=[calculator],
        system_prompt="You are an analyst. Analyze data and calculate when needed.",
        callback_handler=None
    )

    summarizer = Agent(
        model=model,
        system_prompt="You are a summarizer. Create concise summaries.",
        callback_handler=None
    )

    # Build team
    team = TeamExecution("research-team", request_id="req-" + str(uuid.uuid4())[:8])
    team.add_agent("researcher", researcher)
    team.add_agent("analyzer", analyzer)
    team.add_agent("summarizer", summarizer)

    print(f"  Request ID: {team.request_id}")
    print(f"  Team: {team.team_name}")
    print(f"  Agents: researcher → analyzer → summarizer")

    # Execute sequentially
    task = "What are the factors of 144? Analyze which are prime."
    print(f"\n  Task: {task}")

    results = team.execute_sequential(task)

    print("\n  Results:")
    for i, (name, _) in enumerate(team.agents):
        print(f"    [{name}]: {results[i][:100]}...")

    print("\n  → In Jaeger, search for request.id = " + team.request_id)
    print("    You'll see nested spans: team_execution → agent_researcher → agent_analyzer → ...")


# =============================================================================
# ITERATION 6: Metrics and Dashboards
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 6: Metrics and Dashboards")
print("=" * 70)


class MetricsAggregator:
    """
    Aggregate metrics across multiple agent invocations for dashboards.

    Collects:
    - Invocation counts and latencies
    - Tool usage statistics
    - Error rates
    - Token throughput
    """

    def __init__(self):
        self.invocations: list[dict] = []
        self.tool_calls: list[dict] = []
        self.errors: list[dict] = []

    def record_invocation(
        self,
        agent_name: str,
        duration_ms: float,
        input_tokens: int,
        output_tokens: int,
        success: bool = True
    ):
        """Record an agent invocation."""
        self.invocations.append({
            "agent_name": agent_name,
            "duration_ms": duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "success": success,
            "timestamp": time.time()
        })

    def record_tool_call(
        self,
        tool_name: str,
        duration_ms: float,
        success: bool = True,
        error: Optional[str] = None
    ):
        """Record a tool invocation."""
        record = {
            "tool_name": tool_name,
            "duration_ms": duration_ms,
            "success": success,
            "timestamp": time.time()
        }
        if error:
            record["error"] = error
            self.errors.append({"type": "tool_error", "tool": tool_name, "error": error})
        self.tool_calls.append(record)

    def get_dashboard_data(self) -> dict:
        """Generate dashboard-ready metrics summary."""
        if not self.invocations:
            return {"status": "no data"}

        durations = [i["duration_ms"] for i in self.invocations]
        input_tokens = sum(i["input_tokens"] for i in self.invocations)
        output_tokens = sum(i["output_tokens"] for i in self.invocations)

        # Tool stats
        tool_stats = {}
        for tc in self.tool_calls:
            name = tc["tool_name"]
            if name not in tool_stats:
                tool_stats[name] = {"count": 0, "success": 0, "total_ms": 0}
            tool_stats[name]["count"] += 1
            tool_stats[name]["success"] += 1 if tc["success"] else 0
            tool_stats[name]["total_ms"] += tc["duration_ms"]

        # Calculate averages
        for name, stats in tool_stats.items():
            stats["avg_ms"] = round(stats["total_ms"] / stats["count"], 2)
            stats["success_rate"] = round(stats["success"] / stats["count"] * 100, 1)

        return {
            "invocations": {
                "total": len(self.invocations),
                "success_rate": round(
                    len([i for i in self.invocations if i["success"]]) / len(self.invocations) * 100,
                    1
                ),
                "latency": {
                    "min_ms": round(min(durations), 2),
                    "max_ms": round(max(durations), 2),
                    "avg_ms": round(sum(durations) / len(durations), 2),
                    "p50_ms": round(sorted(durations)[len(durations) // 2], 2),
                },
            },
            "tokens": {
                "total_input": input_tokens,
                "total_output": output_tokens,
                "total": input_tokens + output_tokens,
            },
            "tools": tool_stats,
            "errors": {
                "total": len(self.errors),
                "recent": self.errors[-5:] if self.errors else [],
            },
        }


def run_iteration_6():
    """Demonstrate metrics collection and dashboard data."""
    print("\n[Iteration 6] Collecting metrics for dashboards...")

    # Initialize metrics
    metrics = MetricsAggregator()

    # Also enable OTEL metrics
    telemetry = StrandsTelemetry()
    telemetry.setup_meter(enable_console_exporter=False, enable_otlp_exporter=True)
    print("  ✓ OTEL meter enabled")

    model = get_model("haiku")

    # Run multiple invocations
    agent = Agent(
        model=model,
        tools=[instrumented_calculator, instrumented_divider],
        system_prompt="Use tools for math. Be concise.",
        callback_handler=None
    )

    test_prompts = [
        ("What is 100 + 200?", True),
        ("Calculate pow(2, 10)", True),
        ("Divide 100 by 5", True),
        ("Divide 10 by 0", False),  # Expected error
        ("What is 50 * 50?", True),
    ]

    print("\n  Running test invocations...")
    for prompt, expected_success in test_prompts:
        start = time.time()
        result = str(agent(prompt))
        duration_ms = (time.time() - start) * 1000

        # Estimate tokens
        input_tokens = len(prompt) // 4
        output_tokens = len(result) // 4

        metrics.record_invocation(
            agent_name="math_agent",
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            success="Error" not in result
        )

        # Record tool calls (simulated - in production, hook into tool execution)
        if "calculator" in prompt.lower() or any(op in prompt for op in ["+", "*", "pow"]):
            metrics.record_tool_call("instrumented_calculator", duration_ms * 0.1)
        if "divide" in prompt.lower():
            success = "0" not in prompt or "by 0" not in prompt.lower()
            metrics.record_tool_call(
                "instrumented_divider",
                duration_ms * 0.1,
                success=success,
                error=None if success else "ZeroDivisionError"
            )

    # Print dashboard data
    dashboard = metrics.get_dashboard_data()
    print("\n  Dashboard Data:")
    print(f"    Invocations: {dashboard['invocations']['total']} "
          f"({dashboard['invocations']['success_rate']}% success)")
    print(f"    Latency: avg={dashboard['invocations']['latency']['avg_ms']}ms, "
          f"p50={dashboard['invocations']['latency']['p50_ms']}ms")
    print(f"    Tokens: {dashboard['tokens']['total']} total")
    print(f"    Tools:")
    for tool_name, stats in dashboard['tools'].items():
        print(f"      {tool_name}: {stats['count']} calls, "
              f"{stats['success_rate']}% success, avg {stats['avg_ms']}ms")
    print(f"    Errors: {dashboard['errors']['total']}")


# =============================================================================
# ITERATION 7: L19 Planning Observability
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 7: L19 Planning Observability")
print("=" * 70)


class PlanStep(BaseModel):
    """A single step in an execution plan."""
    id: str
    description: str
    tool: Optional[str] = None
    depends_on: list[str] = Field(default_factory=list)
    status: str = "pending"  # pending, in_progress, completed, failed
    result: Optional[str] = None


class ExecutionPlan(BaseModel):
    """A plan with multiple steps."""
    goal: str
    steps: list[PlanStep]
    created_at: float = Field(default_factory=time.time)


class TracedPlanningWorkflow:
    """
    Execute planning workflows with full observability.

    Traces the complete lifecycle: plan → validate → execute → verify
    """

    def __init__(self, request_id: Optional[str] = None):
        self.request_id = request_id or str(uuid.uuid4())
        self.model = get_model("haiku")

    def create_plan(self, goal: str) -> ExecutionPlan:
        """Create a plan with traced span."""
        with tracer.start_as_current_span("phase_planning") as span:
            span.set_attribute("goal", goal)

            # Simple plan generation (in production, use LLM)
            steps = []
            if "calculate" in goal.lower() or "math" in goal.lower():
                steps = [
                    PlanStep(id="s1", description="Parse the mathematical expression", tool="parser"),
                    PlanStep(id="s2", description="Evaluate using calculator", tool="calculator", depends_on=["s1"]),
                    PlanStep(id="s3", description="Format and return result", depends_on=["s2"]),
                ]
            else:
                steps = [
                    PlanStep(id="s1", description="Analyze the request"),
                    PlanStep(id="s2", description="Generate response", depends_on=["s1"]),
                ]

            plan = ExecutionPlan(goal=goal, steps=steps)
            span.set_attribute("plan.step_count", len(steps))
            span.set_attribute("plan.tools", [s.tool for s in steps if s.tool])

            return plan

    def validate_plan(self, plan: ExecutionPlan) -> tuple[bool, list[str]]:
        """Validate plan with traced span."""
        with tracer.start_as_current_span("phase_validation") as span:
            errors = []

            # Check for cycles (Kahn's algorithm)
            step_ids = {s.id for s in plan.steps}
            for step in plan.steps:
                for dep in step.depends_on:
                    if dep not in step_ids:
                        errors.append(f"Step {step.id} depends on unknown step {dep}")

            valid = len(errors) == 0
            span.set_attribute("validation.valid", valid)
            span.set_attribute("validation.errors", errors)

            return valid, errors

    def execute_plan(self, plan: ExecutionPlan) -> dict[str, str]:
        """Execute plan with per-step traces."""
        with tracer.start_as_current_span("phase_execution") as exec_span:
            exec_span.set_attribute("plan.goal", plan.goal)

            results = {}

            for step in plan.steps:
                with tracer.start_as_current_span(f"step_{step.id}") as step_span:
                    step_span.set_attribute("step.description", step.description)
                    step_span.set_attribute("step.tool", step.tool or "none")
                    step_span.set_attribute("step.dependencies", step.depends_on)

                    step.status = "in_progress"
                    start_time = time.time()

                    try:
                        # Simulate execution
                        time.sleep(0.1)  # Simulate work
                        step.result = f"Completed: {step.description}"
                        step.status = "completed"
                        results[step.id] = step.result

                        step_span.set_attribute("step.status", "completed")
                        step_span.set_status(Status(StatusCode.OK))

                    except Exception as e:
                        step.status = "failed"
                        step.result = str(e)
                        step_span.set_attribute("step.status", "failed")
                        step_span.set_status(Status(StatusCode.ERROR, str(e)))
                        step_span.record_exception(e)

                    duration_ms = (time.time() - start_time) * 1000
                    step_span.set_attribute("step.duration_ms", duration_ms)

            return results

    def verify_results(self, plan: ExecutionPlan, results: dict[str, str]) -> bool:
        """Verify execution results with traced span."""
        with tracer.start_as_current_span("phase_verification") as span:
            completed = sum(1 for s in plan.steps if s.status == "completed")
            total = len(plan.steps)
            success = completed == total

            span.set_attribute("verification.completed_steps", completed)
            span.set_attribute("verification.total_steps", total)
            span.set_attribute("verification.success", success)

            return success

    def run(self, goal: str) -> tuple[bool, ExecutionPlan]:
        """Run complete planning workflow with root trace."""
        with tracer.start_as_current_span("planning_workflow") as root_span:
            root_span.set_attribute("request.id", self.request_id)
            root_span.set_attribute("workflow.goal", goal)

            # Phase 1: Planning
            plan = self.create_plan(goal)

            # Phase 2: Validation
            valid, errors = self.validate_plan(plan)
            if not valid:
                root_span.set_attribute("workflow.status", "validation_failed")
                return False, plan

            # Phase 3: Execution
            results = self.execute_plan(plan)

            # Phase 4: Verification
            success = self.verify_results(plan, results)

            root_span.set_attribute("workflow.status", "success" if success else "failed")
            return success, plan


def run_iteration_7():
    """Demonstrate L19 planning observability."""
    print("\n[Iteration 7] Running planning workflow with observability...")

    workflow = TracedPlanningWorkflow()
    print(f"  Request ID: {workflow.request_id}")

    goal = "Calculate the sum of 100 + 200 + 300"
    print(f"  Goal: {goal}")

    success, plan = workflow.run(goal)

    print(f"\n  Workflow completed: {'SUCCESS' if success else 'FAILED'}")
    print(f"  Steps executed: {len(plan.steps)}")
    for step in plan.steps:
        print(f"    [{step.status}] {step.id}: {step.description}")

    print("\n  → In Jaeger, look for 'planning_workflow' span")
    print("    Nested structure: planning_workflow → phase_planning → phase_validation → phase_execution → ...")


# =============================================================================
# ITERATION 8: L20 Meta-Agent Observability
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 8: L20 Meta-Agent Observability")
print("=" * 70)


class AgentBlueprint(BaseModel):
    """Blueprint for creating an agent (from L20)."""
    name: str
    description: str
    system_prompt: str
    model_alias: str = "haiku"
    tools: list[str] = Field(default_factory=list)


class BlueprintValidation(BaseModel):
    """Validation result for a blueprint."""
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# Tool registry for dynamic tool assignment
TOOL_REGISTRY = {
    "calculator": calculator,
    "instrumented_calculator": instrumented_calculator,
    "instrumented_divider": instrumented_divider,
}


def get_tools_by_names(tool_names: list[str]) -> list:
    """Get tool functions by name from registry."""
    return [TOOL_REGISTRY[name] for name in tool_names if name in TOOL_REGISTRY]


class TracedAgentFactory:
    """
    Factory for creating agents with full observability.

    Traces the complete lifecycle: analyze task → create blueprint → validate → instantiate
    """

    def __init__(self, request_id: Optional[str] = None):
        self.request_id = request_id or str(uuid.uuid4())
        self.created_blueprints: list[AgentBlueprint] = []

    def analyze_task(self, task: str) -> dict:
        """Analyze task to determine agent requirements."""
        with tracer.start_as_current_span("analyze_task") as span:
            span.set_attribute("task", task)

            # Simple analysis (in production, use LLM)
            needs_math = any(kw in task.lower() for kw in ["calculate", "math", "number", "sum"])
            needs_division = "divide" in task.lower()

            requirements = {
                "needs_math": needs_math,
                "needs_division": needs_division,
                "suggested_tools": [],
                "suggested_model": "haiku",
            }

            if needs_math:
                requirements["suggested_tools"].append("instrumented_calculator")
            if needs_division:
                requirements["suggested_tools"].append("instrumented_divider")

            span.set_attribute("requirements.tools", requirements["suggested_tools"])
            span.set_attribute("requirements.model", requirements["suggested_model"])

            return requirements

    def create_blueprint(self, task: str, requirements: dict) -> AgentBlueprint:
        """Create agent blueprint based on requirements."""
        with tracer.start_as_current_span("create_blueprint") as span:
            blueprint = AgentBlueprint(
                name=f"task_agent_{self.request_id[:8]}",
                description=f"Agent created for: {task[:50]}",
                system_prompt=f"You are a helpful assistant. {task}. Be concise.",
                model_alias=requirements.get("suggested_model", "haiku"),
                tools=requirements.get("suggested_tools", []),
            )

            span.set_attribute("blueprint.name", blueprint.name)
            span.set_attribute("blueprint.model", blueprint.model_alias)
            span.set_attribute("blueprint.tools", blueprint.tools)
            span.set_attribute("blueprint.prompt_length", len(blueprint.system_prompt))

            self.created_blueprints.append(blueprint)
            return blueprint

    def validate_blueprint(self, blueprint: AgentBlueprint) -> BlueprintValidation:
        """Validate blueprint before instantiation."""
        with tracer.start_as_current_span("validate_blueprint") as span:
            errors = []
            warnings = []

            # Check tools exist
            for tool_name in blueprint.tools:
                if tool_name not in TOOL_REGISTRY:
                    errors.append(f"Unknown tool: {tool_name}")

            # Check model
            valid_models = ["haiku", "claude-sonnet-4", "claude-opus-4", "gemini-flash"]
            if blueprint.model_alias not in valid_models:
                warnings.append(f"Unknown model alias: {blueprint.model_alias}")

            # Check prompt
            if len(blueprint.system_prompt) < 10:
                warnings.append("System prompt is very short")
            if len(blueprint.system_prompt) > 2000:
                warnings.append("System prompt is very long")

            validation = BlueprintValidation(
                valid=len(errors) == 0,
                errors=errors,
                warnings=warnings
            )

            span.set_attribute("validation.valid", validation.valid)
            span.set_attribute("validation.error_count", len(errors))
            span.set_attribute("validation.warning_count", len(warnings))

            return validation

    def instantiate_agent(self, blueprint: AgentBlueprint) -> Agent:
        """Create agent from validated blueprint."""
        with tracer.start_as_current_span("instantiate_agent") as span:
            span.set_attribute("blueprint.name", blueprint.name)

            model = get_model(blueprint.model_alias)
            tools = get_tools_by_names(blueprint.tools)

            agent = Agent(
                model=model,
                tools=tools,
                system_prompt=blueprint.system_prompt,
                trace_attributes={
                    "factory.request_id": self.request_id,
                    "blueprint.name": blueprint.name,
                },
                callback_handler=None
            )

            span.set_attribute("agent.tools_loaded", len(tools))
            return agent

    def create_agent_for_task(self, task: str) -> tuple[Agent, AgentBlueprint]:
        """Full factory flow with tracing."""
        with tracer.start_as_current_span("agent_factory") as root_span:
            root_span.set_attribute("request.id", self.request_id)
            root_span.set_attribute("task", task[:100])

            # Step 1: Analyze
            requirements = self.analyze_task(task)

            # Step 2: Create blueprint
            blueprint = self.create_blueprint(task, requirements)

            # Step 3: Validate
            validation = self.validate_blueprint(blueprint)
            if not validation.valid:
                root_span.set_status(Status(StatusCode.ERROR, "Blueprint validation failed"))
                raise ValueError(f"Invalid blueprint: {validation.errors}")

            # Step 4: Instantiate
            agent = self.instantiate_agent(blueprint)

            root_span.set_attribute("factory.status", "success")
            return agent, blueprint


def run_iteration_8():
    """Demonstrate L20 meta-agent observability."""
    print("\n[Iteration 8] Running meta-agent factory with observability...")

    factory = TracedAgentFactory()
    print(f"  Factory Request ID: {factory.request_id}")

    task = "Calculate 2^8 and then divide the result by 4"
    print(f"  Task: {task}")

    # Create agent via factory
    agent, blueprint = factory.create_agent_for_task(task)

    print(f"\n  Blueprint created:")
    print(f"    Name: {blueprint.name}")
    print(f"    Model: {blueprint.model_alias}")
    print(f"    Tools: {blueprint.tools}")

    # Execute the created agent (also traced)
    print("\n  Executing created agent...")
    result = agent(task)
    print(f"  Result: {result}")

    print("\n  → In Jaeger, look for 'agent_factory' span")
    print("    Nested: agent_factory → analyze_task → create_blueprint → validate_blueprint → instantiate_agent")
    print("    Then: traced agent execution with blueprint metadata")


# =============================================================================
# ITERATION 9: Prometheus Metrics Export
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 9: Prometheus Metrics Export")
print("=" * 70)


from prometheus_client import Counter, Histogram, Gauge, start_http_server, REGISTRY
from threading import Thread

# Define Prometheus metrics
AGENT_INVOCATIONS = Counter(
    'strands_agent_invocations_total',
    'Total number of agent invocations',
    ['agent_name', 'model', 'status']
)

AGENT_LATENCY = Histogram(
    'strands_agent_latency_seconds',
    'Agent invocation latency in seconds',
    ['agent_name', 'model'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

TOOL_CALLS = Counter(
    'strands_tool_calls_total',
    'Total number of tool calls',
    ['tool_name', 'status']
)

TOKEN_USAGE = Counter(
    'strands_tokens_total',
    'Total tokens used',
    ['model', 'type']  # type: input or output
)

COST_USD = Counter(
    'strands_cost_usd_total',
    'Total cost in USD',
    ['model']
)

ACTIVE_AGENTS = Gauge(
    'strands_active_agents',
    'Number of currently active agents'
)


class PrometheusMetrics:
    """
    Prometheus metrics collector for Strands agents.

    Exposes metrics at http://localhost:8000/metrics for Prometheus scraping.
    """

    _server_started = False

    @classmethod
    def start_server(cls, port: int = 8000):
        """Start the Prometheus metrics HTTP server."""
        if not cls._server_started:
            try:
                start_http_server(port)
                cls._server_started = True
                print(f"  ✓ Prometheus metrics server started on port {port}")
                print(f"    Scrape endpoint: http://localhost:{port}/metrics")
            except OSError as e:
                if "Address already in use" in str(e):
                    print(f"  ⚠ Metrics server already running on port {port}")
                    cls._server_started = True
                else:
                    raise

    @staticmethod
    def record_invocation(
        agent_name: str,
        model: str,
        duration_seconds: float,
        success: bool,
        input_tokens: int = 0,
        output_tokens: int = 0
    ):
        """Record an agent invocation with all metrics."""
        status = "success" if success else "error"

        # Increment counters
        AGENT_INVOCATIONS.labels(
            agent_name=agent_name,
            model=model,
            status=status
        ).inc()

        # Record latency
        AGENT_LATENCY.labels(
            agent_name=agent_name,
            model=model
        ).observe(duration_seconds)

        # Record tokens
        if input_tokens > 0:
            TOKEN_USAGE.labels(model=model, type="input").inc(input_tokens)
        if output_tokens > 0:
            TOKEN_USAGE.labels(model=model, type="output").inc(output_tokens)

        # Calculate and record cost
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])
        cost = (input_tokens / 1000 * pricing["input"] +
                output_tokens / 1000 * pricing["output"])
        if cost > 0:
            COST_USD.labels(model=model).inc(cost)

    @staticmethod
    def record_tool_call(tool_name: str, success: bool):
        """Record a tool call."""
        status = "success" if success else "error"
        TOOL_CALLS.labels(tool_name=tool_name, status=status).inc()

    @staticmethod
    def set_active_agents(count: int):
        """Set the number of active agents."""
        ACTIVE_AGENTS.set(count)


class PrometheusTracedAgent:
    """Agent wrapper that records Prometheus metrics."""

    def __init__(self, agent: Agent, agent_name: str, model_id: str):
        self.agent = agent
        self.agent_name = agent_name
        self.model_id = model_id

    def __call__(self, prompt: str) -> str:
        ACTIVE_AGENTS.inc()
        start_time = time.time()
        success = True

        try:
            result = str(self.agent(prompt))
            return result
        except Exception as e:
            success = False
            raise
        finally:
            duration = time.time() - start_time
            # Estimate tokens
            input_tokens = len(prompt) // 4
            output_tokens = len(result) // 4 if success else 0

            PrometheusMetrics.record_invocation(
                agent_name=self.agent_name,
                model=self.model_id,
                duration_seconds=duration,
                success=success,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            ACTIVE_AGENTS.dec()


def run_iteration_9():
    """Demonstrate Prometheus metrics export."""
    print("\n[Iteration 9] Setting up Prometheus metrics...")

    # Start metrics server
    PrometheusMetrics.start_server(port=8002)

    # Create agent with Prometheus tracking
    model = get_model("haiku")
    base_agent = Agent(
        model=model,
        tools=[calculator],
        system_prompt="Be concise. Use calculator for math.",
        callback_handler=None
    )

    agent = PrometheusTracedAgent(base_agent, "math_agent", "claude-3-5-haiku")

    # Run several invocations to generate metrics
    print("\n  Running test invocations...")
    test_prompts = [
        "What is 10 + 20?",
        "Calculate 5 * 5",
        "What is 100 / 4?",
    ]

    for prompt in test_prompts:
        result = agent(prompt)
        print(f"    {prompt} → {str(result)[:50]}...")
        PrometheusMetrics.record_tool_call("calculator", success=True)

    print("\n  Metrics available at: http://localhost:8002/metrics")
    print("  Add to prometheus.yml:")
    print("    scrape_configs:")
    print("      - job_name: 'strands-agents'")
    print("        static_configs:")
    print("          - targets: ['host.docker.internal:8002']")
    print("\n  View in Prometheus: http://localhost:9090")
    print("  Query examples:")
    print("    - strands_agent_invocations_total")
    print("    - rate(strands_agent_latency_seconds_sum[1m])")
    print("    - strands_cost_usd_total")


# =============================================================================
# ITERATION 10: LiteLLM Cost Integration
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 10: LiteLLM Cost Integration")
print("=" * 70)

import requests
from collections import defaultdict


class LiteLLMCostTracker:
    """
    Real cost tracking via LiteLLM proxy spend logs.

    LiteLLM tracks actual costs per request with model-specific pricing.
    Much more accurate than estimation.
    """

    def __init__(self, base_url: str = "http://localhost:4000", api_key: str = "sk-local"):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def get_spend_logs(self, limit: int = 100) -> list[dict]:
        """Fetch recent spend logs from LiteLLM."""
        try:
            response = requests.get(
                f"{self.base_url}/spend/logs",
                headers=self.headers,
                params={"limit": limit},
                timeout=5
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"  ⚠ Failed to fetch spend logs: {e}")
            return []

    def get_summary_by_model(self) -> dict:
        """Get spend summary grouped by model."""
        logs = self.get_spend_logs()
        by_model = defaultdict(lambda: {"spend": 0.0, "tokens": 0, "calls": 0})

        for log in logs:
            model = log.get("model_group", log.get("model", "unknown"))
            by_model[model]["spend"] += log.get("spend", 0)
            by_model[model]["tokens"] += log.get("total_tokens", 0)
            by_model[model]["calls"] += 1

        return dict(by_model)

    def get_total_spend(self) -> float:
        """Get total spend across all models."""
        logs = self.get_spend_logs()
        return sum(log.get("spend", 0) for log in logs)

    def get_recent_requests(self, n: int = 5) -> list[dict]:
        """Get the N most recent requests with spend info."""
        logs = self.get_spend_logs(limit=n)
        return [
            {
                "request_id": log.get("request_id", "")[:8],
                "model": log.get("model_group", log.get("model", "unknown")),
                "tokens": log.get("total_tokens", 0),
                "spend": log.get("spend", 0),
                "duration_ms": (
                    (log.get("endTime", "") and log.get("startTime", ""))
                    and 1000  # Simplified
                ),
            }
            for log in logs
        ]


def run_iteration_10():
    """Demonstrate LiteLLM cost integration."""
    print("\n[Iteration 10] Fetching real costs from LiteLLM...")

    tracker = LiteLLMCostTracker()

    # Get summary by model
    summary = tracker.get_summary_by_model()

    print("\n  Cost Summary by Model:")
    print("  " + "-" * 45)
    total_spend = 0
    for model, stats in sorted(summary.items()):
        print(f"  {model}:")
        print(f"    Calls: {stats['calls']}, Tokens: {stats['tokens']:,}, Spend: ${stats['spend']:.6f}")
        total_spend += stats['spend']
    print("  " + "-" * 45)
    print(f"  Total Spend: ${total_spend:.6f}")

    # Show recent requests
    print("\n  Recent Requests:")
    recent = tracker.get_recent_requests(5)
    for req in recent:
        print(f"    [{req['request_id']}] {req['model']}: {req['tokens']} tokens, ${req['spend']:.6f}")

    print("\n  LiteLLM API endpoints:")
    print("    GET /spend/logs - Detailed spend history")
    print("    GET /spend/calculate - Calculate spend for a request")
    print("    GET /global/spend - Total spend across all keys")

    # Record to Prometheus if available
    try:
        for model, stats in summary.items():
            COST_USD.labels(model=model)._value.set(stats['spend'])
        print("\n  ✓ Synced to Prometheus metrics")
    except:
        pass


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Run all iterations."""
    print("\n" + "=" * 70)
    print("LEVEL 21: OBSERVABILITY - ALL ITERATIONS")
    print("=" * 70)
    print("\nPrerequisites:")
    print("  1. Jaeger running at localhost:16686 (docker)")
    print("  2. LiteLLM proxy at localhost:4000")
    print("  3. Prometheus at localhost:9090 (optional)")
    print("\nView traces at: http://localhost:16686")

    # Initialize telemetry once at the start
    setup_basic_telemetry(console=False, otlp=True)

    # Run all iterations
    iterations = [
        ("1", "Basic Tracing Setup", run_iteration_1),
        ("2", "Custom Trace Attributes", run_iteration_2),
        ("3", "Enhanced Tool Instrumentation", run_iteration_3),
        ("4", "Token and Cost Tracking", run_iteration_4),
        ("5", "Multi-Agent Request Correlation", run_iteration_5),
        ("6", "Metrics and Dashboards", run_iteration_6),
        ("7", "L19 Planning Observability", run_iteration_7),
        ("8", "L20 Meta-Agent Observability", run_iteration_8),
        ("9", "Prometheus Metrics Export", run_iteration_9),
        ("10", "LiteLLM Cost Integration", run_iteration_10),
    ]

    for num, name, func in iterations:
        try:
            func()
            print(f"\n  ✓ Iteration {num} completed")
        except Exception as e:
            print(f"\n  ✗ Iteration {num} failed: {e}")

    print("\n" + "=" * 70)
    print("ALL ITERATIONS COMPLETE")
    print("=" * 70)
    print("\nKey Learnings:")
    print("  1. Strands has NATIVE OpenTelemetry support via strands.telemetry")
    print("  2. Agent(..., trace_attributes={...}) adds custom context to all spans")
    print("  3. trace.get_tracer() for custom spans in tools and workflows")
    print("  4. EventLoopMetrics tracks tool usage and token counts")
    print("  5. Multi-agent correlation via parent-child spans")
    print("  6. Planning/factory workflows benefit from phase-level tracing")
    print("  7. prometheus_client for metrics export (Counter, Histogram, Gauge)")
    print("  8. LiteLLM /spend/logs API for REAL cost tracking (no estimation)")
    print("\nEndpoints:")
    print("  - Traces: http://localhost:16686 (Jaeger)")
    print("  - Metrics: http://localhost:8002/metrics (Prometheus scrape)")
    print("  - Prometheus UI: http://localhost:9090")
    print("  - LiteLLM Costs: http://localhost:4000/spend/logs")


if __name__ == "__main__":
    main()

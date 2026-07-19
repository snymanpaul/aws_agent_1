# Level 21: Observability - Reflection

## Summary
Built production observability for Strands Agents using native OpenTelemetry support with Jaeger, Prometheus, and LiteLLM cost tracking. Implemented 10 iterations covering the full observability stack.

## Key Discoveries

### 1. Strands Native OTEL Support (insight)
Strands has built-in OpenTelemetry via `strands.telemetry.StrandsTelemetry` - agent tracing is automatic once initialized. No manual instrumentation needed for basic agent/tool tracing.

### 2. Tracer API Gotcha (mistake)
`strands.telemetry.get_tracer()` returns a Strands-specific wrapper with custom methods like `start_agent_span()`, `start_tool_call_span()`. For custom spans, use `trace.get_tracer("name")` from OpenTelemetry directly:
```python
# Wrong - Strands wrapper doesn't accept name argument
tracer = get_tracer("my_module")  # TypeError

# Correct - use OpenTelemetry directly
from opentelemetry import trace
tracer = trace.get_tracer("my_module")
```

### 3. LiteLLM Real Cost Tracking (insight)
LiteLLM proxy already tracks REAL costs via `/spend/logs` API - no estimation needed! Each request includes spend, tokens, model, timing. Much more accurate than MODEL_PRICING estimation.
```python
GET http://localhost:4000/spend/logs
# Returns: spend, total_tokens, prompt_tokens, completion_tokens, model, timing
```

### 4. Prometheus Port Conflict (insight)
Port 8000 is used by graphiti-mcp-server. Use alternative port (8002) for Prometheus metrics server to avoid conflicts.

## Patterns Established

### Trace Attributes for Correlation
```python
agent = Agent(
    model=model,
    trace_attributes={
        "request.id": str(uuid.uuid4()),
        "session.id": "session-123",
        "environment": "development"
    }
)
```

### Custom Spans with Context Manager
```python
from opentelemetry import trace
tracer = trace.get_tracer("my_module")

with tracer.start_as_current_span("operation") as span:
    span.set_attribute("key", "value")
    span.record_exception(e)  # On error
```

### Phase Tracing for Workflows
```python
with tracer.start_as_current_span("workflow"):
    with tracer.start_as_current_span("phase_planning"): ...
    with tracer.start_as_current_span("phase_execution"): ...
    with tracer.start_as_current_span("phase_verification"): ...
```

### Prometheus Metrics
```python
from prometheus_client import Counter, Histogram, start_http_server

INVOCATIONS = Counter('agent_invocations_total', 'Total invocations', ['model'])
LATENCY = Histogram('agent_latency_seconds', 'Latency', ['model'])

start_http_server(8002)  # Expose /metrics
```

### LiteLLM Cost Tracking
```python
class LiteLLMCostTracker:
    def get_spend_logs(self, limit=100) -> list[dict]
    def get_summary_by_model(self) -> dict
    def get_total_spend(self) -> float
```

## 10 Iterations Completed

1. **Basic Tracing Setup** - StrandsTelemetry + Jaeger
2. **Custom Trace Attributes** - Request/session correlation
3. **Enhanced Tool Instrumentation** - Custom spans with error recording
4. **Token and Cost Tracking** - MODEL_PRICING estimation
5. **Multi-Agent Request Correlation** - Parent-child spans
6. **Metrics and Dashboards** - MetricsAggregator
7. **L19 Planning Observability** - Phase tracing
8. **L20 Meta-Agent Observability** - Factory tracing
9. **Prometheus Metrics Export** - Counter/Histogram/Gauge
10. **LiteLLM Cost Integration** - Real costs from /spend/logs

## Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| Jaeger | http://localhost:16686 | Trace visualization |
| Prometheus scrape | http://localhost:8002/metrics | Metrics endpoint |
| Prometheus UI | http://localhost:9090 | Query metrics |
| LiteLLM costs | http://localhost:4000/spend/logs | Real cost data |

## Files Created/Modified

- `08_production/__init__.py` - New directory
- `08_production/observability.py` - ~1580 lines, 10 iterations
- `pyproject.toml` - Added OTEL + Prometheus dependencies
- `CLAUDE.md` - Added L21 rules
- `LEARNING_PLAN.md` - Marked L21 done

## Dependencies Added

```toml
"strands-agents[otel]>=1.19.0"
"opentelemetry-sdk>=1.25.0"
"opentelemetry-exporter-otlp>=1.25.0"
"opentelemetry-exporter-prometheus>=0.48b0"
```

## Actual Costs Tracked (via LiteLLM)

| Model | Calls | Tokens | Spend |
|-------|-------|--------|-------|
| claude-3-5-haiku | 98 | 62,255 | $0.077513 |
| claude-sonnet-4 | 9 | 5,059 | $0.032697 |
| gpt-5-nano | 116 | 184,908 | $0.011547 |
| Total | 374 | 254,574 | $0.121870 |

## Next Level Preview

L22: Safety & Guardrails - Input/output validation, rate limiting, capability sandboxing

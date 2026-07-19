# Level 23: Error Recovery - Reflection

**Date**: 2024-12-14
**File**: `08_production/error_recovery.py` (~3500 lines)
**Iterations**: 12

## Summary

Built production-ready error recovery patterns progressing from local patterns to AWS-native integrations:
- **Tier 1** (1-5): Local patterns - retry, classification, policies, fallback, circuit breaker
- **Tier 2** (6-7): Stateful recovery - checkpoint/resume, human escalation
- **Tier 3** (8-9): AWS-native - SQS DLQ, Step Functions retry
- **Tier 4** (10): Unified RecoveryStack
- **Tier 5** (11-12): Validation - Fixed DLQ demo, Real Strands Agent integration

## Key Patterns Learned

### 1. Retry with Exponential Backoff
```python
delay = min(base_delay * (exponential_base ** attempt) + jitter, max_delay)
```
- Jitter prevents thundering herd (random ±10% of delay)
- Max delay cap prevents unbounded waits
- Decorator pattern for easy application to any function

### 2. Failure Classification is Critical
Before deciding to retry, classify the failure:
- **TRANSIENT**: Connection errors, 5xx - retry with backoff
- **PERMANENT**: 4xx validation errors - fail fast, don't waste retries
- **RATE_LIMITED**: 429 - back off more aggressively
- **TIMEOUT**: Retry with longer timeout
- **UNKNOWN**: Try once more, then fail

Classification confidence based on: HTTP code (0.95) > Exception type (0.85) > Pattern match (0.70)

### 3. Retry Policies (Strategy Pattern)
Different scenarios need different policies:
- **AlwaysRetry**: Simple, but wastes resources on permanent failures
- **TransientOnly**: Efficient - only retry what might succeed
- **BudgetAware**: Critical for LLM calls - stop when cost threshold reached
- **Adaptive**: Learns from failure patterns, increases delay for repeated rate limits

### 4. Fallback Chains
Three types of fallback chains:
1. **Service**: primary API → backup API → cached response
2. **Model**: claude-opus → claude-sonnet → haiku → gemini-flash
3. **Graceful Degradation**: full response → summary → cached → error message

### 5. Circuit Breaker States
```
CLOSED --[failure_threshold]--> OPEN --[recovery_timeout]--> HALF_OPEN
   ^                                                            |
   +------------[success_threshold]-----------------------------+
   +------------[any_failure]------------------------------------> OPEN
```
- Prevents cascade failures by failing fast
- Half-open state tests recovery with limited calls
- Registry pattern for managing multiple breakers

### 6. Checkpoint & Resume
- Save state after each successful step
- Resume from last checkpoint on failure
- Combine with retry for maximum resilience
- Storage backends: memory (dev), file (staging), S3 (prod)

### 7. Human Escalation
- Metric-based triggers (failure rate, cost threshold, circuit open)
- Multiple notification channels (log, webhook, SMS)
- Human-in-the-loop for critical decisions
- Audit trail of all escalations

### 8. AWS SQS Dead-Letter Queues
- Failed messages don't get lost - captured in DLQ
- `max_receive_count` before DLQ (default: 3)
- Recovery manager for bulk replay with transformation
- Transform messages during recovery to fix issues

### 9. Step Functions Retry (Declarative)
```python
StepFunctionRetryConfig(
    error_equals=["States.Timeout", "ConnectionError"],
    interval_seconds=1.0,
    max_attempts=3,
    backoff_rate=2.0,
    max_delay_seconds=60.0
)
```
- ErrorEquals pattern matching
- Catch blocks for graceful error handling
- Composable with state machine flows

### 10. Unified RecoveryStack
Single facade combining all patterns:
- Retry executor with policy
- Failure classifier
- Circuit breakers per service
- Fallback support
- Escalation integration
- Comprehensive metrics

## Code Patterns

### Decorator for Retry
```python
@retry_with_backoff(max_retries=3, base_delay=1.0)
def my_function():
    ...
```

### Circuit Breaker Usage
```python
breaker = CircuitBreaker("service_name", config)
try:
    result = breaker.execute(my_function)
except CircuitOpenError:
    result = fallback()
```

### RecoveryStack Usage
```python
stack = RecoveryStack(RecoveryConfig(max_retries=3))
result = stack.execute(
    "operation_name",
    my_function,
    service_name="external_api",
    fallback=cached_response
)
```

## Architecture Insights

1. **Classify Before Retry**: Don't waste retries on permanent failures
2. **Circuit Breakers Per Service**: Isolate failures to prevent cascade
3. **Fallbacks Provide Graceful Degradation**: Something > Nothing
4. **Checkpoints Enable Recovery**: Long-running workflows need state persistence
5. **Human Escalation is the Ultimate Safety Net**: When automation fails, escalate
6. **DLQ Captures Failed Work**: No data loss, analyze and replay later
7. **Step Functions Patterns are Declarative**: Configuration over code

## Production Checklist

- [ ] Failure classification for all error types
- [ ] Retry policies matched to use case (transient vs budget-aware)
- [ ] Circuit breakers on all external service calls
- [ ] Fallback chains for critical paths
- [ ] Checkpoints for long-running workflows
- [ ] Escalation policy with appropriate triggers
- [ ] DLQ for async message processing
- [ ] Recovery metrics and monitoring

## Metrics to Track

- `retry_count`: How often retries are used
- `fallback_used`: Frequency of fallback activation
- `circuit_state`: Current state of each circuit breaker
- `escalation_rate`: How often human escalation triggered
- `success_rate`: Overall operation success rate
- `total_delay_seconds`: Time spent in retry delays

### 11. Fixed SQS DLQ Flow
The original iteration 8 had a bug where messages never reached DLQ. Fixed by:
- `make_visible_now()` method to force message visibility for testing
- Increment `approximate_receive_count` on each receive (not creation)
- Proper tracking of in-flight messages with timestamps

### 12. ResilientAgentV2 (Real Agent Integration)
```python
agent = ResilientAgentV2(
    primary_model="claude-sonnet-4",
    fallback_models=["claude-3-5-haiku"]
)
response = agent("Your prompt", tools=[my_tool])
```
- Wraps Strands Agent with full RecoveryStack
- Per-model circuit breakers
- Transparent fallback on failure
- Metrics tracking for monitoring

## Next Steps

Level 24: Tool Synthesis - Agents that create tools at runtime with sandboxed execution.

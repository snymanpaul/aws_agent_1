# L23: Error Recovery

**Code:** `08_production/error_recovery.py`
**Reflection:** [`L23_error_recovery.md`](../../.claude/learnings/reflections/L23_error_recovery.md)

### Level 23: Error Recovery
**Goal:** Graceful failure handling

**Patterns:**
- Retry with backoff
- Fallback chains
- Human escalation

---

## Integration rework (2026-08-26)

Six constructs in this file stood in for services that were reachable. They were found
by classifying every `no_sim_check` hit in the file (15 hits: 6 real, 9 prose about
deliberate fault injection) and replaced with real calls.

| Was | Now |
|---|---|
| `HumanInTheLoop._simulate_human_response` slept 0.5s and returned `options[0]`, tagged `"simulated"` | `_await_human_choice` reads a numbered choice over `select.select` on stdin, bounded by `timeout_seconds` (previously a dead constructor param) |
| `MockResilientAgent` fabricated a fallback narrative in the `else` of `if STRANDS_AVAILABLE` | Deleted. The `if` branch already runs the real `ResilientAgentV2`; the `else` now states that nothing was called |
| `WebhookEscalationHandler.send` printed "Would POST" and returned `True` | Real `requests.post` with timeout; returns `True` only on 2xx |
| `MockSQSQueue`, `FixedMockSQSQueue`, and the "Simulated SQS message" dataclass | One `SqsQueue` over a real boto3 SQS client; `SQSMessage.from_api` parses an actual `ReceiveMessage` response |
| `mock_model_caller` raised for opus/sonnet then returned `f"Response from {model_id}..."` | `call_model_via_proxy` POSTs to the LiteLLM proxy and raises on transport failure or non-2xx |

### What the file now needs to run

- **SQS**: served in-process by `moto` (5.1.18) by default, which implements the real SQS
  wire contract. `USE_LIVE_SQS=1` runs the identical code against a real account. All six
  queues are torn down at the end of Iteration 11, which is what stops a live run leaving
  billable resources behind. Note that `moto` currently sits in the **dev** dependency
  group while this lesson imports it at module scope; moving it is an open one-line change.
- **Models**: Iterations 4 and 12 make billable calls through the LiteLLM proxy. Start it
  first (`podman start litellm-proxy`). `LITELLM_BASE_URL` overrides the endpoint. With the
  proxy stopped, both iterations report real connection failures rather than degrading to a
  fabricated result.
- **Webhook**: `ESCALATION_WEBHOOK_URL` points Iteration 7 at a real endpoint. The default
  is the local discard port, so the POST is genuinely attempted, genuinely fails, and is
  reported as failed.
- **Human escalation**: interactive runs prompt for a choice; non-interactive runs report
  `no-tty-default` and apply the configured `default_action`.

### Verified behaviour

Observed on real runs, not reasoned about:

- **HITL**, 4 of 5 branches: `human` (pty, fed `2`, returned `refund_customer`),
  `timeout-default`, `eof-default` and `no-tty-default` (all returned the configured
  `abort`). `no-options-default` is unexercised, since the demo always passes options.
- **SQS Iteration 8**: orders 2 and 3 go `will_retry (receive #1)` to `#2` to
  `moved_to_dlq (receive #3)`, driven by SQS's own `ApproximateReceiveCount`. The DLQ ends
  with 2 and recovery replays 2.
- **SQS Iteration 11**: immediate retry via `ChangeMessageVisibility(0)` instead of waiting
  out the timeout, which is the distinction the iteration now carries.
- **Model fallback (Iteration 4)**: `claude-opus-4` returned a real HTTP 404 from the proxy,
  then `claude-sonnet-4` returned a real completion. The old fake asserted "Rate limited"
  for opus, which is not why it actually fails.
- **Iteration 12**: forced fallback confirmed. `non-existent-model` got a real 400, retries
  exhausted, escalation fired, `claude-3-5-haiku` answered, `Fallback count: 1`.

### Behaviour changes to be aware of

- `HumanInTheLoop` previously returned `options[0]`, which in Demo 7 is
  `retry_with_manual_review`. It now returns the configured `default_action` (`abort`) when
  no human answers. The fake was silently choosing the risky branch on a failed payment.
- Iteration 8's `visibility_timeout` dropped from 5 to 1, and the round delay is now
  `visibility_timeout + 0.2` rather than a fixed `0.1`. Under real semantics the old sleep
  would never have let a message reappear.

### Known remaining hits

`no_sim_check` reports 7 in this file, all classified as prose rather than behaviour: six
are `simulate_failure(...)`, a fault injector that genuinely raises, and one is a
"Simulated model failure" print describing the real 400 from `non-existent-model`. Renaming
`simulate_failure` would clear six of the seven.

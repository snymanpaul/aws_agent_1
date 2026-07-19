# Level 34: AgentCore Evaluations — Cloud-side Quality Measurement
**Date:** 2026-03-18 | **File:** `11_platform/agentcore_evaluations.py`
**Depends on:** L21 (Observability), L27 (AgentCore), L33 (Policy)
**Unlocks:** L35 (Strands Evals SDK — local/CI complement)

---

## Part 1 — For Humans

### What We Built
A walkthrough of AgentCore's cloud-side evaluation service: 13 built-in
LLM judges, a custom domain-specific judge, and the online evaluation
config that samples live traffic continuously. We hit the ADOT prerequisite
wall for online evaluation — which itself is a valuable lesson about
platform-first APIs.

### How It Works

    +------------------+
    |  Evaluation      |
    |  Service         |
    +--+----------+----+
       |          |
       v          v
    [Builtin]  [Custom LLM-as-judge]
    13 judges  your rubric + Bedrock model
       |          |
       +----+-----+
            |
            v  evaluators list
    +------------------+         +------------------+
    |  Online Config   |<--OTel--|  ADOT-Instrumented|
    |  (continuous)    |  spans  |  Agent Runtime   |
    +------------------+         +------------------+
            |
            v CloudWatch Metrics
    +------------------+
    |  Quality scores  |
    |  per request     |
    +------------------+

    On-demand path (no config needed):
    +------------------+
    |  OTel span data  |---> runtime.evaluate(evaluatorId, spans)
    |  from trace store|         |
    +------------------+         v
                             score + reasoning

### What Went Wrong
1. **Wrong log groups** — used runtime stdout logs (`/aws/bedrock-agentcore/runtimes/...`)
   instead of OTel trace log groups. The evaluation service validates against an
   Application Signals registry, not plain CloudWatch. Fix: use the log group
   created by Application Signals after enabling ADOT instrumentation.

2. **Wrong service name format** — passed agent ID string instead of
   `agentName.endpoint` OTel format. Fix: `l27agentcore_Agent-8SQjr5BSN3.PROD`.

3. **Missing `{assistant_turn}` placeholder** in TRACE-level instructions — the
   evaluation service requires at least one OTel data placeholder so it knows
   what to fill in. Fix: include `{assistant_turn}` in the instructions string.

4. **boto3 IAM uses PascalCase** — `RoleName` not `roleName`. Same mistake on
   two different calls. No excuse; should have read boto3 IAM docs.

5. **Anthropic models blocked on channel accounts** — `anthropic.claude-3-haiku`
   not available. Fix: use `amazon.nova-micro-v1:0`.

### What Worked
1. **Probe-before-code (API shapes)** — probing the service model for all
   evaluator and eval config operations before coding saved multiple errors.

2. **Two-Strike + docs fetch** — hit the same log-group error twice, stopped,
   fetched the AWS docs. Four correct facts in one read: service name format,
   log group type, ADOT prerequisite, `/aws/spans` role permission. One doc
   fetch resolved four unknowns.

3. **Graceful Preview API handling** — wrapping `create_online_evaluation_config`
   in try/except with a clear explanation turns a hard failure into a useful
   documentation of prerequisites. The level still runs clean.

4. **IAM propagation wait** — 10s sleep after `create_role` before using the
   role in `create_online_evaluation_config`. Without this, the role trust
   policy isn't globally visible yet.

### The Single Most Important Thing
Online evaluation in AgentCore is a **platform-first** API: it only works if
your agent is already ADOT-instrumented, exporting spans to Application Signals,
and Application Signals has auto-created and registered the trace log group.
You cannot bootstrap it with a freshly-created CloudWatch log group — the
service validates against an internal OTel registry that only Application
Signals populates. Custom evaluators and on-demand `evaluate()` work without
any of that, but online sampling does not.

---

## Part 2 — For LLMs

### Architecture

```mermaid
flowchart TD
    subgraph Evaluators
        B13[13 Built-in Evaluators\nno creation needed]
        CE[Custom LLM-as-judge\ncreate_evaluator → poll ACTIVE]
    end

    subgraph OnlineEval [Online Evaluation - requires ADOT]
        ADOT[Agent + ADOT SDK] -->|OTel spans| SPANS[/aws/spans]
        APPSIG[Application Signals] -->|auto-creates| TLG[Custom Trace Log Group]
        TLG -->|registered| OELC[create_online_evaluation_config]
        OELC --> ENABLED[executionStatus=ENABLED\nsamples live traffic]
        ENABLED -->|quality scores| CW[CloudWatch Metrics]
    end

    subgraph OnDemand [On-demand - requires OTel spans]
        SPANS2[OTel span data\ntrace_id+span_id+scope+times] -->|runtime.evaluate| SCORE[score + reasoning]
    end

    Evaluators -->|evaluators list| OELC
    Evaluators -->|evaluatorId| OnDemand
```

### Decision Log

| Decision | Why | Trade-off |
|----------|-----|-----------|
| Use amazon.nova-micro-v1:0 as judge model | Anthropic models blocked on channel program accounts | Nova less capable than Claude for complex rubrics |
| Wrap online eval config in try/except | Preview API: log group registry validation fails without ADOT setup | Level still runs clean; documents prerequisites |
| enableOnCreate=False then ENABLED via update | Demonstrates two-step lifecycle explicitly | Extra API call; could use enableOnCreate=True |
| IAM propagation sleep 10s | New role trust policy takes seconds to propagate globally | Brittle fixed delay; retry loop would be cleaner |

### Pseudocode — Key Patterns

```
# Custom LLM-as-judge evaluator (TRACE level)
evaluator = create_evaluator(
    name, level="TRACE",
    llmAsAJudge = {
        instructions = "...{assistant_turn}...",  # placeholder REQUIRED
        ratingScale  = {numerical: [{value, label, definition}, ...]},
        modelConfig  = {bedrockEvaluatorModelConfig: {modelId: "amazon.nova-micro-v1:0"}}
    }
)
poll get_evaluator until ACTIVE
# Reference by evaluatorId string in any evaluators list

# Online eval config (requires ADOT-instrumented agent)
PREREQUISITES:
  agent uses ADOT SDK → spans in /aws/spans
  Application Signals enabled → auto-creates + registers trace log group
  execution role: logs:* + bedrock:InvokeModel + bedrock-agentcore:*

cfg = create_online_evaluation_config(
    name, rule={samplingConfig: {samplingPercentage: 100}},
    dataSourceConfig={cloudWatchLogs: {
        logGroupNames: [APPSIG_CREATED_LOG_GROUP],  # NOT runtime stdout logs
        serviceNames:  ["agentName.endpoint"]        # OTel service.name format
    }},
    evaluators: [{evaluatorId: "Builtin.Helpfulness"}, ...],
    evaluationExecutionRoleArn: ..., enableOnCreate: False
)
poll get_online_evaluation_config until ACTIVE
update executionStatus=ENABLED   # start sampling
update executionStatus=DISABLED  # stop
delete_online_evaluation_config

# On-demand evaluate (requires real OTel span format)
# span schema: trace_id, span_id, scope, start_time/startTimeUnixNano,
#              end_time/endTimeUnixNano, plus OTel attribute fields
result = runtime.evaluate(evaluatorId, {sessionSpans: [otel_span_dict]})
# → evaluationResults list
```

### Observation Log

| # | Category | Topic | Observation |
|---|----------|-------|-------------|
| 1 | mistake | iam-boto3-case | boto3 IAM uses PascalCase (RoleName not roleName) — appeared on two calls |
| 2 | mistake | runtime-log-groups-wrong | Runtime stdout log groups rejected; eval needs OTel trace log group from APPSIG |
| 3 | mistake | service-name-format | serviceNames format is agentName.endpoint, not just the agent ID |
| 4 | mistake | trace-level-instructions-placeholder | TRACE instructions must contain {assistant_turn}, {context}, or {expected_response} |
| 5 | insight | online-eval-needs-adot | Platform-first API: validates log groups against APPSIG OTel registry, not CloudWatch |
| 6 | insight | session-spans-otel-schema | sessionSpans "document" type enforces full OTel span schema at service layer |
| 7 | insight | anthropic-models-blocked-channel-account | Anthropic models blocked on channel program accounts; use Amazon Nova |
| 8 | pattern | builtin-evaluators-no-creation | 13 built-ins always available, no creation/cleanup; mix with custom freely |
| 9 | pattern | docs-rca-before-strike2 | WebFetch docs after Strike 1 resolved 4 unknowns in one call |
| 10 | question | adot-integration-path | How to add ADOT to BedrockAgentCoreApp for end-to-end online eval? |

### Forward Links

- **Unlocks L35**: Strands Evals SDK — local/CI complement to L34's cloud-side evaluation; works without ADOT or live traffic
- **Revisit when**: ADOT instrumentation is set up on an agent — then online evaluation is unblocked and iterations 2+3 can be fully exercised
- **Backward link L21**: L21 = what happened (OTel traces, latency); L34 = how well (semantic quality scores on those same traces)

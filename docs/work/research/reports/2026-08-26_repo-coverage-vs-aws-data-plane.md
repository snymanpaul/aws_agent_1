# Repo coverage versus the AWS data plane (2026-08-26)

**Date:** 2026-08-26
**Purpose:** the companion to [`2026-08-26_aws-analytics-delta.md`](2026-08-26_aws-analytics-delta.md).
That report says what AWS shipped on the data axis. This one says where this repo stands against it:
what is covered, what is absent, what transfers, and which gap is worth closing first. Input to the
Tier 23 decision recorded in `NEXT_STEPS_PLAN.md` (items 7 to 9).

## Method

Coverage claims below are counts from `git grep -ril <term> -- '*.py'` over tracked Python, re-run
on 2026-08-26 rather than quoted from an earlier pass. Absence is the highest-risk kind of claim, so
each is a broad search over all tracked source, not a narrow one, and the hits that survive are
described by what they actually are rather than by their count.

## 1. Verdict

**High fit on one axis only.** The repo covers roughly 80 percent of the agent interface layer and
0 percent of the storage, engine and governance layers. The two meet at exactly the components never
built here: AgentCore Gateway, the managed AWS MCP Server, and catalog-native skills.

This is not a defect. It is what the repo set out to be. It matters now because the analytics delta
shows the agent-relevant surface moving onto the axis this repo does not watch.

## 2. The data plane is absent, and the absence is clean

| Term | Tracked `.py` files |
|---|---:|
| `athena`, `s3 tables`, `iceberg`, `lake formation`, `data catalog`, `lakehouse`, `redshift`, `glue`, `emr`, `msk`, `datazone`, `quicksight`, `firehose`, `duckdb` | **0 each** |
| `kinesis` | 9 |
| `parquet` | 1 |

The `kinesis` hits are all L37 and its probes: streaming AgentCore **memory events** to a Kinesis
Data Stream. That is an agent-infrastructure use of a data service, not data engineering.

So there are two genuine data-plane touches in 101 levels:

- **L45**, agentic RAG on Amazon S3 Vectors.
- **L37**, AgentCore long-term memory streamed to Kinesis.

Neither queries a catalog, neither reads a table format, and no lesson has ever run a query engine.

## 3. AgentCore: three services never built against

The developer guide currently lists 13 services. Levels exist for Runtime (L10, L27), Memory (L37,
L66, L80, L97, L97b), Identity (L74), Code Interpreter (L72), Browser (L73), Observability (L21,
L34), Payments (L69), Evaluations (L34, L35, L91), Policy (L33, L96, L99), Registry (L71), plus
config bundles (L75) and AG-UI (L44, L76).

Three have no level:

- **Gateway.** The most consequential omission. L33 depends on it conceptually (Cedar enforced at
  the Gateway) and L75 touched a Gateway ARN, but no level has ever created one. It is how an API
  or Lambda becomes an MCP tool, and where Policy intercepts every tool call before execution.
- **Harness.** Registered in `LEARNING_PLAN_v148_impact.md` as GA-announced with the SDK surface
  unverified. Its own description names data analysis as a target use case.
- **Optimization.** Newer than the last delta pass, unexamined.

## 4. What transfers, and is genuinely ahead

Four things here are prerequisites for agentic data work rather than merely adjacent to it.

**The MCP security spine.** L09 integration, L56 secure MCP architecture, L60 elicitation, L50 toxic
flow analysis. That is the right lens for the three MCP tiers the analytics delta describes, and it
is the idiom AWS's own servers are written in: read-only by default, explicit write flags,
creator-only mutation, single-statement query enforcement.

**Skills as an architecture.** L30 built progressive disclosure by hand: a menu of names, activation
by name, full instructions injected only on activation. AWS has since shipped that same shape twice,
as Agent Toolkit agent skills and as preview skill assets in the Glue Data Catalog. L30 is the
mechanism layer under both.

**Trajectory-level evaluation.** L83 to L85. A data agent fails in the trajectory, meaning wrong
catalog, wrong table, wrong join path, unfiltered scan, not in the final answer. This is the single
most transferable asset here, and the data plane grounds it better than the agent work did: ground
truth becomes a checkable row count rather than a judge's opinion.

**The first-party-ization thesis, already written.** `SESSION_2026-07-19-reflection.md` recorded that
the SDK shipped native versions of five things this repo hand-built, turning those levels into the
mechanism layer under new primitives. The analytics delta is the next chapter of the same thesis on
a different axis: what AWS absorbed between June and August 2026 is skills, context, and the MCP
client wiring itself.

## 5. Gaps, ordered by consequence

1. **No AWS MCP server has ever been wired.** `.mcp.json` declares exactly one server,
   `graphiti-memory`, local. The repo has MCP theory and no AWS MCP practice.
2. **AgentCore Gateway**, per section 3.
3. **The delta process has no data axis.** The 2026-07-18 ecosystem report says so itself, parking
   AWS Context and Harness GA as "platform-level additions invisible at the SDK layer of this
   report". Honest, and self-declared, but it meant a whole wave passed unseen. Closed by standing
   item 4b.

## 6. The risk is axis lock-in, not staleness

The watch process is SDK-shaped, so a data-plane wave passes it invisibly. That is a property of the
process, not an oversight in any one pass, and it is why the second feed exists now. Anything built
on this work should keep both feeds running, because the agent-relevant surface has moved onto the
one that was missing.

One framing worth correcting while it is cheap: Strands is no longer the only or default way to
reach AWS services from an agent. For data work AWS is steering toward the managed AWS MCP Server
plus the `aws-data-analytics` plugin, which is framework-agnostic by design. Strands remains the
right choice for authoring agents; it is no longer the whole path.

## 7. What this feeds

Tier 23 in `NEXT_STEPS_PLAN.md` (items 7 to 9) is the bridge this report argues for: Gateway, the
managed AWS MCP Server under the L56 and L50 lenses, and trajectory evals against a data agent.

Two smaller items from the same analysis, not yet scheduled:

- **Extend `ship_gate` with a bytes-scanned budget.** Athena and Glue meter on data scanned, not
  tokens. The gate already has a token and latency cost gate, and the AWS analytics skills report
  cost and data scanned per query, so the signal is available.
- **Revisit the deferred `BedrockKnowledgeBaseStore` arm** (Tier 22 follow-on 1). It is billable and
  partly overtaken: AWS Context and Glue business context are the organisation-scale version of the
  same question, and S3 Annotations plus S3 Metadata offer a cheaper, non-provisioned way to test
  grounded retrieval against real object context.

# Next Steps

**Status (2026-08-26):** L1 to L100 plus L97b complete, cross-model validated, repo published publicly
with the README as the front door. The repo passes its own gates: 0 `no_sim_check` hits over 277
`.py` files scanned, 132 tests, all enforced in CI on every push. The gates now ship as
`packages/agent-build-gates`, installable into other projects.

**Status (2026-07-18):** L1 to L93 complete, cross-model validated, repo published publicly with the
README as the front door. Prior plan items (cross-model validation, doc fixes, public README, push to
`main`) are done; the record lives in `.claude/learnings/reflections/` and git history.

**New (2026-07-18):** the ecosystem moved (strands 1.42→1.48, evals 1.0 GA, agentcore 1.18, Strands
Shell). Delta: `docs/work/research/reports/2026-07-18_strands-ecosystem-delta-v142-to-v148.md`.
Tier 22 (L94–L100) plan + sequencing: `LEARNING_PLAN_v148_impact.md`.
**Tier 22 COMPLETE (L94–L100 + L97b), all on `origin/main`:** L94 upgrade+regression (L61 vindicated),
L95 checkpoint runtime, L96 interventions+Cedar, L97 memory rematch (native underperforms on the test
store) + L97b semantic parity (native matches with real recall), L98 sandbox tier (Strands Shell vs
Podman, Rust-source-grounded SSRF), L99 red-team the memory channel (explicit deny-policy defends),
L100 context-mgmt verify (auto ~56% token cut confirms ~55%; accuracy lift an honest negative on
Gemini's 1M window). Session-wide learnings: `.claude/learnings/reflections/SESSION_2026-07-19-reflection.md`.

**New (2026-08-26):** a review of the repo against its two stated purposes, then the work it called for. Done:

- `test_no_sim_check.py` (56 tests, now in the package): the gate now has the positive/negative controls it demands
  of everything else, plus characterization tests for its own gaps.
- `no_sim_check` repaired on the evidence those tests exposed: identifier-aware boundaries
  (`MockSQSQueue`, `mock_client`, `_simulate_human_response` were all invisible before), the two
  vocabulary rules no longer fire on comments or docstrings, and `assume-good-default` narrowed to
  `return True` (its three numeric hits were pass-ratio floors, all false positives). Repo-wide:
  **133 hits to 56**; comment-leading noise 72 to 3.
- L23 `08_production/error_recovery.py`: six substituted integrations replaced with real calls (HITL
  over stdin, real webhook POST, real boto3 SQS via moto with teardown, real model calls through the
  LiteLLM proxy). Verified on live runs including a real 404-then-success fallback. Detail in
  `docs/levels/L23-error-recovery.md`.

Then the rest of that work landed the same day:

- **Enforcement is real.** Triaged all 56 remaining `no_sim_check` hits to zero across 22 files,
  surfacing nine real substituted integrations. Worst was a Bedrock guardrail falling back to a
  five-keyword blocklist whenever the client was missing or the API errored, so a safety control
  answered ALLOW on an outage. `.github/workflows/gates.yml` runs both tripwires and the suite on
  every push; the pre-commit hook runs both over staged files. `eval_harness` and `ship_gate`
  gained 34 tests, and `check_no_aws_ids` gained 21 plus a `noaws:ok` per-line escape.
- **The gates are installable.** `packages/agent-build-gates` v0.1.0, a uv workspace member with
  its own version, tests and console scripts. Zero dependencies; `ship_gate` behind a `[strands]`
  extra. Proven by running the built wheel from a clean venv outside the repo.
- **Docs.** Stale L43 source link repaired, `METHOD.md` written, README reframed to lead with the
  method, and the analytics watch feed started (standing item 4b).

Still open from that pass: the 18 files using `sys.path.insert(0, ".")`, which break when run from
anywhere but the repo root. Everything else on that list is done.

## Tier 22 follow-ons (deferred by choice: each a clean next session)

1. **Authentic `BedrockKnowledgeBaseStore` memory arm** (the real AWS L97b). L97b answered the
   parity question with a local semantic store; this does it on a provisioned Bedrock KB (vector
   index + embedding model + S3 data source + IAM). Billable, teardown-critical: probe-first, and
   run it as a deliberate session with a teardown checklist on the agentic sandbox account.

2. **Full chaos-resilience evaluators** (`strands_evals.chaos`). L99 did the red-team half; the
   chaos half (failure-communication / partial-completion / recovery-strategy evaluators under
   injected tool faults) is a level's worth on its own, reusing L99's red-team plumbing.

3. ~~**Cross-model (Bedrock Nova) pass of the L96/L99 security findings.**~~ **DONE 2026-07-19**
   (`13_quality/crossmodel_nova_l96_l99.py`, reflection `crossmodel-nova-l96-l99-reflection.md`):
   L96 interventions (Deny/Transform/Cedar/Guide) are framework-inherent on Nova; L99's
   explicit-policy defense holds on Nova, but injection susceptibility is model-specific: Nova Lite
   is markedly MORE injection-resistant than Gemini (1–2/3 vs 4/4). Security posture transfers;
   raw attack-success rate does not.

## Standing items

4. ~~**Operationalize the quality gates.**~~ **DONE 2026-08-26.** `.github/workflows/gates.yml`
   runs `check-no-aws-ids`, `no-sim-check` and `uv run pytest` on every push and pull request.
   `tools/install_hooks.sh` installs a pre-commit hook running both tripwires over staged files,
   verified by staging a violation and confirming the commit was rejected. `ship-gate` stays
   manual because it spends money, and is documented as a release step in README and CLAUDE.md.
   CI deliberately excludes the lessons: they need credentials, a proxy and AWS access.

4b. **Keep the second watch feed running.** The Strands/AgentCore delta is SDK-shaped and
   says so, which is why AWS Context and Harness GA were logged as names and never analysed.
   The analytics feed covers that axis: `docs/aws-data-engineering-landscape.md`
   is the first entry. Sources to sweep: AWS Glue, Amazon Athena, Amazon S3 Tables, AWS Lake
   Formation, and the dated SageMaker Unified Studio release-notes page. Refresh it before any
   data-plane lesson, and carry the primary versus extraction markers across.

5. **Meta-eval: judge reliability at the ambiguous boundary.** L52 showed judges are reliable on
   clear-cut cases; the ambiguous middle is its known weak spot. Build a graded-ambiguity dataset and
   measure where judge agreement collapses.

6. **Memory safety and privacy evals.** L89 + L99 covered tool-result and memory-record injection
   (L99 found the explicit-policy defense); still open: PII handling in extracted LTM records and
   tenant isolation across memory stores.

## Tier 23 candidate: the data plane (L101+)

Deferred deliberately until enforcement and the analytics feed were in place. Both now are, so
this is the next tier if lesson work resumes. Three levels, not a full tier of seven, chosen
because each closes a gap the repo can name rather than a topic that merely looks next.

The analysis behind these three, including the coverage counts and the ordering, is
[`docs/assessment-aws-agent-1-cross-reference.md`](docs/assessment-aws-agent-1-cross-reference.md).
Headline: two genuine data-plane touches in 101 levels (L45 S3 Vectors, L37 Kinesis), zero tracked
Python mentioning Athena, Glue, Redshift, S3 Tables, Iceberg or Lake Formation, and two AgentCore
services with no level at all (Harness, Optimization).

7. **Give L27's Gateway target a real backend.** Corrected 2026-08-26: this was written as
   "the one platform primitive never built here", which was wrong. Section 2.3 of the assessment
   has the bytes. `10_production/l27agentcore/cdk/lib/stacks/agentcore-stack.ts` creates a
   `CfnGateway` (MCP, Cognito CUSTOM_JWT) and a `CfnGatewayTarget` onto a Lambda with an inline
   tool schema; `src/mcp_client/client.py` connects a Strands `MCPClient` to it with a bearer
   token; L33 attaches Cedar to that same gateway; L75 provisions another through boto3. The
   stack was deployed: `observations.jsonl:815` names `l27agentcore-AgentCoreStack` as a real
   CloudFormation stack. Two things are missing, not one. The tool:
   `mcp/lambda/handler.py` serves `placeholder_tool`, a no-op that echoes its arguments. And the
   proof: no completed MCP call through the Gateway appears in the observation log, the
   reflections or the level docs, while `level-33-reflection.md:61` records the gateway as having
   no registered tool schema. So the work is to put something real behind the target, capture a
   call landing on it with a runtime sentinel, then re-run L96's intervention taxonomy at the
   Gateway instead of in-process. Still needs AWS credentials, still spends money, still
   teardown-critical, but it is a substitution plus a proof rather than a new primitive, which
   makes it the cheapest of the three.

8. **The managed AWS MCP Server**, run under the L56 secure-MCP lens and L50 toxic-flow analysis.
   Current state, stated precisely: `.mcp.json` declares one server (`graphiti-memory`, local),
   and L27 calls an AgentCore Gateway over MCP, but that is an endpoint this repo stood up itself
   with a placeholder tool behind it. No AWS-published server has been run: not the managed AWS
   MCP Server, not `awslabs/mcp`, not the Knowledge MCP server. The Agent Toolkit for AWS went GA
   in May 2026 and ships an `aws-data-analytics` plugin; see the analytics delta report for the
   survey.

9. **Trajectory evals against a data agent.** Highest value of the three. Port the L83 trajectory
   evaluator so the trajectory is catalog chosen, table resolved, join path taken, and filters
   applied before aggregation. Ground truth is a known-correct query and a checkable row count
   rather than a judge's opinion, which is the property the agent-side evals never had.
   Refresh item 4b first so the level is built against a current picture of the analytics surface.

## On demand

- Cloud ADOT online-eval (extends L34/F2 to continuous production sampling).
- **Bytes-scanned budget in `ship_gate`.** Athena and Glue meter on data scanned, not tokens. The
  gate already has a token and latency cost gate, and the AWS analytics skills report cost and data
  scanned per query, so the signal is there. Needed before any data-plane level can be gated on cost.
- **Re-scope Tier 22 follow-on 1 before spending on it.** The `BedrockKnowledgeBaseStore` arm is
  billable and partly overtaken: AWS Context and Glue business context are the organisation-scale
  version of the same question, and S3 Annotations plus S3 Metadata test grounded retrieval against
  real object context without provisioning anything.

## Data hygiene

- L97b observations in `observations.jsonl` are keyed `"level": 971` (integer stand-in for "97b");
  the reflection/docs use "97b". Normalize if a consumer filters the log by integer level.

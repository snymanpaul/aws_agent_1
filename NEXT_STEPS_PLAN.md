# Next Steps

**Status (2026-08-26):** L1 to L100 plus L97b complete, cross-model validated, repo published publicly
with the README as the front door. The repo does not currently pass its own `no_sim_check` gate:
56 hits over 271 tracked `.py` files.

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

**New (2026-08-26):** outside assessment against the repo's stated mission, plus the first pass on
standing item 4. Assessment: `MISSION_ASSESSMENT_2026-08-26.md`. Done:

- `tests/test_no_sim_check.py` (56 tests): the gate now has the positive/negative controls it demands
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

Still open from that assessment: CI (nothing in `.github/` yet), packaging `tools/` for external
reuse, and the `simulate_failure` naming that accounts for six of L23's seven remaining hits.

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

4. **Operationalize the quality gates.** Wire `tools/no_sim_check.py` and `uv run pytest` into
   pre-commit and CI (GitHub Actions) so the anti-simulation bar is enforced on every push, not run
   by hand. Precedent exists: `tools/install_hooks.sh` already installs the `check_no_aws_ids`
   pre-commit hook; extend that hook to run `no_sim_check` + `pytest`. `ship_gate.py` stays manual
   (it spends money) but should be a documented release step.

4b. **Keep the second watch feed running.** The Strands/AgentCore delta is SDK-shaped and
   says so, which is why AWS Context and Harness GA were logged as names and never analysed.
   The analytics feed covers that axis: `docs/work/research/reports/2026-08-26_aws-analytics-delta.md`
   is the first entry. Sources to sweep: AWS Glue, Amazon Athena, Amazon S3 Tables, AWS Lake
   Formation, and the dated SageMaker Unified Studio release-notes page. Refresh it before any
   data-plane lesson, and carry the primary versus extraction markers across.

5. **Meta-eval: judge reliability at the ambiguous boundary.** L52 showed judges are reliable on
   clear-cut cases; the ambiguous middle is its known weak spot. Build a graded-ambiguity dataset and
   measure where judge agreement collapses.

6. **Memory safety and privacy evals.** L89 + L99 covered tool-result and memory-record injection
   (L99 found the explicit-policy defense); still open: PII handling in extracted LTM records and
   tenant isolation across memory stores.

## On demand

- Cloud ADOT online-eval (extends L34/F2 to continuous production sampling).
- Package the eval harness for external use.

## Data hygiene

- L97b observations in `observations.jsonl` are keyed `"level": 971` (integer stand-in for "97b");
  the reflection/docs use "97b". Normalize if a consumer filters the log by integer level.

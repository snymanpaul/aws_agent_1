# Next-Steps Plan (cross-model validation → … → public README)

**Context snapshot (2026-06-03):** L78–L92 built, run live, gate-clean (no_sim_check), committed, reflected
— but every new lesson ran on a SINGLE model (`gemini-2.5-flash` via the LiteLLM proxy). Tools:
`tools/{no_sim_check,eval_harness,ship_gate}.py`. observations.jsonl ~901 lines (0 malformed).
Repo will be **published publicly** — the README is the front door.

## Ranked recommendations (from the review)
1. **Cross-model validation of L78–L92** — findings are single-model; validate vs a 2nd model.
   ← **DONE** (L93 on Nova Lite, committed `eeec432`; L77 ADK patterns also cross-model on Bedrock Claude, `a5e45f0`).
2. Fix stale docs (CLAUDE.md said "27 levels"; repo is at L93).
   ← **DONE 2026-06-04** (README podman fix + accurate scope; CLAUDE.md structure map extended to L1–L93/`artifacts/`).
3. Operationalize gates (pytest + pre-commit / CI for no_sim_check + ship_gate).
4. Meta-eval: judge reliability at the ambiguous boundary (L52's known weak spot).
5. Memory safety/privacy evals (poisoning, PII, tenant isolation).
6. Cloud ADOT online-eval · push `main` · package for the external team (do on demand).

## DONE — cross-model validation on Bedrock Nova Lite (L93, committed `eeec432`)
- **Model:** `amazon.nova-lite-v1:0` (cost-effective; Amazon family ≠ Gemini = real contrast),
  `region us-east-1`, profile `<your-sso-profile>`.
- **Goal:** label each model-sensitive finding **framework-inherent** (holds on Nova too) vs
  **model-specific** (differs) — the repo's signature discipline (cf. L77's Gemini-vs-Claude deltas).
- **Scope (model-sensitive findings only):** memory tool-use (L78), trajectory tool-args (L83),
  multi-turn goal-success (L84), memory-faithfulness (L88), tool-injection safety (L89, the
  single-model claim), and Nova-as-judge (L91). Memory STORES (L79/L80/L81/L90) and stats (L85) are
  model-agnostic by construction → not re-run.
- **How:** a real Nova exercise of each finding's core mechanism, same anti-sim discipline
  (runtime sentinels, real services, positive/negative controls); pass no_sim_check.
- **Capture:** observations tagged framework-inherent vs model-specific; extend the reflection.
- **Note:** a capability-driven failure on Nova (e.g. weak tool-use) is distinct from a framework
  finding — interpret accordingly.

## DEFERRED — FINAL STEP: public README (the repo's front door)
Surface the **biggest insights** learned across the repo (not a file index). Candidate headliners:
- Provider portability: ADK's per-pattern classes → Strands' few primitives (Graph+conditions+cycles,
  Swarm, agents-as-tools); patterns are framework-inherent across Gemini + Bedrock.
- "Reproducible ≠ temperature 0" — determinism is architectural (typed outputs, capped loops, guards).
- Anti-simulation as a *mechanism* (no_sim_check) + structurally un-fakeable tests (runtime sentinels,
  real crashes, positive/negative controls).
- Agentic memory: shared/cross-session/LTM-filtered/long-horizon/durable, behind hexagonal ports.
- Agentic evals: trajectory+args, goal-success, significance, native trace-level evaluators run LOCALLY.
- The synthesis: a paid, audit-reproducible **ship-gate** (`tools/ship_gate.py`).
- Honest negative results (e.g., gemini-2.5-flash robust to a blatant injection; more-sources ≠ better).
Write it LAST, after cross-model results are in.

## Working notes
- Context budget watched (~780k/1M) — keep runs/outputs lean; this doc is the durable intent if compacted.

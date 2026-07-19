# Handover — ADK multi-agent patterns on Strands + Gemini (mechanically verified)

**To:** Lead engineer, review-gate project
**From:** Strands reference/learning repo (`aws_agent_1`)
**Re:** Follow-up to the 5-question architecture review. I built and ran all 8 ADK multi-agent patterns on
Strands. Read this together with `strands-review-gate-architecture.md` — where the two disagree, trust the
architecture doc's hedges; this handover is the empirical follow-up, not a stronger claim.

> **Transport caveat (read first).** These prototypes run against a **local LiteLLM proxy**
> (`_model.py`: `localhost:4000`, `sk-local`) — the **same OpenAI-compat *shape* as your stack, but a
> different wire path** than Google's first-party Gemini compat endpoint. They were **not** run against
> your endpoint. Editing `_model.py` (`BASE_URL`/`API_KEY`/`MODEL_ID`) is **mandatory** to run these, and
> the architecture doc flags that a proxy can drop provider metadata — so re-confirm the model-level
> findings (Q4, determinism) on *your* endpoint.

---

## Update — 2026-06-03 (newer than everything below; read first)

Since I sent this, the cross-model leg was executed properly and the **whole suite was independently
audited against its own traces** (not the harness's self-report). Two changes, then four lessons that bear
directly on your gate.

**What changed (all committed; reproducible from disk):**
- **Bedrock `claude-haiku-4-5` is now artifact-backed.** 8/8 pass, 8/8 reproducible, **23 per-run traces
  preserved + committed** (`traces_bedrock_claude_haiku_2026-06-03/`), every per-pattern signal
  byte-identical to the Gemini run. This **closes** the original "not artifact-backed; traces overwrite in
  place" caveat (the cross-model note below now reflects it).
- **Full independent trace audit of all 8 patterns** — mechanisms verified against the event logs. All 8
  hold on both model families; two assertions are provable only by inference (lesson 3).

**Key lessons since then — these change how you build the gate:**

1. **"Reproducible" bounds control-flow, NOT latency — and the noise is not a local-proxy artifact.** P8
   run2 stalled **~61 s** on a single parallel sub-agent on **native AWS Bedrock** (run1 ~35 s, run2 ~100 s)
   while *both* runs emit an identical "reproducible" signal. → Treat determinism and latency as **separate
   gates**: per-node timeouts + fallbacks, and watch p95/p99 tail. Never read "8/8 reproducible" as "latency
   is stable" — the signal check masks a 3× wall-clock spread completely.

2. **Topology-green ≠ good decisions — now demonstrated in the evidence, not just hedged.** P4 passed while
   its agent answered *"insufficient data … RISK: HIGH"* — a content-free punt. P6's "iterative refinement"
   **did not refine**: the critic returned `GOOD` on round 1, and the 2nd round ran *only* because
   `MIN_ROUNDS=2` forces it (byte-identical reason both rounds). → The suite proves the wiring
   routes/exits/loops; it says **nothing** about whether a verdict is correct or whether a critic-loop
   improves the artifact. Stand up a **separate quality eval** (golden ballots, decision-accuracy,
   inter-rater agreement) before trusting any pattern to gate real reviews — and **measure** that iteration
   helps; do not assume it. A green topology check on your ballot loop could be approving garbage.

3. **A hook/callback trace can't prove nesting depth — capture lineage or OTel.** In the audit, P1's
   content-lineage (the node trace has **0 tool calls**) and P4's 2-level depth were **not** directly
   observable: an agent-as-tool emits no hook events, so the deepest level is provable only by **output
   provenance** (a sentinel surfacing up top) or OTel spans. → Your audit *artifact* must record
   lineage/OTel, or it will silently under-report nested agents-as-tools and leave gaps in the evidence
   chain. (Sharpens the "callbacks don't fire as tools" note below: it also limits what the trace can *prove*.)

4. **The typed-verdict gate is provider-portable — confirmed on Bedrock, with committed trace rows.** Forced
   `structured_output` (the `Ballot` tool) produced typed `REVISE→PASS` on native Bedrock Claude exactly as
   on the proxy→Gemini path. → Your typed-verdict approach should port across providers; still add the
   fail-closed `StructuredOutputException` handler (step 1 in "Suggested next steps").

**Evidence:** committed traces in `traces_bedrock_claude_haiku_2026-06-03/`; full per-pattern audit table +
both findings in `.claude/learnings/reflections/level-77-crossmodel-validation-reflection.md`. **Net stance
is unchanged:** two model families with identical, now-trace-verified *plumbing* — strong corroboration that
the topology is framework-inherent, **not** a proof of decision quality, and still not your real transport.

---

## What this gives you

The first deliverable answered your 5 questions on paper. This one **runs** the patterns and reports what
happens — at the **mechanism** level (does the topology build/route/exit/loop), not output quality.

**Result:** 8/8 patterns pass the suite (7 patterns ×3 runs, composite ×2) on `gemini-2.5-flash` via the
local proxy. "Reproducible" here = an **identical control-flow signal** (execution order / routing /
verdict label) across same-session runs — **not output-text determinism** (free text varies every run).
~26.8k tokens/full-pass (mean of 3 Gemini runs; model- and prompt-dependent; re-verified 2026-06-03 at
~25.2k). Cross-model: the 8 patterns were re-run on **Bedrock `claude-haiku-4-5`** and, on **2026-06-03,
artifact-backed** — 8/8 pass, 8/8 reproducible, ~35.1k tok, with all **23 per-run traces preserved** to
`traces_bedrock_claude_haiku_2026-06-03/` and **every per-pattern signal byte-identical to the Gemini run**.
Treat it as **consistent with** framework-inherence — strong for N=2 model families, still **not a universal
proof** (mechanism not quality; one task/session/machine; Claude access on the test account stays
intermittent). The basis for framework-inherence is that the topology is **model-agnostic Strands code**
(`Graph`/`Swarm`/hooks); the other durable cross-model evidence in this repo is the **Nova Lite** run for
the separate L78–L92 work.

---

## Lessons that change your decisions (mapped to your original questions)

**Q5 — `temperature=0.0` does NOT pin Gemini.** Reproducible control-flow came **only after** structural
guards, not temperature. The multi-run audit caught two nondeterminisms single runs hid (a swarm that
ping-ponged to `FAILED`; an intermittent nested tool-call). Engineer reproducibility from **structure**
(handoff/iteration limits, bounded retries, typed outputs, execution caps); treat "reproducible on
identical input" as the bar — and note output *text* still varies.

**Q4 — Forced structured output worked through `OpenAIModel`→proxy→`gemini-2.5-flash`.** Set
`structured_output_model=PydanticModel` at construction → typed `Literal` verdict, even as a Graph node;
the loop reads `ballot.verdict` (no substring parse). The trace shows it surfaces as a `Ballot` **tool call**.
Caveats: (a) the architecture doc marks the *Google-endpoint* compat path **NOT VERIFIED** — this was the
*proxy* path, and the repo's other Gemini runs use native `GeminiModel` (a third wire path); confirm on
yours. (b) "malformed → raises" is a **Pydantic property, not stress-tested here** (happy-path only) — and
it converts silent-REVISE into a `StructuredOutputException` you must **catch with an explicit fail-closed
policy**. See `p5_generator_critic.py`, `p6_iterative_refinement.py`.

**Q3 — Swarm vs. independent panel.** `Swarm` = shared-context + autonomous handoff = **cross-talk**, and it
**ping-pongs to `FAILED`** without `repetitive_handoff_detection_window` + "don't hand off" prompts. For an
**independent N-reviewer panel use a `Graph` with no edges between reviewers**. **For a paid audit gate,
prefer zero Swarm in the gated path** — its cost scales with handoffs and it can terminate `FAILED`
nondeterministically; use a deterministic Graph conditional edge or a code router. See `p2_coordinator.py`, `p3_parallel.py`.

**Latency — parallel fan-out *can* be ~2× faster, but the number is not portable.** Isolated, parallel ran
~46% of sequential wall-clock; under load on the **memory-stressed local proxy** it **inverted once**. The
test takes **best-of-2 on the parallel side only** (so the gate doesn't flap — this biases the reported
number). Treat ~2× as best-case on *that* proxy; on your endpoint it's unknown. See `p3_parallel.py`.

**Q5 — Trace gotcha: a sub-agent's `callback_handler` does NOT fire when it runs as a tool.** So
callback-based tracing under-reports nested agents-as-tools (a qualitative finding; the "0–2/3" figure was
an unlogged observation, not a persisted metric). Trace nested calls by **output lineage** or OTel — not callbacks.

**General — `Graph` is the workhorse.** No `SequentialAgent`/`ParallelAgent`/`LoopAgent` in Strands; one
`Graph` covers sequential/parallel/loop via **conditional edges** + **cycles** (`reset_on_revisit`). Bound
every cycle with `set_max_node_executions` and loops with `Limits(turns=...)` — **mandatory** for a gate
(a real ballot won't have the toy prompt's convenient single-cycle behavior; budget for the cap × retries × fan-out).

**HITL is a real *in-process* pause/resume.** `BeforeToolCallEvent` → `event.interrupt(...)` →
`result.interrupts` → resume with `interruptResponse`. APPROVE runs the gated tool; DENY via
`event.cancel_tool` blocks it (ledger-proven). **Not demonstrated:** durable cross-process/overnight
interrupt persistence, or evasion resistance — it's a mechanism demo, not a security control. See `p7_human_in_the_loop.py`.

**Observability.** Native hooks (`_trace.py`) record per-node invocations + every tool call/result with
`seq`+`ms`, dumped to `traces/<pattern>_run<N>.jsonl` (shape — see the real files for records). Caveats for
an *audit* gate: (a) `traces/` is **git-ignored** and **overwritten in place** each run — not append-only
evidence as-is; (b) records carry wall-clock `ms`, so byte-diffing runs always differs — **diff the
signal/verdict projection, not raw JSONL**; (c) reasoning/CoT is not captured; (d) the OTel path
(`_trace.enable_otel()`) is **not exercised here** — validate it before relying on it for the audit trail.

---

## Source code (full paths, repo: `aws_agent_1`)

- `.../artifacts/strands_review_gate/strands-review-gate-architecture.md` — the 5-question answer (more hedged; the source of truth on disagreements)
- `.../artifacts/adk_patterns/README.md` — mapping, audit table, findings, caveats
- `.../artifacts/adk_patterns/_model.py` — **the transport you must edit** (currently local proxy → `gemini-2.5-flash`)
- `_harness.py` (multi-run + tokens) · `_trace.py` (hook trace + OTel option) · `run_all.py` (audit runner)
- `p1_sequential … p8_composite.py` — one pattern each, with `trial()` + assertions
- `traces/` — per-run JSONL (git-ignored; regenerated by `run_all.py`)
- `.../08_production/observability.py` — repo's OTel/Jaeger reference (L21)

---

## How to run

```bash
# Prereqs: Python >=3.13, strands-agents >=1.42; an OpenAI-compat endpoint you control.
# The bundled local proxy is a single fragile container (it OOM'd on a 2GB VM mid-session) — not for prod.
# 1) EDIT _model.py: point BASE_URL/API_KEY at YOUR Gemini compat endpoint (sk-local won't work).
cd .../artifacts/adk_patterns && uv run python run_all.py     # or any pN_*.py alone
```
The Bedrock path (`ADK_MODEL_PROVIDER=bedrock`) needs AWS SSO + Bedrock model-access grants; Anthropic
models are **gated on channel/partner accounts** (Nova works everywhere). Pinned model IDs
(`gemini-2.5-flash`, `claude-haiku-4-5-…`) **will retire and fail at call time** — keep a fallback + monitor lifecycle.

---

## Honest caveats — don't over-trust this

- **Not your transport.** Verified on a *local proxy*, not your Gemini endpoint (see top). The model-level
  findings (Q4, determinism, latency, cost) are the ones most likely to differ on your wire path.
- **Mechanism, not quality.** Asserts topology runs/routes/exits (e.g. P8 only checks node set + result
  types + non-empty output). It does **not** measure whether a pattern produces *good* review decisions.
- **Loops engineered to iterate** (P5 qualitative-first, P6 `MIN_ROUNDS=2`) — the cycle mechanism is proven,
  not emergent refinement; a real ballot won't take exactly one REVISE→PASS pass.
- **Tiny sample.** 3 runs/pattern (composite 2), one task each, one session, one machine — surfaces gross
  nondeterminism, **not** a powered study. No statistical-significance testing in this suite.
- **Cross-model = N=2 providers**, one (Bedrock-Claude) flaky and un-artifacted. "Framework-inherent" is
  *consistent with* the evidence (model-agnostic code paths), not proven.
- **Cost numbers are proxy/Gemini, toy-input means** (~26.8k; Bedrock-Claude ~32.5k) — budget against your
  real ballot sizes + worst-case loop/retry/fan-out, not this figure.

---

## Suggested next steps for your gate

1. Move your ballot to `structured_output_model` (typed verdict) — but add an **explicit fail-closed handler**
   for `StructuredOutputException` (it replaces silent-REVISE with an exception, not with safety).
2. Build the reviewer panel as a `Graph` with no edges between reviewers; **no Swarm in the gated path**; set
   `set_max_node_executions` + per-agent `Limits(turns=...)`.
3. For audit reproducibility: structural determinism (typed outputs, capped loops, guards) + an
   **append-only, timing-stripped** trace store (the bundled traces are git-ignored/overwritten — fix that);
   diff the verdict/signal projection, not raw JSONL. Don't claim determinism from temperature.
4. **Re-run on YOUR endpoint + model** (edit `_model.py`) and probe the architecture doc's open items —
   especially structured-output-through-*your*-compat-path and whether `seed`/`thinking` survive the shim.
   Two providers ported cleanly here, so porting is *likely* — but weaker models may need more retries
   (Gemini already needed 1–2 vs Claude's 1); verify, don't assume.

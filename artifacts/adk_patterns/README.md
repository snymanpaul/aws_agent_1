# ADK multi-agent patterns, prototyped + verified on Strands + Gemini

Source: [A developer's guide to multi-agent patterns in ADK](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/).

All 8 ADK patterns reproduced with **Strands** primitives and verified live on **`gemini-2.5-flash`
through the OpenAI-compat proxy** (`OpenAIModel` → LiteLLM `:4000` → Gemini) — the production gate's
transport. Each pattern is run **N times** by `run_all.py`, which checks pass-rate, cross-run
**reproducibility** (identical signal every run), and **token cost** (the gate is paid).

```bash
podman start litellm-proxy        # proxy must be up (serves gemini-2.5-flash)
uv run python run_all.py          # full audit; or: uv run python p5_generator_critic.py
```

## Audit result (temp 0.0, 3 runs each; P8 ×2)

| pattern | pass | reproducible | mean tok |
|---|---|---|---|
| P1 Sequential Pipeline | 3/3 | yes | 2,228 |
| P2 Coordinator/Dispatcher | 3/3 | yes | 2,325 |
| P3 Parallel Fan-Out/Gather | 3/3 | yes | 3,751 |
| P4 Hierarchical Decomposition | 3/3 | yes | 812 |
| P5 Generator & Critic | 3/3 | yes | 3,172 |
| P6 Iterative Refinement | 3/3 | yes | 4,050 |
| P7 Human-in-the-Loop | 3/3 | yes | 1,286 |
| P8 Composite | 2/2 | yes | 9,131 |

**8/8 pass all runs · 8/8 reproducible · ~26,800 tok per full pass.** (Fully instrumented run; P3 uses
best-of-2 timing — see finding 5. Re-verified 2026-06-03: 8/8 pass, 8/8 reproducible, ~25.2k tok.)

**Cross-model (artifact-backed; consistent with framework-inherence):** re-running the same suite on **AWS
Bedrock `claude-haiku-4-5`** (`ADK_MODEL_PROVIDER=bedrock`, acct <agentic-account-id>, us-east-1) → **8/8 pass, 8/8
reproducible**, with **every per-pattern signal byte-identical to the Gemini run**. Same code, different
provider — strong for N=2 model families, not a universal proof (mechanism not quality; one task/session).
Re-run **2026-06-03**: ~35.1k tok/pass (Claude more verbose on swarm/interrupt — P2/P7/P8 — but terser on
P1/P3), all **23 per-run traces preserved** to `traces_bedrock_claude_haiku_2026-06-03/`. The one
model-specific delta, confirmed this run: P4's nested tool-call fired first-attempt on Claude (`attempts=1/4`)
vs 2 on Gemini — handled by the bounded retry.

## Key finding

ADK ships **one class per pattern** (`SequentialAgent`, `ParallelAgent`, `LoopAgent`, …). Strands has
**none of those**; three general primitives subsume all 8:

- **`Graph`** — a DAG that also supports **conditional edges** (`add_edge(condition=...)`, `graph.py:279`)
  and **cycles** (`reset_on_revisit`, `graph.py:309`). Covers Sequential, Parallel, Generator-Critic,
  Iterative-Refinement.
- **`Swarm`** — autonomous handoff by agent description (Coordinator/Dispatcher).
- **agents-as-tools** — a sub-agent in `tools=[...]` (Hierarchical decomposition).

A node's executor can itself be a `MultiAgentBase` (`graph.py:168`) → patterns nest (Composite).

## Mapping + what each test asserts

| # | ADK pattern | Strands mechanism | Verified assertion |
|---|---|---|---|
| 1 | Sequential Pipeline | `Graph` linear edges | linear `execution_order` **and content lineage** — a codename injected at the input survives extract→analyze→write |
| 2 | Coordinator/Dispatcher | `Swarm` handoff by description | **both** directions: billing→`billing` only, tech→`tech` only, swarm `COMPLETED` |
| 3 | Parallel Fan-Out/Gather | `Graph` fan-out + fan-in | all 5 ran, synth gathered after all sources, **and measured faster than an equivalent sequential graph** (~42% wall-clock) |
| 4 | Hierarchical Decomposition | agents-as-tools, 2 levels | orchestrator→researcher→analyst; deepest agent's **sentinel surfaces in the top output** (lineage proof), bounded retry |
| 5 | Generator & Critic | `Graph` cycle + conditional exit | looped `gen→critic→gen→critic`, exited on a **typed ballot** `verdict==PASS` (not a substring) |
| 6 | Iterative Refinement | `Graph` cycle + `max_node_executions` | reviser/critic looped, early-exit before cap, **typed** `verdict==GOOD` |
| 7 | Human-in-the-Loop | `BeforeToolCallEvent` + `event.interrupt()` | real **pause → `result.interrupts` → resume**: APPROVE runs the refund, DENY blocks it |
| 8 | Composite | `Graph` nesting Swarm + 2 Graphs | the article's 3 stages run end-to-end: `triage`(Swarm)→`research`(parallel Graph)→`compose`(cyclic Graph) |

## Empirical findings (what the multi-run audit surfaced)

1. **Forced structured output works through `OpenAIModel`→proxy→Gemini.** `structured_output_model=Ballot`
   set at construction returns a typed `Literal` verdict even when the agent runs as a Graph node. This
   closes the "NOT VERIFIED" gap from the architecture doc and removes the brittle string-parse the gate
   was failing on (P5/P6 conditions read `ballot.verdict`).
2. **temp 0 does not fully pin Gemini.** Single runs hid two flakinesses the 3× audit caught:
   - **P2** ping-ponged (`coordinator→tech→coordinator→tech`) → swarm `FAILED`. Fixed with the
     documented `repetitive_handoff_detection_window` + "do not hand off" specialist prompts. Cost also
     dropped 8,364→2,359 tok once the loop was gone.
   - **P4** nested tool-calls aren't guaranteed first try; a bounded retry (1–2 attempts observed)
     makes it reliable — the repo's "treat LLM calls like external APIs, retry" rule.
3. **A sub-agent's `callback_handler` does not fire when it runs as a tool.** Callback-based detection
   *under-reported* P4's nested call (showed 0–2/3 even though the chain ran every time). Trustworthy
   signal = **lineage** (a sentinel from the deepest agent surfacing up top), not callbacks.
4. **All 8 are reproducible across 3 runs at temp 0** once the above are handled — relevant to the
   audit-reproducible gate, with the caveat that reproducibility required loop guards + retries, not
   temperature alone.
5. **Parallel fan-out is ~2× faster, but the speedup is tail-latency-noisy on the shared proxy.** P3 in
   isolation is 5/5 with `t_par≈9s` vs `t_seq≈19s` (~46%). In the full suite it inverted once (parallel
   bounded by the slowest of 3 concurrent calls, on a memory-stressed 2 GB proxy with ~330 MB free). A
   single-sample `t_par<t_seq` gate flaps; best-of-2 on the parallel side makes it robust. Takeaway: if
   you fan out for latency, the *concurrency benefit is real but variable on the proxy* — budget for tail
   latency, don't assume a fixed speedup.

## Semantic gap

ADK's named `output_key` + `{template}` interpolation has **no 1:1 Strands equivalent**: Graph keys
results by **node_id** and injects them as text (no `{var}` substitution). For an explicit named
whiteboard use `AgentState` / `SessionManager`, or a Swarm's `shared_context`.

## Honest caveats

- **P3** measures concurrency via wall-clock (parallel vs. an equivalent sequential graph); timing is
  network-dependent but the gap is large (~5 LLM round-trips vs ~3 phases).
- **P6** uses a count-based loop policy (`MIN_ROUNDS=2`, then exit on the typed verdict, capped) so the
  loop body deterministically executes rather than depending on the model failing pass 1.
- **P4** uses a bounded retry; without it the nested call occasionally needs a second attempt.
- Models: verified on **both** `gemini-2.5-flash` (OpenAI-compat proxy) and `claude-haiku-4-5` (native
  AWS Bedrock) — 8/8 pass + reproducible on each (`ADK_MODEL_PROVIDER=bedrock`). Topology is
  framework-inherent; the nested-call retry need is a *Gemini* tendency (Claude fired on the first attempt).

## Observability (per-run audit trace)

Every run is instrumented via Strands native hooks (`_trace.py`, no external collector). A
`TraceRecorder` is attached to every Agent reachable in the graph/swarm (walking `.nodes[*].executor`)
and records, in order, **per-node invocation boundaries and every tool call + result** with sequence
numbers and relative timing. The harness writes one JSONL per run to `traces/<pattern>_run<N>.jsonl` —
the audit artifact you attach to a gate decision and diff across runs. Example (P5, generator-critic loop):

```json
{"seq":2,"ms":4968,"evt":"invoke.start","agent":"critic"}
{"seq":3,"ms":6061,"evt":"tool.start","agent":"critic","tool":"Ballot","input":{"verdict":"REVISE","reason":"...no concrete number..."}}
{"seq":4,"ms":6061,"evt":"tool.end","agent":"critic","tool":"Ballot","result":"[success] ...validated Ballot..."}
{"seq":6,"ms":6062,"evt":"invoke.start","agent":"gen"}
```

The trace also makes a mechanism visible: **`structured_output_model` is implemented as a forced
tool call** (the `Ballot` tool above), and the typed verdict + reason are captured for audit. Reasoning
/ chain-of-thought is *not* captured — Gemini via the OpenAI-compat proxy doesn't surface a separate
reasoning trace (matches the architecture doc's Q5 caveat); the trace records auditable **actions**, not
hidden thought. For an OTel span tree to Jaeger instead, `_trace.enable_otel()` mirrors
`08_production/observability.py`.

## Files

`_model.py` (transport) · `_harness.py` (multi-run audit + token accounting) · `_trace.py` (hook-based
execution trace) · `p1…p8_*.py` (one pattern each, with `trial(rec)` + assertions) · `run_all.py` (full
audit) · `traces/` (per-run JSONL audit traces).

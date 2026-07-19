# Session Reflection — 2026-07-19: Publish, Ecosystem Delta, Tier 22

Cross-cutting learnings from a large session. Per-level detail is in `level-94..100` + `level-97b`;
this file captures what spans them.

---

## What the session did

1. **Public-publish hardening.** Rebuilt the repo on a clean single-commit history (the old history
   was corrupt and carried pre-scrub AWS account IDs), split the 2,700-line `LEARNING_PLAN.md` into
   one doc per lesson under `docs/levels/` (L01–L93), rewrote the README as a recruiter-facing front
   door in the user's own voice, and pushed public.
2. **Ecosystem delta (v1.42 → v1.48).** Fresh clone of the Strands monorepo + three parallel
   explorers + web research → `docs/work/research/reports/2026-07-18_strands-ecosystem-delta-*.md`
   (code-level evidence, resolved unknowns, mermaid, external coverage) and an impact evaluation
   (`LEARNING_PLAN_v148_impact.md`).
3. **Tier 22 (L94–L100 + L97b).** Upgrade + regression sweep; checkpoint runtime; interventions +
   Cedar; the memory rematch (native underperforms on the test store, reaches parity with real
   semantic recall); sandbox tier (Strands Shell vs Podman); red-team the memory channel;
   context-management verification. All built live, gate-clean, reflected, committed.

## Meta-learnings (the durable ones)

### 1. Source-first, and clone the repo when the behavior is native
The session's defining discipline, and its worst error. I concluded the Strands Shell SSRF
enforcement was "unobservable" — a guess dressed as a finding — because I read only the thin Python
wrapper over a Rust `.so`. Cloning `github.com/strands-agents/shell` and reading `curl.rs` +
`vfs_kernel.rs` showed the truth: the allowlist is *additive trust*, and the default SSRF guard IS
observable (blocks IMDS including the `[::ffff:169.254.169.254]` bypass, loopback, private). Rule:
read the installed source fully; if the behavior lives in a compiled layer, clone the source repo;
design tests *from* the source. Cost of guessing = wasted cycles + trust; cost of cloning = minutes.

### 2. Priors are hypotheses; the run is the authority
Across L97, L98, L99 I repeatedly coded a hypothesis into a gated assertion and had it refuted live
("extractor lands 0 facts"; "memory bypasses prompt hardening"; "allowlist blocks example.org").
The fix each time: stop at strike 2, run a controlled probe to isolate the truth, then rewrite the
checks to encode what the runs show and demote variable behavior to reported observations. A red
result with a root cause is a finding, not a failure — several of Tier 22's best results are honest
negatives (L97 native underperforms; L99 explicit-policy defends; L100 accuracy lift didn't
reproduce on Gemini's 1M window).

### 3. Enforce rules with mechanisms, not memory
I leaked a live AWS account ID into a public commit; the post-commit scan caught it, I scrubbed and
squashed it out of reachable history, then built `tools/check_no_aws_ids.py` + a pre-commit hook
(`tools/install_hooks.sh`) so it cannot recur — verified with a positive control. Knowing the rule
("no account info in md/py") was not enough; the hook is. Same spirit as `no_sim_check`.

### 4. Cheapest experiment that answers the question
The "does native memory match hand-built?" question was scoped for a billable Bedrock KB; a ~35-line
local `SemanticMemoryStore` answered it identically at zero cost/teardown risk (L97b). L100 reached
the pressured-window regime by capping the *reported* `context_window_limit` in a subclass instead of
paying for a giant context. Probe-first also showed the vended KB store only *attaches* to a
pre-existing KB — so provisioning would have been all mine. Reserve billable infra for when the
integration itself is the question.

### 5. The Tier 22 thesis: first-party-ization
The delta shipped SDK-native versions of five things this repo hand-built (memory, interventions,
sandbox, storage, agentic context management), turning the hand-built levels into the mechanism layer
under the new primitives. Verified: native memory ties the hand-built stack only with real recall;
interventions unify four control lessons; `auto` context management confirms the ~55% token claim.
Two repo theses got upstream confirmation — the trust boundary (tools 0.8.x = five pure-hardening
releases) and determinism-as-architecture (checkpoint/interrupt/cancel is now a formal stop-reason
state machine).

## Loose ends

Forward work (Tier 22 follow-ons, standing items, and the L97b `971` data-hygiene note) now lives in
`NEXT_STEPS_PLAN.md` — that is the single source of truth for what to do next.

One caveat that belongs with the incident record: the briefly-leaked account ID lives in a
now-unreachable commit; GitHub may serve orphaned SHAs until GC — a support purge would make it
provably gone.

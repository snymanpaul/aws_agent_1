# Session Reflection — 2026-06-02
**Scope:** 11 lessons built/verified/reflected on **Gemini 2.5 Flash** and **live AWS**
(the agentic sandbox account, `<agentic-account-id>`), plus repo recovery, an account migration,
and unlocking Claude on Bedrock. 17 commits; observations 750 → 843.

---

## Lessons (each: built → live-verified → reflected → committed)

| L | Title | One-line takeaway |
|---|-------|-------------------|
| 61 | Token Counting | `chars/4` under-counts code/CJK/punct 40–75%; native `count_tokens` == billed tokens |
| 64 | SDK Snapshots | selective in-memory capture; branch many timelines from one immutable snapshot |
| 65 | Experimental Checkpoint | **types-only in 1.42** — realized durable exec via after_model/after_tools hooks |
| 70 | Native Interrupts (HITL) | `event.interrupt()` pauses the loop; approve/deny gates a tool; resume by id |
| 71 | Agent Registry | **approval gates discovery** — a DRAFT skill is invisible to search until APPROVED |
| 72 | Code Interpreter | managed sandbox; structured results; agent ran `fib(20)=6765` in it |
| 73 | Browser | drive remote Chrome over CDP; **async tools for an async agent** |
| 62 | Bedrock Caching + strict_tools | cache TTL + `strict_tools` on Claude (after the use-case form); cache-point trap |
| 74 | Workload Identity | secrets in a vault, not in code; `@requires_api_key` injects at runtime |
| 75 | Config Bundles | Git-like versioned config (commits/branches/lineage) keyed to resource ARNs |
| 76 | AG-UI Native | full protocol: text, tools, **shared state**, steps, thinking, components, **HITL** |

Per-lesson detail in `level-N-reflection.md`; raw observations in `observations.jsonl`.

---

## Cross-cutting work (not a "lesson")

- **Repo recovery:** an OneDrive-offload had stripped git objects; commits failed because the
  cache-tree forced a full-tree rebuild. Restored 15 intact blobs (`git hash-object -w`,
  not `git add` — stat-cache no-ops), regenerated 2 missing trees (`git add --renormalize`
  + `--amend`), recorded the unrecoverable deletions. HEAD made fully readable.
- **Wrong-account episode:** every AWS lesson (this session + prior L27/L67) had been run on
  the *data-only* sandbox because `todo.md` documented the wrong profile. Inventoried the
  stray resources (`MIGRATION_*.md`), re-verified the lessons on the correct account, and
  cleaned the sandbox (one orphaned service-linked identity remains).
- **Claude unlock:** Claude on Bedrock was gated behind the account-wide **use-case form**;
  once submitted, L62 was completed on real Claude.

---

## The meta-insights (the disciplines that kept paying off)

1. **Validate empirically; don't trust the map.** Caught repeatedly: the `count_tokens`
   docstring claims tiktoken but the path is char-based (L61); `experimental.checkpoint` is
   types-only despite a full docstring (L65); `agreementAvailability` metadata "lied" about
   Claude while a real Converse call + `GetUseCaseForModelAccess` told the truth (L62).
2. **A single success is not proof.** A Claude Converse call flake-succeeded once, then
   failed 3× — the real gate was a form. Re-confirm with repeats (L62).
3. **Confirm the target, not the documented default.** A wrong account number in a project
   note propagated silently across many sessions. `sts get-caller-identity` + the account's
   *purpose* before provisioning.
4. **Validate in layers.** For a server: in-process (`TestClient`) ≠ off-process (a real
   socket) ≠ a rendered client. Name which claim you're making (L76).
5. **Async tools for an async agent.** Sync Playwright's greenlet loop collides with Strands'
   asyncio loop — go uniformly async (L73). Same family as the `LESSON_DOTENV`-clobbers-SSO
   trap (L72) and the module-level shared-state leak (L76).
6. **Probe-first for new AWS services.** Offline `service_model` shapes + a live, self-tearing
   -down smoke probe before writing — every AWS lesson left its account clean.

---

## Open items
- `l67demopaymentmanager` — an orphaned service-linked workload identity in the data sandbox
  (caller can't delete; needs the linking service or AWS support).
- Pre-milestone git history has unrecoverable missing objects (a full-history push would hit
  them); current HEAD is sound for local work + new commits.
- Deferred lessons still open: protocol-level HITL interrupts, managed harness, filesystem
  persistence (AWS previews not yet in the Python SDK).

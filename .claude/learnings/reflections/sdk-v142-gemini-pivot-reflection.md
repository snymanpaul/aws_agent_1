# SDK v1.42 Upgrade + Gemini Pivot — Reflection (2026-06-02)

## Context
Extending the lessons to demonstrate genuinely-new 2026-Q2 SDK surface. Two
exogenous shifts hit mid-stream: (1) the Anthropic/Claude budget was exhausted,
forcing the whole course onto **Gemini 2.5 Flash**; (2) a brutal, hours-long
environment hang that turned out to have nothing to do with the SDK.

## Step 0 — dependency upgrade (committed `23a1460`)
`strands-agents 1.38->1.42`, `strands-agents-tools 0.5.2->0.7.0`,
`bedrock-agentcore 1.8->1.12`, `starter-toolkit 0.3.6->0.3.9`. Transitive:
`fastapi 0.124->0.136`, **`starlette 0.50->1.2` (major)**. Verified by a 16/16
offline import-smoke probe (every Tier-17/18 API surface present). pytest gives
no signal here (no collectable tests); the broad lesson-import sweep proved
fragile and was abandoned for the import-smoke.

## Phase 1 — shipped & verified on Gemini
| Lvl | Feature | Commit | Verified |
|-----|---------|--------|----------|
| L64 | Invocation `Limits` (turns/token caps) | `a11a1ae` | 4 iters, graceful stop_reason, priority, reset |
| L15 | Proactive compression (Iter 9) | `2a19c68` | hook fired (debug log), 20->13 msgs before call |
| L7  | Swarm `MultiAgentPlugin` | `88c68ac` | 8 node events, Status.COMPLETED |
| L8  | Graph `MultiAgentPlugin` | `3227f86` | 8 node events, Status.COMPLETED |
| L22 | tools 0.7.0 hardening (Iter 13) | `3ef71d8` | 9/9 — AST sandbox, redaction, cron sanitize |

## The infra battle — root cause (cost ~hours)
Lessons hung at **0% CPU forever** during import. Misdiagnosed in order:
iCloud-eviction (0 `.icloud` placeholders), OTel (`OTEL_SDK_DISABLED` no help),
stray procs, corrupt pycache — all wrong. **macOS `sample <pid>` + `lsof -p`**
on the live hung PID nailed it: stuck in `read()` on a freshly-written
`tools/__pycache__/__init__.cpython-313.pyc`. Raw `cat` of every module was
instant (0.01s) — so it was the *newly-written `.pyc`* under iCloud-synced
`~/Documents` stalling on read (iCloud/EDR new-file intercept), **not** file
content. **Fix: `PYTHONDONTWRITEBYTECODE=1`** (import: ∞ -> 1.04s).
**Lesson: on a 0%-CPU import hang, go straight to `sample`+`lsof`.**

## Infra fixes
- **LiteLLM DB-less**: Postgres is only for optional features (spend/keys/UI).
  The bundled Postgres OOM-looped (RestartCount=9) in the 2GB podman VM. Running
  litellm standalone without `DATABASE_URL` → healthy in seconds. Old corrupt PG
  data preserved at `data/postgres.corrupt.bak.20260602`.
- **Gemini direct**: `get_model` routes `gemini*` straight to Google AI
  (`GeminiModel`, no proxy), via `LESSON_DOTENV` (key file) + `LESSON_MODEL`
  (global override) + `context_window_limit` passthrough. `gemini-2.0-flash` is
  **retired** → `gemini-2.5-flash`.

## Plan corrections found empirically
- **L66**: `async_mode` is an `AgentCoreMemoryConfig` field (`self.config.async_mode`),
  NOT an `AgentCoreMemorySessionManager(async_mode=...)` ctor kwarg.
- **L34**: DatasetClient needs **botocore >=1.43.19** (`create_dataset` absent in
  1.43.2; SDK bundles no model). And **datasets are NOT wired to `evaluate`** —
  no op takes a `datasetId`; they are standalone curated eval-example resources
  (`inlineExamples`/`s3Source`, schema PREDEFINED/SIMULATED).
- **L7/L8**: a `MultiAgentPlugin` subclass with a custom `__init__` must call
  `super().__init__()` or `self._hooks` is unset.
- **L22**: already had 12 iterations (docstring said 8); tool-security is Iter 13.

## Run recipe (this machine)
```
PYTHONDONTWRITEBYTECODE=1 LESSON_DOTENV=/path/to/your/.env \
  uv run python <lesson>.py
```

## Status / next
Phase 1 complete. Phase 2 in progress: **P2.5 L34 DatasetClient** (API probed,
deps bumped, lesson code next), then P2.6 L66 async memory, P2.7 L27 header
forwarding/class entrypoint, P2.8 Payments (needs billable provisioning — will
confirm first). Phase 3 docs after.

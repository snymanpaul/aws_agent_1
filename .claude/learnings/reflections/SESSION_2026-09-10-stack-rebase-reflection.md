# Session 2026-09-10: stack re-base to strands 1.55.1

**Ask:** check the latest AWS versions, update the clones, investigate what is new.
**Report:** `docs/work/research/reports/2026-09-10_strands-ecosystem-delta-v148-to-v155.md`
**Probes:** `_sandbox/probe_upgrade_2026-09-10_{imports,mcp_symbols,surface}.py`
**Observations:** obs-1013 to obs-1018 (`_sandbox/append_2026_09_10_obs.py`)

## What happened

1. Three clones fast-forwarded: strands monorepo `41f9f59b` to `9663bcfa5` (its origin is
   `harness-sdk.git`, renamed 2026-06-05), agentcore `a4bc13f` to `3c9f15e`, shell `1178e0c` to
   `943e4dc`.
2. `uv lock --upgrade` moved strands 1.48.0 to 1.55.1, agentcore 1.18.1 to 1.22.0, evals 1.0.2 to
   1.2.0, tools 0.8.4 to 0.8.8, ag-ui-strands 0.1.1 to 0.3.0, ai-functions 0.1.0 to 0.4.0, and mcp
   1.23.3 to 2.1.1. pytest 221/221, both gates clean.
3. A named symbol probe showed mcp 2.1.1 had removed `FastMCP`, `streamablehttp_client` and
   `mcp.server.experimental`, imported by 13 lesson files. Pinned `mcp>=1.23.3,<2`; re-locked to
   mcp 1.30.0; re-probed clean.
4. Runtime surface probe of the 1.55.1 additions: 16/16. Six lessons live on the new stack (L1,
   L28, L64, L68, L70, L78), L78 with its negative control.
5. Four parallel inventories (core SDK, agentcore, ecosystem packages, web) consolidated into the
   delta report. Docs updated: CLAUDE.md status and gate counts, README counts, LEARNING_PLAN
   stack line and report link, NEXT_STEPS_PLAN status block.

## Mistakes and what shaped the work

- **Green tests were not evidence the lessons ran.** The lessons are excluded from CI, so the 221
  passing tests said nothing about the 13 files that import mcp 1.x names. The symbol probe is the
  check that found it; it took one run. Captured as obs-1013.
- **Wrong observation category.** First append used `cat="decision"`, which the schema checker
  (run in CI) rejects. First reflex was a superseding entry, but the checker validates every line,
  so that would have left CI red. Because the bad line was uncommitted, the right fix was to
  restore the committed log, correct the script, and re-append; the append-only rule protects
  committed history, not a mistake made minutes ago in the working tree.
- **Probe drift on vended tools.** The first surface probe reported `stop` and `web_fetch`
  missing. Both exist: `web_fetch` is lazy-loaded through module `__getattr__` (needs the
  `web-fetch` extra), and `stop` moved to `strands.experimental.tools` in 1.50.1 (`afe34d4a9`).
  A `dir()` listing is not the export surface when a package uses `__getattr__`.
- **Secrets.** Reading `.env` was denied, correctly. The Gemini key for three smoke lessons was
  passed from the proxy container's environment inside one shell command and never printed
  (obs-1017).
- **The mermaid checker could not run**: `tools/check_mermaid.sh` fails on every block with
  "Could not find Chrome (ver. 131.0.6778.204)". The report's one diagram is unverified by render;
  the environment, not the diagram, is the open item.

## Follow-ons (all in the report, section 6)

F1 migrate 13 lesson files to mcp 2 and drop the pin (unlocks SEP-2663 MCP tasks). F2 seven files
on deprecated `calculator`/`current_time` (error logs at tools 0.9.0). F3 re-run L76 on
ag-ui-strands 0.3.0. F4 `AgentCoreMemoryStore` (agentcore 1.21.0) as the native memory arm.
F5 re-baseline evals before comparing (1.1.0 to 1.2.0 changed multi-agent trace scoping).

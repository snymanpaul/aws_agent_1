# L73: AgentCore Browser — Managed Headless Chrome over CDP

**Code:** `16_agentcore_tools/browser.py`
**Reflection:** [`level-73-reflection.md`](../../.claude/learnings/reflections/level-73-reflection.md)

**Status:** Done (Tier 20, live AWS; self-tearing-down).

**Empirical findings (live-validated):**
- `browser_session(region)` → `generate_ws_headers()` (wss + SigV4) → Playwright `connect_over_cdp`
  — no local browser binaries; navigate/fill/click/JS all work.
- `generate_live_view_url` + `take_control`/`release_control` = human-on-the-loop for the browser.
- **Gotcha:** sync Playwright's greenlet loop collides with Strands' asyncio loop (`greenlet.error`)
  — go uniformly async (`async_playwright` + `invoke_async` + async `@tool`).
- Needs the `playwright` package (package only, no local browser install).

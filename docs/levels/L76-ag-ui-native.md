# L76: AG-UI Native — `serve_ag_ui` / `build_ag_ui_app`

**Code:** `19_agentcore_agui/agui_native.py` (client: `19_agentcore_agui/client.html`)
**Reflection:** [`level-76-reflection.md`](../../.claude/learnings/reflections/level-76-reflection.md)

**Status:** Done (Tier 20, local — no AWS needed). Realizes the long-open L67 AG-UI slot.

**Empirical findings:**
- `build_ag_ui_app(entrypoint)` builds a Starlette app (`/invocations` SSE, `/ws`, `/ping`).
- Pass an ENTRYPOINT (async-gen `RunAgentInput` → AG-UI events), **not** a raw Agent — else
  `RUN_ERROR` "Input prompt must be of type…".
- Adapter event sequence: `RunStarted → TextMessageStart → TextMessageContent` (delta from
  `stream_async` `event["data"]`) `→ TextMessageEnd → RunFinished`.
- `RunAgentInput` requires `forwardedProps` et al. (missing → HTTP 400); mid-stream errors →
  `RunErrorEvent`. Test headlessly with Starlette `TestClient`.
- Contrast with L44 (self-hosted AG-UI adapter): this is the platform-native serving path.

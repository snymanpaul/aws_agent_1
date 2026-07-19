# Level 76: AG-UI Native — Serve a Strands Agent over the Agent-to-Frontend Protocol
**Date:** 2026-06-02 | **File:** `19_agentcore_agui/agui_native.py`
**Depends on:** L44 (AG-UI self-hosted), L36 (streaming), L27 (AgentCore runtime)
**Unlocks:** any AG-UI frontend can drive your agent; deploy via `serve_ag_ui`

---

## Part 1 — For Humans

### What We Built
A way to put a Strands agent behind the standard agent-to-frontend protocol (AG-UI)
with essentially one call. `serve_ag_ui` / `build_ag_ui_app` give you SSE on
`/invocations`, a WebSocket on `/ws`, and a health check on `/ping` — so any AG-UI
frontend can stream a run. We drove it headlessly and watched the canonical event
sequence come back.

### How It Works

```
 POST /invocations (RunAgentInput)
        |
   entrypoint(run_input)  -- async generator
        |
   RUN_STARTED -> TEXT_MESSAGE_START
        -> TEXT_MESSAGE_CONTENT (delta) x N   <- from agent.stream_async
        -> TEXT_MESSAGE_END -> RUN_FINISHED
        |
   SSE stream (text/event-stream) to the frontend
```

### What Went Wrong
1. **Passed a raw agent.** `build_ag_ui_app(strands_agent)` looked right but the run
   came back as a single `RUN_ERROR`: *"Input prompt must be of type ..."*. The app
   calls the handler with a `RunAgentInput`, and a raw `Agent` treats that as a prompt.
   The app wants an **entrypoint** — an async generator that turns a `RunAgentInput`
   into AG-UI events. Writing that ~10-line adapter fixed it.
2. **Missing a required field.** A `RunAgentInput` needs `forwardedProps` (and several
   others); leaving it out is a clean HTTP 400 before the stream even opens.

### What Worked
1. **The adapter pattern.** Yield `RunStarted → TextMessageStart →
   TextMessageContent(delta)* → TextMessageEnd → RunFinished`, pulling each delta from
   `stream_async` (`event["data"]`). The frontend sees a normal AG-UI run.
2. **TestClient for SSE.** `TestClient(build_ag_ui_app(entrypoint))` + a POST lets you
   assert the whole event sequence without running a server.

### The Single Most Important Thing
AG-UI flips the integration: instead of inventing a streaming JSON contract for your
frontend, you emit a *standard vocabulary* of run/message/tool events, and any AG-UI
client already knows how to render them. The only code you write is the thin adapter
that maps your agent's stream onto that vocabulary — and `serve_ag_ui` does the
transport. Your agent becomes a drop-in backend for the whole AG-UI ecosystem.

---

## Part 2 — For LLMs

### Architecture

```mermaid
flowchart TD
    F["AG-UI frontend"] -->|POST /invocations RunAgentInput| A["AGUIApp (Starlette)"]
    A --> E["entrypoint(run_input) async-gen"]
    E --> S["agent.stream_async"]
    S -->|event['data']| TC["TextMessageContentEvent(delta)"]
    E --> EV["RunStarted / TextMessageStart / End / RunFinished"]
    TC --> SSE["SSE text/event-stream"]
    EV --> SSE
    SSE --> F
```

```
[AG-UI frontend] --POST /invocations RunAgentInput--> [AGUIApp (Starlette)]
        ^                                                     |
        |                                                     v
        |                                       [entrypoint(run_input) async-gen]
        |                                              |             |
   [SSE text/event-stream] <----------------+          v             v
        ^                                    |   [agent.stream_async]  [RunStarted/
        |                                    |          |              TextMessageStart/
        +----[RunStarted..RunFinished]-------+   event['data'] ->      End/RunFinished]
                                              [TextMessageContent(delta)]
```

### Decision Log

| Decision | Why | Trade-off |
|----------|-----|-----------|
| entrypoint adapter, not raw agent | The app passes a RunAgentInput, not a prompt | ~10 lines of mapping |
| Map stream_async event["data"] | That's where Strands text deltas are | Other event kinds (tools) need more mapping |
| TestClient, not a live server | Headless, assertable, fast | Doesn't exercise real network/WS |
| Local (no AWS) | serve_ag_ui builds a local Starlette app | Deploy step is separate |

### Pseudocode — Key Patterns

```
# Strands -> AG-UI entrypoint
async def entrypoint(run_input):
    mid = new_id()
    yield RunStartedEvent(thread_id=run_input.thread_id, run_id=run_input.run_id)
    yield TextMessageStartEvent(message_id=mid, role="assistant")
    for ev in agent.stream_async(run_input.messages[-1].content):
        if ev["data"]: yield TextMessageContentEvent(message_id=mid, delta=ev["data"])
    yield TextMessageEndEvent(message_id=mid)
    yield RunFinishedEvent(thread_id=run_input.thread_id, run_id=run_input.run_id)

app = build_ag_ui_app(entrypoint)        # serve_ag_ui(entrypoint, port=8080) to run
```

### Observation Log

| # | Category | Topic | Observation |
|---|----------|-------|-------------|
| 1 | insight | ag-ui-native-serve-one-call | serve_ag_ui/build_ag_ui_app -> SSE /invocations + WS /ws + /ping; local Starlette |
| 2 | mistake | ag-ui-needs-entrypoint-not-raw-agent | pass an async-gen entrypoint, not a raw Agent (else RUN_ERROR on the prompt type) |
| 3 | pattern | strands-to-agui-event-mapping | RunStarted->TextMessageStart->Content(delta from event["data"])->End->RunFinished |
| 4 | insight | runagentinput-required-fields-400 | RunAgentInput requires forwardedProps et al.; bad input -> 400; mid-run error -> RunErrorEvent |
| 5 | pattern | test-sse-app-with-testclient | TestClient(app).post("/invocations"); parse SSE types/deltas; no live server |

### Forward Links

- **vs L44 (self-hosted AG-UI):** same protocol; `serve_ag_ui` is the AgentCore-native
  one-liner instead of a hand-rolled SSE server.
- **Builds on L36 (streaming):** the deltas come from `stream_async`.
- **Revisit when:** wiring an agent to an AG-UI frontend, or adding tool-call / reasoning
  events (ToolCall*/Reasoning* event classes) to the adapter.

---

## Update — Extended: tool calls + a real frontend

Pushed L76 from "text over the wire" to "a tool-using agent a browser can render".

1. **Tool-call events.** The entrypoint now maps Strands tool use to AG-UI:
   `contentBlockStart.toolUse → ToolCallStart`, `toolUse.input → ToolCallArgs`,
   `contentBlockStop → ToolCallEnd`. The tool **result isn't in the model stream**
   (the SDK runs the tool internally) — so the tool function appends its return to a
   list and the entrypoint drains it → `ToolCallResultEvent`. Verified sequence:
   `RUN_STARTED → TOOL_CALL_START/ARGS/END/RESULT → TEXT_MESSAGE_* → RUN_FINISHED`.
2. **A real web client, same-origin.** `AGUIApp.routes` is a mutable list, so I append
   `GET /` serving a tiny HTML/JS AG-UI client (fetch `/invocations`, read the SSE via
   `response.body.getReader()`, render tool chips + text). Same origin as `/invocations`
   → no CORS. `serve` mode runs it: `python agui_native.py serve` → `http://127.0.0.1:8080/`.
3. **Validation, honestly layered.**
   - *Server (in-process):* `TestClient` asserts the real event stream — ✅.
   - *Server (off-process):* a live `serve` process + `curl` over a real **socket** —
     `/ping` healthy, `/invocations` streamed the full tool+text sequence — ✅.
   - *Browser render:* set up (server live, client served at `/`) but the automated
     Chrome navigation was **declined**, so the visual layer is left for the user to
     confirm by opening the URL. The first two layers prove the protocol end-to-end.

**Lesson:** "did it work?" needs a layered answer — in-process test, off-process socket,
and a rendered client are three different claims. The first two are fully nailed; the
third is one click away.

---

## Update 2 — The full vocabulary (generative UI)

Critique: "the AG-UI standard has more than that" — correct. Text + tools is ~a third
of it. Rebuilt L76 to emit the rich vocabulary and render a real **generative UI**:

- **Shared state (the headline):** `STATE_SNAPSHOT` once + `STATE_DELTA` (RFC-6902
  JSON-Patch) as the run progresses — `/status` transitions, `/city` parsed from the
  tool args, `/weather` from the tool result, `/tools_called` incremented. State is
  **adapter-owned**, not from the model. The frontend applies the patches to a local
  copy and renders a **live state panel** — that's the difference between AG-UI and
  plain SSE chat.
- **Steps:** `STEP_STARTED/FINISHED` (understand → tool:get_weather → answer) → a steps
  timeline in the UI.
- **Thinking:** `THINKING_START → THINKING_TEXT_MESSAGE_* → THINKING_END` → an inline
  reasoning block, shown apart from the answer.
- Verified **all 18 event types** stream over a real socket; the vanilla `client.html`
  (served via `FileResponse` on the appended `GET /`) renders state panel + steps +
  thinking + tool cards + chat from one SSE stream. A production app would use an AG-UI
  framework client (e.g. CopilotKit) rather than hand-rolled JS.
- Still unshown (further capabilities): `MESSAGES_SNAPSHOT`, `ACTIVITY_*`, `CUSTOM/RAW`,
  and the **input** side — frontend-defined tools + shared state + context (human-in-the-loop).

**Lesson:** AG-UI's value isn't streaming text — it's a *shared, structured state* the
agent mutates and the frontend renders. Treat the entrypoint as the place that projects
your agent's run onto that state vocabulary.

---

## Update 3 — Generative components + human-in-the-loop

Two more rungs, both visible in the browser:

- **Agent-selected component (generative UI):** the agent emits `CustomEvent(name=
  "renderComponent", value={component:"WeatherCard", props})` (`type:"CUSTOM"`). The
  frontend has a *pre-coded* `WeatherCard` and renders it with the agent's props. So the
  AI **picks + parameterizes a component**; it does **not** author UI code. (Answers the
  question "did the AI generate the UI?" — no: content is agent-generated at runtime,
  presentation is developer-coded at build time.)
- **Human-in-the-loop via a frontend-defined tool:** the agent calls `ask_temperature_unit`
  (a tool the *frontend* fulfills). The run **pauses** — `RUN_FINISHED` with the tool
  call and **no result**. The frontend renders a °C/°F picker; the human's pick returns
  as `run_input.state.unit` in the **next** run, which resumes the work and renders the
  `WeatherCard` in the chosen unit (21 °C → 70 °F). Pause/resume spans **HTTP turns via
  shared state** — the AG-UI counterpart to L70's in-process interrupt resume.

**Lesson:** AG-UI is *bidirectional*. The agent doesn't just push events to the UI; the
UI pushes tools, state, and human decisions back. The entrypoint is the projection layer
in both directions.

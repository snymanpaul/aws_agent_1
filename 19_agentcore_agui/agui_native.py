"""
Level 76: AG-UI Native — Serve a Strands Agent with the FULL Event Vocabulary
============================================================================
AWS Bedrock AgentCore — `bedrock_agentcore.runtime.ag_ui` (`serve_ag_ui`,
`build_ag_ui_app`).

Goal: expose a Strands agent over AG-UI — the standard agent-to-frontend protocol —
using its rich event vocabulary, not just streamed text. A real AG-UI frontend then
renders a *generative UI* (live shared state + steps + thinking + tool cards + text),
all from one SSE stream. You write only the entrypoint adapter; `serve_ag_ui` does
the transport, and a separate `client.html` (served same-origin) is the frontend.

The AG-UI event families this lesson emits (there are more):
    lifecycle : RUN_STARTED / RUN_FINISHED / RUN_ERROR, STEP_STARTED / STEP_FINISHED
    thinking  : THINKING_START / THINKING_TEXT_MESSAGE_* / THINKING_END  (reasoning, shown apart)
    tools     : TOOL_CALL_START / ARGS / END / RESULT
    state     : STATE_SNAPSHOT + STATE_DELTA (JSON-Patch) — the SHARED, generative-UI state
    text      : TEXT_MESSAGE_START / CONTENT / END
    (also MESSAGES_SNAPSHOT, ACTIVITY_*, CUSTOM/RAW; input carries frontend tools + state + context)

The key realization (cost a 500): pass an ENTRYPOINT (async generator
RunAgentInput -> AG-UI events), NOT a raw Strands `Agent`.

Depends on: L44 (AG-UI self-hosted), L36 (streaming), L27 (AgentCore runtime)
Unlocks:    a real generative-UI frontend driven by any AG-UI client

Iterations (headless asserts):
  1. Protocol surface  — routes /, /invocations (SSE), /ping, /ws.
  2. Full run          — one run emits RUN/STEP/THINKING/TOOL_CALL/STATE/TEXT events.
  3. Shared state      — a STATE_SNAPSHOT then STATE_DELTA patches mutate live state.
  4. Validation        — malformed RunAgentInput -> HTTP 400.

Critical API facts (validated by probe + a real browser, not docs):
    * build_ag_ui_app(entrypoint) -> Starlette AGUIApp (POST /invocations SSE, /ws, /ping).
      AGUIApp.routes is mutable -> append GET / serving client.html same-origin (no CORS).
    * Map Strands stream_async -> AG-UI:
        event["data"] (str)                                   -> TextMessageContentEvent
        ["event"]["contentBlockStart"]["start"]["toolUse"]    -> ToolCallStartEvent (+ ARGS/END)
      The tool RESULT isn't in the model stream (the SDK runs the tool), so capture it
      from the tool fn and drain -> ToolCallResultEvent.
    * Shared state is adapter-owned: emit StateSnapshotEvent(snapshot=dict) once, then
      StateDeltaEvent(delta=[{"op":"replace","path":"/k","value":v}, ...]) (RFC-6902 JSON-Patch).
      The frontend applies the patches to its copy and re-renders.
    * Steps: StepStartedEvent / StepFinishedEvent (step_name). Thinking: ThinkingStartEvent ->
      ThinkingTextMessageStart/Content(delta)/End -> ThinkingEndEvent.

Usage:
    LESSON_DOTENV=/path/.env uv run python 19_agentcore_agui/agui_native.py          # headless asserts
    LESSON_DOTENV=/path/.env uv run python 19_agentcore_agui/agui_native.py serve     # server + generative UI at http://127.0.0.1:8080/
"""

import json
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool

from bedrock_agentcore.runtime.ag_ui import build_ag_ui_app
from ag_ui.core import (
    RunStartedEvent, RunFinishedEvent,
    StepStartedEvent, StepFinishedEvent,
    ThinkingStartEvent, ThinkingTextMessageStartEvent,
    ThinkingTextMessageContentEvent, ThinkingTextMessageEndEvent, ThinkingEndEvent,
    StateSnapshotEvent, StateDeltaEvent, CustomEvent,
    TextMessageStartEvent, TextMessageContentEvent, TextMessageEndEvent,
    ToolCallStartEvent, ToolCallArgsEvent, ToolCallEndEvent, ToolCallResultEvent,
)
from starlette.responses import FileResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from tools import get_model

_tool_results: list = []


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    result = f"{city}: 21C, sunny"
    _tool_results.append(result)
    return result


agent = Agent(model=get_model("gemini-2.5-flash"), tools=[get_weather],
              system_prompt="Use get_weather for weather questions, then answer in one sentence.",
              callback_handler=None)


def _patch(path: str, value):
    return StateDeltaEvent(delta=[{"op": "replace", "path": path, "value": value}])


async def entrypoint(run_input):
    """Adapt the agent to the FULL AG-UI vocabulary: HITL + state + steps + thinking + tools + text."""
    mid = uuid.uuid4().hex
    yield RunStartedEvent(thread_id=run_input.thread_id, run_id=run_input.run_id)

    # Shared state the frontend renders live (generative UI), mutated via JSON-Patch deltas.
    # `unit` arrives in run_input.state once the HUMAN has chosen it (see the HITL gate).
    unit = (run_input.state or {}).get("unit")
    state = {"status": "understanding", "city": None, "unit": unit, "weather": None, "tools_called": 0}
    yield StateSnapshotEvent(snapshot=dict(state))

    # HUMAN-IN-THE-LOOP: a FRONTEND-defined tool. If the human hasn't chosen a unit, the
    # agent CALLS ask_temperature_unit and the run PAUSES (RUN_FINISHED, no tool result) —
    # the frontend renders a picker, the human answers, and the NEXT run arrives with
    # state.unit set. (This is where L70 interrupts meet AG-UI, across HTTP turns.)
    if not unit:
        yield StepStartedEvent(step_name="ask the human")
        tid = uuid.uuid4().hex
        yield ToolCallStartEvent(tool_call_id=tid, tool_call_name="ask_temperature_unit")
        yield ToolCallArgsEvent(tool_call_id=tid, delta=json.dumps({"question": "Show temperature in:", "options": ["°C", "°F"]}))
        yield ToolCallEndEvent(tool_call_id=tid)
        yield _patch("/status", "awaiting human input")
        yield StepFinishedEvent(step_name="ask the human")
        yield RunFinishedEvent(thread_id=run_input.thread_id, run_id=run_input.run_id)
        return  # PAUSE — resumed by the next run once the human picks a unit

    # RESUMED: the human's unit choice is in shared state -> do the work in it.
    yield StepStartedEvent(step_name="understand")
    yield ThinkingStartEvent(title="Planning")
    yield ThinkingTextMessageStartEvent()
    yield ThinkingTextMessageContentEvent(delta=f"Human chose {unit}. Call get_weather, then answer in {unit}.")
    yield ThinkingTextMessageEndEvent()
    yield ThinkingEndEvent()
    yield StepFinishedEvent(step_name="understand")

    text_open = False
    answer_open = False
    active_tool = None
    tool_step = None
    tool_args = ""
    pending: list = []
    # _tool_results is module-level (the tool fn can't see the request); baseline the
    # index so THIS run only drains the results it appended — not a prior run's leftover.
    emitted = len(_tool_results)

    async for ev in agent.stream_async(f"{run_input.messages[-1].content} Give the temperature in {unit}."):
        e = ev.get("event", {}) if isinstance(ev, dict) else {}

        tu = e.get("contentBlockStart", {}).get("start", {}).get("toolUse")
        if tu:
            active_tool, tool_args, tool_step = tu["toolUseId"], "", "tool:" + tu["name"]
            yield StepStartedEvent(step_name=tool_step)
            yield ToolCallStartEvent(tool_call_id=active_tool, tool_call_name=tu["name"])
            state["status"] = "calling " + tu["name"]
            yield _patch("/status", state["status"])

        delta = e.get("contentBlockDelta", {}).get("delta", {})
        if delta.get("toolUse") and active_tool:
            chunk = delta["toolUse"].get("input", "")
            tool_args += chunk
            yield ToolCallArgsEvent(tool_call_id=active_tool, delta=chunk)

        if "contentBlockStop" in e and active_tool:
            yield ToolCallEndEvent(tool_call_id=active_tool)
            try:
                city = json.loads(tool_args).get("city")
            except Exception:
                city = None
            if city:
                state["city"] = city
                yield _patch("/city", city)
            pending.append((active_tool, tool_step))
            active_tool, tool_step = None, None

        while emitted < len(_tool_results) and pending:
            tid, step = pending.pop(0)
            result = _tool_results[emitted]
            emitted += 1
            yield ToolCallResultEvent(message_id=mid, tool_call_id=tid, content=result)
            state["weather"] = result
            state["tools_called"] += 1
            yield _patch("/weather", result)
            yield _patch("/tools_called", state["tools_called"])
            yield StepFinishedEvent(step_name=step)
            # GENERATIVE UI: the agent SELECTS a component for the frontend to render
            # (the frontend has a coded WeatherCard; the agent picks it + supplies props).
            m = re.match(r".*?:\s*(\d+)C,\s*(\w+)", result)
            if m:
                c = int(m.group(1))
                temp = f"{c}°C" if unit == "°C" else f"{round(c * 9 / 5 + 32)}°F"
                icon = {"sunny": "☀️", "cloudy": "☁️", "rainy": "🌧️"}.get(m.group(2), "🌡️")
                yield CustomEvent(name="renderComponent", value={
                    "component": "WeatherCard",
                    "props": {"city": state["city"] or "", "temp": temp,
                              "condition": m.group(2), "icon": icon}})

        text = ev.get("data") if isinstance(ev, dict) else None
        if isinstance(text, str) and text:
            if not text_open:
                yield StepStartedEvent(step_name="answer")
                answer_open = True
                yield TextMessageStartEvent(message_id=mid, role="assistant")
                text_open = True
                state["status"] = "answering"
                yield _patch("/status", "answering")
            yield TextMessageContentEvent(message_id=mid, delta=text)

    if text_open:
        yield TextMessageEndEvent(message_id=mid)
    if answer_open:
        yield StepFinishedEvent(step_name="answer")
    yield _patch("/status", "done")
    yield RunFinishedEvent(thread_id=run_input.thread_id, run_id=run_input.run_id)


CLIENT_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client.html")


def build_app():
    app = build_ag_ui_app(entrypoint)

    async def index(_request):
        return FileResponse(CLIENT_HTML)

    app.routes.append(Route("/", index, methods=["GET"]))
    return app


def event_types(sse_text: str) -> list:
    return re.findall(r'"type"\s*:\s*"([A-Z_]+)"', sse_text)


def run_body(text: str, state: dict | None = None) -> dict:
    return {"threadId": "t1", "runId": "r1",
            "messages": [{"id": "m1", "role": "user", "content": text}],
            "tools": [], "context": [], "state": state or {}, "forwardedProps": {}}


def iteration_1_surface(client: TestClient) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 1: the AG-UI protocol surface (+ the web client route)")
    print("=" * 70)
    paths = [getattr(r, "path", None) for r in client.app.routes]
    print(f"  routes: {paths}")
    assert client.get("/ping").status_code == 200 and "Healthy" in client.get("/ping").text
    assert {"/invocations", "/ws", "/"} <= set(paths)
    print("  OK: SSE /invocations + WS /ws + /ping + the generative-UI client at /.")


def iteration_hitl(client: TestClient) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 2: human-in-the-loop — the run PAUSES on a frontend tool")
    print("=" * 70)
    text = client.post("/invocations", json=run_body("weather in Tokyo?")).text  # NO state.unit
    types = event_types(text)
    name = re.findall(r'"toolCallName"\s*:\s*"([^"]+)"', text)
    print(f"  events: {types}")
    print(f"  frontend tool called: {name}")
    assert "ask_temperature_unit" in name, "the agent should call the frontend unit tool"
    assert "TEXT_MESSAGE_CONTENT" not in types, "the run pauses BEFORE answering (no text)"
    assert "TOOL_CALL_RESULT" not in types and types[-1] == "RUN_FINISHED", "paused with NO result"
    assert "awaiting human input" in text
    print("  OK: called ask_temperature_unit with NO result — the frontend renders a picker,")
    print("      the human answers, and the next run resumes with state.unit set.")


def iteration_2_full_run(client: TestClient):
    print("\n" + "=" * 70)
    print("ITERATION 3: resumed run emits the FULL event vocabulary")
    print("=" * 70)
    _tool_results.clear()
    # state.unit present -> the HITL gate is satisfied and the full flow runs.
    text = client.post("/invocations", json=run_body("What's the weather in Tokyo?", {"unit": "°C"})).text
    types = event_types(text)
    families = {
        "lifecycle": {"RUN_STARTED", "RUN_FINISHED", "STEP_STARTED", "STEP_FINISHED"},
        "thinking": {"THINKING_START", "THINKING_TEXT_MESSAGE_CONTENT", "THINKING_END"},
        "tools": {"TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END", "TOOL_CALL_RESULT"},
        "state": {"STATE_SNAPSHOT", "STATE_DELTA"},
        "generative": {"CUSTOM"},  # agent selects a frontend component to render
        "text": {"TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END"},
    }
    print(f"  distinct event types: {sorted(set(types))}")
    for fam, need in families.items():
        present = need <= set(types)
        print(f"    {fam:9s}: {'OK' if present else 'MISSING'}  {sorted(need)}")
        assert present, f"{fam} events missing"
    print("  OK: a single run drove lifecycle + thinking + tools + state + text.")
    return text


def iteration_3_state(text: str) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 4: shared state — snapshot + JSON-Patch deltas")
    print("=" * 70)
    snap = re.search(r'"snapshot"\s*:\s*(\{.*?\})', text)
    deltas = re.findall(r'"op"\s*:\s*"replace"\s*,\s*"path"\s*:\s*"([^"]+)"\s*,\s*"value"\s*:\s*("?[^,}]*)', text)
    print(f"  initial snapshot: {snap.group(1) if snap else '?'}")
    print(f"  patches applied: {deltas[:6]}")
    paths = {p for p, _ in deltas}
    assert snap and {"/status", "/city", "/weather"} <= paths, "state should be snapshotted then patched"
    assert any('Tokyo' in v for _, v in deltas), "the live state should reflect the asked-about city"
    print("  OK: the frontend applies these patches to render live, structured state.")


def iteration_4_validation(client: TestClient) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 5: malformed RunAgentInput -> HTTP 400")
    print("=" * 70)
    bad = run_body("hi")
    del bad["forwardedProps"]
    resp = client.post("/invocations", json=bad)
    print(f"  missing forwardedProps -> {resp.status_code}: {resp.json().get('error')}")
    assert resp.status_code == 400
    print("  OK: validation up front (400); mid-stream errors -> RunErrorEvent.")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L76 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. AG-UI is a generative-UI protocol, not just streamed text
   One run emits lifecycle + steps + thinking + tool calls + SHARED STATE + text.
   The headline is STATE_SNAPSHOT + STATE_DELTA (JSON-Patch): the agent and frontend
   share a live state object, so the UI renders structured/generative content.

2. The adapter owns the mapping
   You decide what to surface: real model text/tools from stream_async, plus
   adapter-owned state/steps. A raw Agent won't do — pass an async-generator entrypoint.

3. Serve a real frontend same-origin
   AGUIApp.routes is mutable -> GET / serves client.html (no CORS). serve_ag_ui runs it.

4. Validate in layers
   Headless TestClient asserts every event family; a live `serve` + curl proves the
   socket; a browser renders the generative UI (state panel + steps + chat).

   Run it:  uv run python 19_agentcore_agui/agui_native.py serve  ->  http://127.0.0.1:8080/
""")


def main() -> None:
    print("AG-UI Native (full vocabulary) — L76")
    client = TestClient(build_app())
    iteration_1_surface(client)
    iteration_hitl(client)
    text = iteration_2_full_run(client)
    iteration_3_state(text)
    iteration_4_validation(client)
    summary()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        print("Serving AG-UI generative UI at http://127.0.0.1:8080/  (Ctrl-C to stop)")
        build_app().run(port=8080, host="127.0.0.1")
    else:
        main()

"""
L44 Probe 3: create a real AG-UI FastAPI app and capture events
without a frontend.

Test:
1. Create StrandsAgent + FastAPI app
2. Fire a POST /invocations with a RunAgentInput
3. Capture the SSE stream and parse events
4. Show each event type + content
"""
import asyncio
import json
import httpx
from fastapi.testclient import TestClient
from ag_ui_strands import StrandsAgent, create_strands_app, ToolBehavior, StrandsAgentConfig
from ag_ui.core import UserMessage
from strands import Agent, tool
from tools import get_model
import sys
sys.path.insert(0, '.')

# ── Build a Strands agent with a tool ────────────────────────────────────────
fast = get_model("haiku")

@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    forecasts = {
        "london": "12°C, overcast",
        "paris":  "18°C, sunny",
        "tokyo":  "22°C, partly cloudy",
    }
    return forecasts.get(city.lower(), f"No data for {city}")

strands_agent = Agent(
    model=fast,
    tools=[get_weather],
    system_prompt="You are a helpful weather assistant.",
    callback_handler=None,
)

# ── Wrap in AG-UI adapter ────────────────────────────────────────────────────
agui_agent = StrandsAgent(
    agent=strands_agent,
    name="weather_agent",
    description="Answers weather questions",
)

app = create_strands_app(agui_agent, path="/invocations", ping_path="/ping")

# ── Fire a test request ───────────────────────────────────────────────────────
print("=== Ping test ===")
with TestClient(app) as client:
    r = client.get("/ping")
    print(f"  GET /ping → {r.status_code} {r.json()}")

print("\n=== POST /invocations — SSE stream ===")
payload = {
    "thread_id": "test-thread-1",
    "run_id":    "test-run-1",
    "messages":  [{"role": "user", "id": "msg-1", "content": "What's the weather in Paris?"}],
    "tools":     [],
    "state":     {},
    "context":   [],
    "forwarded_props": {},
}

event_types = []
with TestClient(app) as client:
    with client.stream(
        "POST", "/invocations",
        json=payload,
        headers={"Accept": "text/event-stream"},
        timeout=30,
    ) as response:
        print(f"  Status: {response.status_code}")
        for line in response.iter_lines():
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_str = line[5:].strip()
                try:
                    event = json.loads(data_str)
                    etype = event.get("type", "unknown")
                    event_types.append(etype)
                    # Print key events
                    if etype in ("TextMessageContentEvent",):
                        print(f"  [{etype}] delta={event.get('delta','')!r}")
                    elif etype in ("ToolCallStartEvent",):
                        print(f"  [{etype}] tool_name={event.get('tool_name')}")
                    elif etype in ("ToolCallArgsEvent",):
                        print(f"  [{etype}] delta={event.get('delta','')!r}")
                    elif etype not in ("TextMessageContentEvent",):
                        print(f"  [{etype}]")
                except json.JSONDecodeError:
                    print(f"  raw: {data_str[:80]}")

print(f"\n=== Event sequence ===")
print("  " + " → ".join(event_types))

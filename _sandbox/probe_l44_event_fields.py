"""
L44 Probe: dump raw event dicts for TOOL_CALL_START and TOOL_CALL_RESULT.
"""
import json, sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
from ag_ui_strands import StrandsAgent, create_strands_app
from strands import Agent, tool
from tools import get_model

fast = get_model("haiku")

@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return {"london": "12°C, overcast", "paris": "18°C, sunny"}.get(city.lower(), f"No data for {city}")

strands_agent = Agent(model=fast, tools=[get_weather], callback_handler=None)
agui_agent = StrandsAgent(agent=strands_agent, name="weather_agent")
app = create_strands_app(agui_agent, path="/invocations", ping_path="/ping")

payload = {
    "thread_id": "t1", "run_id": "r1",
    "messages": [{"role": "user", "id": "m1", "content": "What's the weather in Paris?"}],
    "tools": [], "state": {}, "context": [], "forwarded_props": {},
}

with TestClient(app) as client:
    with client.stream("POST", "/invocations", json=payload, headers={"Accept": "text/event-stream"}, timeout=30) as resp:
        for line in resp.iter_lines():
            if line.startswith("data:"):
                ev = json.loads(line[5:].strip())
                etype = ev.get("type", "?")
                if etype in ("TOOL_CALL_START", "TOOL_CALL_RESULT", "STATE_SNAPSHOT"):
                    print(f"\n=== {etype} ===")
                    print(json.dumps(ev, indent=2, default=str))

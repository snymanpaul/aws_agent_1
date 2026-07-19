"""
L44 Probe 4: correct UserMessage format for ag-ui.
"""
import inspect, json
from ag_ui.core import UserMessage, AssistantMessage, Message

# What fields does UserMessage have?
print("=== UserMessage fields ===")
try:
    print(list(UserMessage.model_fields.keys()))
    print(inspect.signature(UserMessage))
except Exception as e:
    print(f"  {e}")
    # Try instantiating
    try:
        m = UserMessage(id="m1", role="user", content="hello")
        print(f"  ok: {m.model_dump()}")
    except Exception as e2:
        print(f"  {e2}")

# Try content as list
print("\n=== UserMessage with content list ===")
try:
    m = UserMessage(id="m1", role="user", content=[{"type": "text", "text": "hello"}])
    print(f"  ok: {m.model_dump()}")
except Exception as e:
    print(f"  {e}")

# What does the serialized payload look like?
print("\n=== Serialized message ===")
try:
    m = UserMessage(id="m1", role="user", content="find papers on reflexion")
    print(json.dumps(m.model_dump(), indent=2))
except Exception as e:
    try:
        m = UserMessage(**{"id": "m1", "role": "user", "content": "find papers"})
        print(json.dumps(m.model_dump(), indent=2))
    except Exception as e2:
        print(f"  {e2}")

# Try from the probe3 payload format (raw dict sent to TestClient)
print("\n=== How messages are parsed server-side ===")
from ag_ui.core import RunAgentInput
try:
    inp = RunAgentInput.model_validate({
        "thread_id": "t1",
        "run_id": "r1",
        "messages": [{"role": "user", "id": "m1", "content": "find papers on reflexion"}],
        "tools": [],
        "state": {},
        "context": [],
        "forwarded_props": {},
    })
    print(f"  parsed ok, messages: {inp.messages}")
    print(f"  first message content: {inp.messages[0].content!r}")
except Exception as e:
    print(f"  {e}")

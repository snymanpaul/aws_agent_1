"""
L44 Probe: ag-ui-strands + ag-ui-protocol — what do they expose?

Questions:
1. What does ag_ui_strands export?
2. What does ag_ui_protocol export (event types)?
3. What's the adapter/server API?
4. Can we run a standalone SSE server without a frontend?
"""
import ag_ui_strands
import ag_ui_protocol
import inspect

# ── Q1: ag_ui_strands exports ─────────────────────────────────────────────────
print("=== Q1: ag_ui_strands exports ===")
names = [n for n in dir(ag_ui_strands) if not n.startswith("_")]
print(names)
print()
for name in names[:8]:
    obj = getattr(ag_ui_strands, name)
    print(f"  {name}: {type(obj).__name__}")
    if inspect.isclass(obj):
        print(f"    init: {inspect.signature(obj.__init__)}")

# ── Q2: ag_ui_protocol event types ───────────────────────────────────────────
print("\n=== Q2: ag_ui_protocol event types ===")
proto_names = [n for n in dir(ag_ui_protocol) if not n.startswith("_")]
print(proto_names[:30])

# Find event classes
event_classes = [n for n in proto_names if "Event" in n or "event" in n]
print(f"\n  Event types: {event_classes}")

# ── Q3: adapter API ───────────────────────────────────────────────────────────
print("\n=== Q3: AGUIStrandsAdapter or similar ===")
for name in dir(ag_ui_strands):
    obj = getattr(ag_ui_strands, name)
    if inspect.isclass(obj):
        print(f"\n  class {name}:")
        try:
            src = inspect.getsource(obj)
            print(src[:600])
        except:
            print(f"    (no source)")

# ── Q4: ag_ui_protocol RunAgentInput structure ────────────────────────────────
print("\n=== Q4: RunAgentInput ===")
try:
    rai = ag_ui_protocol.RunAgentInput
    print(f"  fields: {rai.model_fields.keys() if hasattr(rai, 'model_fields') else 'N/A'}")
    print(f"  signature: {inspect.signature(rai)}")
except Exception as e:
    print(f"  {e}")

"""
Probe L37: Full Kinesis streaming config shape in bedrock-agentcore-control.
- Find which operations/shapes reference KinesisResource / StreamDeliveryResource
- Print full KinesisResourceContentConfigurations structure
- Probe CreateMemory and UpdateMemory for stream delivery config
- Live: try create a memory store with Kinesis config (dry-run shape check only)
"""
import os
import sys, gzip, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
import botocore

session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
ctrl = session.client("bedrock-agentcore-control", region_name="us-east-1")

# --- 1. Find which shapes reference KinesisResource ---
print("=== Shapes referencing KinesisResource or StreamDelivery ===")
import gzip as gz
svc_path = os.path.join(os.path.dirname(botocore.__file__), "data",
                        "bedrock-agentcore-control", "2023-06-05", "service-2.json.gz")
with gz.open(svc_path) as f:
    model = json.load(f)

shapes = model["shapes"]
for name, val in shapes.items():
    s = json.dumps(val)
    if "KinesisResource" in s or "StreamDelivery" in s:
        print(f"  {name}")
        print(json.dumps(val, indent=2)[:800])
        print()

# --- 2. Operations referencing StreamDelivery ---
print("=== Operations referencing StreamDelivery ===")
ops = model["operations"]
for op_name, op_val in ops.items():
    s = json.dumps(op_val)
    if "StreamDelivery" in s or "Kinesis" in s:
        print(f"  {op_name}: {json.dumps(op_val)[:200]}")

# --- 3. CreateMemory full shape with stream delivery ---
print("\n=== CreateMemory input shape (full - looking for streamDelivery) ===")
def print_shape_deep(s, indent=0, depth=0, visited=None):
    if visited is None:
        visited = set()
    if depth > 6:
        return
    pad = "  " * indent
    if hasattr(s, "members"):
        req = getattr(s, "required_members", [])
        for name, member in s.members.items():
            r = " *" if name in req else ""
            print(f"{pad}{name}: {member.type_name}{r}")
            k = getattr(member, "name", str(id(member)))
            if k not in visited:
                visited.add(k)
                if member.type_name in ("structure", "union"):
                    print_shape_deep(member, indent + 1, depth + 1, visited)
                elif member.type_name == "list":
                    inner = member.member
                    print(f"{pad}  [item]: {inner.type_name}")
                    if hasattr(inner, "members"):
                        print_shape_deep(inner, indent + 2, depth + 1, visited)
                elif member.type_name == "map":
                    print(f"{pad}  {{key}}: {member.key.type_name} -> {member.value.type_name}")

try:
    shape = ctrl._service_model.operation_model("CreateMemory").input_shape
    print_shape_deep(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 4. UpdateMemory shape ---
print("\n=== UpdateMemory input shape (full) ===")
try:
    shape = ctrl._service_model.operation_model("UpdateMemory").input_shape
    print_shape_deep(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 5. What does KinesisResourceContentConfigurationsList look like ---
print("\n=== KinesisResourceContentConfigurations raw shape ===")
for name in ["KinesisResourceContentConfigurationsList",
             "KinesisResourceContentConfiguration",
             "ContentConfiguration",
             "KinesisContentConfiguration"]:
    if name in shapes:
        print(f"  {name}:")
        print(json.dumps(shapes[name], indent=2)[:1000])

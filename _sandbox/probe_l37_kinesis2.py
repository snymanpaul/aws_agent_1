"""
Probe L37: Find Kinesis streaming config in bedrock-agentcore-control service model.
- Check botocore version
- Search all shapes for 'kinesis', 'streamArn', 'deliveryStream'
- List all CreateMemory shape members (full depth)
- Check if there are any 'Configuration' or 'EventStream' shapes
- Also check boto3 for newer APIs (pip install --upgrade boto3?)
"""
import os
import sys, json, gzip
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
import botocore

print(f"botocore version: {botocore.__version__}")
print(f"botocore path: {botocore.__file__}")

session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
ctrl = session.client("bedrock-agentcore-control", region_name="us-east-1")
runtime = session.client("bedrock-agentcore", region_name="us-east-1")

# --- 1. Search service model for kinesis / stream ---
print("\n=== Searching service model for kinesis/stream/delivery ===")
svc_model_path = None
for path in botocore.__path__:
    candidate = os.path.join(path, "data", "bedrock-agentcore-control", "2023-06-05", "service-2.json.gz")
    if os.path.exists(candidate):
        svc_model_path = candidate
        break

if svc_model_path:
    with gzip.open(svc_model_path) as f:
        model = json.load(f)
    shapes = model.get("shapes", {})
    ops = model.get("operations", {})
    found = False
    keywords = ["kinesis", "streamarn", "deliverystream", "streamconfig", "kinesisconfig", "eventstream"]
    for key, val in shapes.items():
        s = json.dumps(val).lower()
        for kw in keywords:
            if kw in s:
                print(f"  Shape: {key}")
                print(f"  {json.dumps(val, indent=2)[:600]}")
                found = True
                break
    if not found:
        print("  None found in shapes")
    for op_name in ops:
        s = json.dumps(ops[op_name]).lower()
        for kw in keywords:
            if kw in s:
                print(f"  Op: {op_name}")
else:
    print("  Service model gz not found")

# --- 2. Full CreateMemory shape (deep) ---
print("\n=== CreateMemory full input shape (deep) ===")
def print_shape_deep(s, indent=0, depth=0, visited=None):
    if visited is None:
        visited = set()
    if depth > 5:
        return
    pad = "  " * indent
    if hasattr(s, "members"):
        req = getattr(s, "required_members", [])
        for name, member in s.members.items():
            r = " *" if name in req else ""
            print(f"{pad}{name}: {member.type_name}{r}")
            member_name = getattr(member, "name", id(member))
            if member_name not in visited:
                visited.add(member_name)
                if member.type_name == "structure":
                    print_shape_deep(member, indent + 1, depth + 1, visited)
                elif member.type_name == "list":
                    inner = member.member
                    print(f"{pad}  [item]: {inner.type_name}")
                    if hasattr(inner, "members"):
                        print_shape_deep(inner, indent + 2, depth + 1, visited)

try:
    shape = ctrl._service_model.operation_model("CreateMemory").input_shape
    print_shape_deep(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 3. All shape names containing 'stream' or 'kinesis' ---
print("\n=== Shape names with 'stream' or 'kinesis' ===")
for name in sorted(ctrl._service_model.shape_names):
    if any(kw in name.lower() for kw in ["stream", "kinesis", "event"]):
        print(f"  {name}")

# --- 4. Check if there's a separate 'ConfigureMemoryStreaming' or similar op ---
print("\n=== All control-plane operations ===")
for op in sorted(ctrl._service_model.operation_names):
    print(f"  {op}")

"""
Probe L37: Fix issues found in first run.
1. RetrieveMemoryRecords correct input shape
2. CreateEvent output shape (response keys)
3. BatchCreateMemoryRecords response shape
4. ListMemoryRecords shape
"""
import os
import sys, gzip, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3, botocore

session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
runtime = session.client("bedrock-agentcore", region_name="us-east-1")

def print_shape_deep(s, indent=0, depth=0, visited=None):
    if visited is None:
        visited = set()
    if depth > 4:
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
                if member.type_name == "structure":
                    print_shape_deep(member, indent + 1, depth + 1, visited)
                elif member.type_name == "list":
                    inner = member.member
                    print(f"{pad}  [item]: {inner.type_name}")
                    if hasattr(inner, "members"):
                        print_shape_deep(inner, indent + 2, depth + 1, visited)

# --- 1. RetrieveMemoryRecords ---
print("=== RetrieveMemoryRecords input ===")
try:
    shape = runtime._service_model.operation_model("RetrieveMemoryRecords").input_shape
    print_shape_deep(shape)
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== RetrieveMemoryRecords output ===")
try:
    shape = runtime._service_model.operation_model("RetrieveMemoryRecords").output_shape
    print_shape_deep(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 2. CreateEvent output ---
print("\n=== CreateEvent output ===")
try:
    shape = runtime._service_model.operation_model("CreateEvent").output_shape
    print_shape_deep(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 3. BatchCreateMemoryRecords output ---
print("\n=== BatchCreateMemoryRecords output ===")
try:
    shape = runtime._service_model.operation_model("BatchCreateMemoryRecords").output_shape
    print_shape_deep(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 4. ListMemoryRecords ---
print("\n=== ListMemoryRecords input ===")
try:
    shape = runtime._service_model.operation_model("ListMemoryRecords").input_shape
    print_shape_deep(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 5. SearchCriteria shape ---
svc_path = os.path.join(os.path.dirname(botocore.__file__), "data",
                        "bedrock-agentcore", "2023-06-05", "service-2.json.gz")
with gzip.open(svc_path) as f:
    model = json.load(f)
print("\n=== SearchCriteria shape ===")
sc = model["shapes"].get("SearchCriteria", {})
print(json.dumps(sc, indent=2)[:600])

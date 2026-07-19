"""
Probe L37: Find Kinesis streaming config in LTM API.
Also check CreateEvent and BatchCreateMemoryRecords shapes.
"""
import os
import sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3

session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
ctrl = session.client("bedrock-agentcore-control", region_name="us-east-1")
runtime = session.client("bedrock-agentcore", region_name="us-east-1")

# --- 1. GetMemory shape (control plane) — does it show Kinesis config? ---
print("=== GetMemory output shape (control plane) ===")
try:
    shape = ctrl._service_model.operation_model("GetMemory").output_shape

    def print_shape(s, indent=0, depth=0):
        if depth > 4:
            return
        pad = "  " * indent
        if hasattr(s, 'members'):
            for name, member in s.members.items():
                print(f"{pad}{name}: {member.type_name}")
                if member.type_name in ('structure',) and depth < 3:
                    print_shape(member, indent+1, depth+1)
                elif member.type_name == 'list' and depth < 2 and hasattr(member.member, 'members'):
                    print(f"{pad}  [item]: structure")
                    print_shape(member.member, indent+2, depth+1)

    print_shape(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 2. Live GetMemory for existing store ---
MEMORY_ID = "l27agentcore_Memory-9RYaOkDitt"
print(f"\n=== GetMemory live: {MEMORY_ID} ===")
try:
    resp = ctrl.get_memory(memoryId=MEMORY_ID)
    # Print the full response (filter out response metadata)
    resp.pop("ResponseMetadata", None)
    print(json.dumps(resp, default=str, indent=2)[:2000])
except Exception as e:
    print(f"  ERROR: {e}")

# --- 3. UpdateMemory shape — Kinesis config? ---
print("\n=== UpdateMemory input shape (control plane) ===")
try:
    shape = ctrl._service_model.operation_model("UpdateMemory").input_shape
    print_shape = lambda s, i=0, d=0: [
        (print(f"{'  '*i}{n}: {m.type_name}"), print_shape(m, i+1, d+1) if m.type_name == 'structure' and d < 3 else None)
        for n, m in s.members.items()
    ] if hasattr(s, 'members') else None
    def print_s(s, indent=0, depth=0):
        if depth > 4: return
        if hasattr(s, 'members'):
            for name, member in s.members.items():
                print(f"{'  '*indent}{name}: {member.type_name}")
                if member.type_name == 'structure' and depth < 3:
                    print_s(member, indent+1, depth+1)
    print_s(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 4. CreateEvent shape on runtime ---
print("\n=== CreateEvent shape (runtime) ===")
try:
    shape = runtime._service_model.operation_model("CreateEvent").input_shape

    def print_full(s, indent=0, depth=0):
        if depth > 5: return
        pad = "  " * indent
        if hasattr(s, 'members'):
            req = getattr(s, 'required_members', [])
            for name, member in s.members.items():
                r = " *" if name in req else ""
                print(f"{pad}{name}: {member.type_name}{r}")
                if member.type_name == 'structure' and depth < 4:
                    print_full(member, indent+1, depth+1)
                elif member.type_name == 'list' and depth < 3:
                    print(f"{pad}  [item]: {member.member.type_name}")
                    if hasattr(member.member, 'members'):
                        print_full(member.member, indent+2, depth+1)

    print_full(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 5. BatchCreateMemoryRecords shape ---
print("\n=== BatchCreateMemoryRecords shape ===")
try:
    shape = runtime._service_model.operation_model("BatchCreateMemoryRecords").input_shape
    print_full(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 6. All operations on both clients that contain 'kinesis' or 'stream' ---
print("\n=== 'stream' or 'kinesis' operations ===")
for label, client in [("control", ctrl), ("runtime", runtime)]:
    for op in sorted(client._service_model.operation_names):
        if any(kw in op.lower() for kw in ['kinesis', 'stream', 'event']):
            print(f"  [{label}] {op}")

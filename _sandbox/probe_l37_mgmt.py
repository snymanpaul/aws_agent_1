"""
Probe L37: find the memory store management API.
CreateMemory failed on bedrock-agentcore — try bedrock-agentcore-control.
Also probe IngestConversationEvents payload shape and Kinesis config in CreateMemory.
"""
import os
import sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3

session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))

# --- 1. Try bedrock-agentcore-control ---
print("=== bedrock-agentcore-control operations (memory) ===")
try:
    ctrl = session.client("bedrock-agentcore-control", region_name="us-east-1")
    sm = ctrl._service_model
    all_ops = sorted(sm.operation_names)
    for op in all_ops:
        if any(kw in op.lower() for kw in ['memory', 'ltm', 'episod', 'recall', 'remember']):
            print(f"  {op}")
    print(f"\n  (total ops: {len(all_ops)})")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 2. CreateMemory shape on control plane ---
print("\n=== CreateMemory shape (control plane) ===")
try:
    ctrl = session.client("bedrock-agentcore-control", region_name="us-east-1")
    shape = ctrl._service_model.operation_model("CreateMemory").input_shape

    def print_shape(s, indent=0, depth=0):
        if depth > 3:
            return
        pad = "  " * indent
        if hasattr(s, 'members'):
            req = getattr(s, 'required_members', [])
            for name, member in s.members.items():
                r = " (required)" if name in req else ""
                print(f"{pad}{name}: {member.type_name}{r}")
                if member.type_name in ('structure', 'list') and depth < 2:
                    inner = member.member if member.type_name == 'list' else member
                    if hasattr(inner, 'members'):
                        print_shape(inner, indent+1, depth+1)

    print_shape(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 3. ListMemories on control plane ---
print("\n=== ListMemories (control plane) ===")
try:
    ctrl = session.client("bedrock-agentcore-control", region_name="us-east-1")
    resp = ctrl.list_memories()
    print(f"  response keys: {list(resp.keys())}")
    memories = resp.get('memories', resp.get('memoryStores', resp.get('memorySummaries', [])))
    print(f"  count: {len(memories)}")
    for m in memories[:3]:
        print(f"  {json.dumps(m, default=str)[:300]}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 4. IngestConversationEvents payload shape ---
print("\n=== IngestConversationEvents full shape ===")
try:
    client = session.client("bedrock-agentcore", region_name="us-east-1")
    sm = client._service_model
    shape = sm.operation_model("IngestConversationEvents").input_shape

    def print_deep(s, indent=0, depth=0):
        if depth > 4:
            return
        pad = "  " * indent
        if hasattr(s, 'members'):
            req = getattr(s, 'required_members', [])
            for name, member in s.members.items():
                r = " *" if name in req else ""
                print(f"{pad}{name}: {member.type_name}{r}")
                if member.type_name == 'structure' and depth < 3:
                    print_deep(member, indent+1, depth+1)
                elif member.type_name == 'list' and depth < 3:
                    print(f"{pad}  [item]: {member.member.type_name}")
                    if hasattr(member.member, 'members'):
                        print_deep(member.member, indent+2, depth+1)

    print_deep(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 5. RetrieveMemoryRecords shape ---
print("\n=== RetrieveMemoryRecords shape ===")
try:
    client = session.client("bedrock-agentcore", region_name="us-east-1")
    sm = client._service_model
    shape = sm.operation_model("RetrieveMemoryRecords").input_shape
    for name, member in shape.members.items():
        req = " *" if name in getattr(shape, 'required_members', []) else ""
        print(f"  {name}: {member.type_name}{req}")
except Exception as e:
    print(f"  ERROR: {e}")

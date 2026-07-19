"""
Probe L37: AgentCore LTM + Kinesis streaming shapes.
Questions:
  1. What LTM operations exist on bedrock-agentcore client?
  2. What is the shape of create_memory_store (Kinesis config param name)?
  3. What is the Kinesis event payload shape (FULL_CONTENT vs METADATA_ONLY)?
  4. Are there separate memory namespace operations vs memory records?
  5. What does list/get/create memory look like?
"""
import os
import sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3

session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
client = session.client("bedrock-agentcore", region_name="us-east-1")
sm = client._service_model

# --- 1. All LTM-related operations ---
print("=== All operations (grep for memory/ltm) ===")
all_ops = sorted(sm.operation_names)
for op in all_ops:
    if any(kw in op.lower() for kw in ['memory', 'ltm', 'episod', 'recall', 'remember']):
        print(f"  {op}")

# --- 2. CreateMemory input shape ---
print("\n=== CreateMemory input shape ===")
try:
    shape = sm.operation_model("CreateMemory").input_shape
    def print_shape(s, indent=0):
        pad = "  " * indent
        if hasattr(s, 'members'):
            for name, member in s.members.items():
                req = "(required)" if name in getattr(s, 'required_members', []) else ""
                print(f"{pad}{name}: {member.type_name} {req}")
                if member.type_name == 'structure':
                    print_shape(member, indent+1)
                elif member.type_name == 'list' and hasattr(member.member, 'members'):
                    print(f"{pad}  [item]:")
                    print_shape(member.member, indent+2)
        else:
            print(f"{pad}type={s.type_name}")
    print_shape(shape)
except Exception as e:
    print(f"  ERROR: {e}")

# --- 3. ListMemories input/output ---
print("\n=== ListMemories shapes ===")
try:
    shape_in = sm.operation_model("ListMemories").input_shape
    shape_out = sm.operation_model("ListMemories").output_shape
    print("  input:")
    for name, member in shape_in.members.items():
        print(f"    {name}: {member.type_name}")
    print("  output (top level):")
    for name, member in shape_out.members.items():
        print(f"    {name}: {member.type_name}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 4. GetMemory ---
print("\n=== GetMemory shapes ===")
try:
    shape = sm.operation_model("GetMemory").input_shape
    for name, member in shape.members.items():
        print(f"  {name}: {member.type_name}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 5. CreateMemoryRecord / IngestConversationEvents (LTM write) ---
print("\n=== Memory record write operations ===")
for op_name in ['CreateMemoryRecord', 'IngestConversationEvents', 'CreateEvent',
                'PutMemoryRecord', 'AddMemory', 'StoreMemory']:
    try:
        shape = sm.operation_model(op_name).input_shape
        print(f"  {op_name}:")
        for name, member in shape.members.items():
            print(f"    {name}: {member.type_name}")
    except Exception as e:
        print(f"  {op_name}: {e}")

# --- 6. Live state: existing memory stores ---
print("\n=== Existing memory stores ===")
try:
    resp = client.list_memories()
    memories = resp.get('memories', resp.get('memoryStores', []))
    print(f"  count: {len(memories)}")
    for m in memories[:3]:
        print(f"  {json.dumps(m, default=str)[:200]}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 7. Check Kinesis client shapes for context ---
print("\n=== Kinesis stream (for reference) ===")
k = session.client("kinesis", region_name="us-east-1")
try:
    streams = k.list_streams()
    print(f"  streams: {streams.get('StreamNames', [])}")
except Exception as e:
    print(f"  ERROR: {e}")

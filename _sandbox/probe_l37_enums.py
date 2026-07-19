"""
Probe L37: ContentType and ContentLevel enum values + Kinesis stream availability.
"""
import os
import sys, gzip, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3, botocore

session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
ctrl = session.client("bedrock-agentcore-control", region_name="us-east-1")
runtime = session.client("bedrock-agentcore", region_name="us-east-1")
kinesis = session.client("kinesis", region_name="us-east-1")

# --- 1. ContentType and ContentLevel enums ---
svc_path = os.path.join(os.path.dirname(botocore.__file__), "data",
                        "bedrock-agentcore-control", "2023-06-05", "service-2.json.gz")
with gzip.open(svc_path) as f:
    model = json.load(f)

print("=== ContentType enum ===")
ct = model["shapes"].get("ContentType", {})
print(json.dumps(ct, indent=2))

print("\n=== ContentLevel enum ===")
cl = model["shapes"].get("ContentLevel", {})
print(json.dumps(cl, indent=2))

# --- 2. Existing memory stores ---
print("\n=== Existing memory stores ===")
try:
    resp = ctrl.list_memories()
    memories = resp.get("memories", [])
    for m in memories:
        print(f"  {m.get('id')}: {m.get('name')} ({m.get('status')})")
        # Does it have streamDeliveryResources?
        print(f"    keys: {list(m.keys())}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 3. Check if the existing memory has stream config ---
print("\n=== GetMemory l27agentcore ===")
try:
    resp = ctrl.get_memory(memoryId="l27agentcore_Memory-9RYaOkDitt")
    mem = resp.get("memory", {})
    print(json.dumps(mem, default=str, indent=2))
except Exception as e:
    print(f"  ERROR: {e}")

# --- 4. Existing Kinesis streams ---
print("\n=== Existing Kinesis streams ===")
try:
    resp = kinesis.list_streams()
    print(f"  streams: {resp.get('StreamNames', [])}")
    summaries = resp.get("StreamSummaries", [])
    for s in summaries:
        print(f"    {s}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 5. CreateEvent full shape (with enum values for role, etc) ---
print("\n=== CreateEvent - payload content types ===")
runtime_path = os.path.join(os.path.dirname(botocore.__file__), "data",
                            "bedrock-agentcore", "2023-06-05", "service-2.json.gz")
with gzip.open(runtime_path) as f:
    runtime_model = json.load(f)

for enum_name in ["ConversationRole", "PayloadType", "EventStatus"]:
    shape = runtime_model["shapes"].get(enum_name, {})
    if shape:
        print(f"\n  {enum_name}: {json.dumps(shape)}")

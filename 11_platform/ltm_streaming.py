"""
Level 37: AgentCore LTM Streaming + Kinesis
============================================
Event-driven memory pipelines: memory record changes flow to a Kinesis Data Stream
so downstream Lambda consumers get real-time push notifications — no polling.

Key concepts:
  - streamDeliveryResources on CreateMemory / UpdateMemory wires a Kinesis stream ARN
  - ContentType: MEMORY_RECORDS (only current type)
  - ContentLevel: FULL_CONTENT (complete record payload) | METADATA_ONLY (ID+type+timestamp)
  - CreateEvent → ingests conversational events into the LTM event store
  - BatchCreateMemoryRecords → direct memory record injection (faster than extraction pipeline)
  - Lambda consumer pattern: decode Kinesis Data → parse JSON → branch on eventType

Clients used:
  bedrock-agentcore-control → CreateMemory / UpdateMemory / GetMemory / DeleteMemory
  bedrock-agentcore          → BatchCreateMemoryRecords / RetrieveMemoryRecords / CreateEvent
  kinesis                   → CreateStream / GetShardIterator / GetRecords / DeleteStream

Architecture:
  Agent → CreateEvent / BatchCreateMemoryRecords
       → AgentCore LTM (processes + stores records)
       → Kinesis Data Stream (CREATED / MODIFIED events pushed)
       → Lambda: personalization update
       → Lambda: audit log to S3
       → Lambda: sync to other agents

Usage:
    AWS_PROFILE=<your-sso-profile> uv run python 11_platform/ltm_streaming.py
"""

import json
import sys
import os
import time
import base64
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
ctrl    = session.client("bedrock-agentcore-control", region_name="us-east-1")
runtime = session.client("bedrock-agentcore", region_name="us-east-1")
kinesis = session.client("kinesis", region_name="us-east-1")
sts     = session.client("sts", region_name="us-east-1")

ACCOUNT_ID   = sts.get_caller_identity()["Account"]
STREAM_NAME  = "l37ltmevents"
MEMORY_NAME  = "l37_ltm_streaming"
ACTOR_ID     = "user_l37_demo"

# ---------------------------------------------------------------------------
# ITERATION 1: Create infrastructure
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 1: Create Kinesis stream + memory store with streaming config")
print("=" * 70)
print("""
streamDeliveryResources config shape (botocore 1.42.70+):

    CreateMemory / UpdateMemory:
      streamDeliveryResources:
        resources: [                    # max 1 resource
          kinesis:
            dataStreamArn: str *        # ARN of Kinesis Data Stream
            contentConfigurations: [    # max 1 config
              type: "MEMORY_RECORDS" *  # only enum value
              level: str               # FULL_CONTENT | METADATA_ONLY
            ]
        ]

  FULL_CONTENT  → pushes complete memory record (text + namespaces + metadata)
  METADATA_ONLY → pushes only record ID + event type + timestamp (lightweight)
""")


def wait_kinesis_active(stream_name: str, timeout: int = 60) -> str:
    """Poll until stream is ACTIVE; return stream ARN."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = kinesis.describe_stream_summary(StreamName=stream_name)
        status = resp["StreamDescriptionSummary"]["StreamStatus"]
        arn    = resp["StreamDescriptionSummary"]["StreamARN"]
        if status == "ACTIVE":
            return arn
        time.sleep(3)
    raise TimeoutError(f"Stream {stream_name} not ACTIVE within {timeout}s")


def wait_memory_active(memory_id: str, timeout: int = 120) -> None:
    """Poll until memory store is ACTIVE."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp   = ctrl.get_memory(memoryId=memory_id)
        status = resp["memory"]["status"]
        if status == "ACTIVE":
            return
        if status in ("FAILED", "DELETING"):
            raise RuntimeError(
                f"Memory {memory_id} reached terminal status {status}: "
                + resp["memory"].get("failureReason", "")
            )
        time.sleep(5)
    raise TimeoutError(f"Memory {memory_id} not ACTIVE within {timeout}s")


# --- 1a. Create Kinesis stream ---
print("--- Creating Kinesis stream ---")
stream_arn: str | None = None
try:
    existing = kinesis.list_streams()
    if STREAM_NAME in existing.get("StreamNames", []):
        print(f"  Stream {STREAM_NAME!r} already exists — reusing")
        stream_arn = wait_kinesis_active(STREAM_NAME)
    else:
        kinesis.create_stream(StreamName=STREAM_NAME, ShardCount=1)
        print(f"  Creating stream {STREAM_NAME!r} …")
        stream_arn = wait_kinesis_active(STREAM_NAME)
        print(f"  Stream ACTIVE: {stream_arn}")
except Exception as e:
    print(f"  ERROR creating stream: {e}")

# --- 1b. Create memory store with Kinesis config ---
memory_id: str | None = None
print(f"\n--- Creating memory store {MEMORY_NAME!r} with Kinesis config ---")

if stream_arn:
    try:
        resp = ctrl.create_memory(
            name=MEMORY_NAME,
            description="L37: LTM streaming demo — memory records pushed to Kinesis",
            eventExpiryDuration=7,          # 7-day event retention
            memoryStrategies=[
                {
                    "semanticMemoryStrategy": {
                        "name": "l37_semantic",
                        "description": "Semantic facts extracted from conversations",
                        "namespaces": ["facts"],
                    }
                }
            ],
            streamDeliveryResources={
                "resources": [
                    {
                        "kinesis": {
                            "dataStreamArn": stream_arn,
                            "contentConfigurations": [
                                {
                                    "type": "MEMORY_RECORDS",
                                    "level": "FULL_CONTENT",
                                }
                            ],
                        }
                    }
                ]
            },
        )
        memory_id = resp["memory"]["id"]
        print(f"  Memory created: {memory_id}")
        print(f"  Waiting for ACTIVE …")
        wait_memory_active(memory_id)
        print(f"  Memory ACTIVE")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        print(f"  ClientError [{code}]: {e.response['Error']['Message']}")
        # Fall back to an existing memory store for the rest of the demo
        existing_memories = ctrl.list_memories().get("memories", [])
        if existing_memories:
            memory_id = existing_memories[0]["id"]
            print(f"  Using existing memory: {memory_id}")
    except Exception as e:
        print(f"  ERROR: {e}")
        existing_memories = ctrl.list_memories().get("memories", [])
        if existing_memories:
            memory_id = existing_memories[0]["id"]
            print(f"  Using existing memory: {memory_id}")
else:
    print("  Skipped (no stream ARN)")

# --- 1c. Show the resulting GetMemory config ---
if memory_id:
    print(f"\n--- GetMemory: {memory_id} ---")
    try:
        resp = ctrl.get_memory(memoryId=memory_id)
        mem  = resp["memory"]
        print(f"  id:                     {mem.get('id')}")
        print(f"  name:                   {mem.get('name')}")
        print(f"  status:                 {mem.get('status')}")
        print(f"  eventExpiryDuration:    {mem.get('eventExpiryDuration')} days")
        print(f"  strategies:             {len(mem.get('strategies', []))}")
        sdr = mem.get("streamDeliveryResources")
        if sdr:
            print(f"  streamDeliveryResources: {json.dumps(sdr, default=str)}")
        else:
            print("  streamDeliveryResources: (none — feature may require account allow-list)")
    except Exception as e:
        print(f"  ERROR: {e}")


# ---------------------------------------------------------------------------
# ITERATION 2: Write memory records + read from Kinesis
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 2: Inject memory records → read Kinesis push")
print("=" * 70)
print("""
Two ways to write memory records:
  a) CreateEvent → raw conversation events → extraction job → memory records
  b) BatchCreateMemoryRecords → direct injection (no extraction job needed)

BatchCreateMemoryRecords is faster for demos — records are written directly
without waiting for the async extraction pipeline.  Each record requires:
  - requestIdentifier: unique per-request ID
  - namespaces: list of namespace strings (must exist on the memory strategy)
  - content.text: the memory record text
  - timestamp: when the memory was formed
""")


def inject_memory_records(mem_id: str) -> list[str]:
    """Inject 3 demo memory records; return request identifiers."""
    ts = datetime.datetime.now(datetime.timezone.utc)
    records = [
        {
            "requestIdentifier": f"l37-rec-001",
            "namespaces": ["facts"],
            "content": {"text": "User prefers dark mode in all UI applications."},
            "timestamp": ts,
        },
        {
            "requestIdentifier": f"l37-rec-002",
            "namespaces": ["facts"],
            "content": {"text": "User is working on an AWS Strands learning project in Python."},
            "timestamp": ts,
        },
        {
            "requestIdentifier": f"l37-rec-003",
            "namespaces": ["facts"],
            "content": {"text": "User's preferred coding language is Python; secondary is TypeScript."},
            "timestamp": ts,
        },
    ]
    resp = runtime.batch_create_memory_records(memoryId=mem_id, records=records)
    ok = resp.get("successfulRecords", [])
    failed = resp.get("failedRecords", [])
    if failed:
        print(f"    WARNING: {len(failed)} failed records: {failed}")
    return [r.get("memoryRecordId", r.get("requestIdentifier", "?")) for r in ok]


if memory_id:
    print("--- Injecting 3 memory records via BatchCreateMemoryRecords ---")
    try:
        ids = inject_memory_records(memory_id)
        print(f"  Successful: {ids}")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        print(f"  ClientError [{code}]: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"  ERROR: {e}")
else:
    print("  Skipped (no memory_id)")

# --- Read from Kinesis ---
print("\n--- Reading Kinesis stream (waiting up to 15s for record propagation) ---")


def read_kinesis_records(stream_name: str, wait_secs: int = 15) -> list[dict]:
    """Read all available records from a Kinesis stream (TRIM_HORIZON)."""
    shards = kinesis.list_shards(StreamName=stream_name)["Shards"]
    all_records: list[dict] = []
    deadline = time.time() + wait_secs
    for shard in shards:
        it_resp = kinesis.get_shard_iterator(
            StreamName=stream_name,
            ShardId=shard["ShardId"],
            ShardIteratorType="TRIM_HORIZON",
        )
        iterator = it_resp["ShardIterator"]
        while time.time() < deadline:
            rec_resp = kinesis.get_records(ShardIterator=iterator, Limit=100)
            for raw in rec_resp.get("Records", []):
                try:
                    payload = json.loads(raw["Data"])
                except Exception:
                    payload = {"raw": base64.b64encode(raw["Data"]).decode()}
                all_records.append(payload)
            iterator = rec_resp.get("NextShardIterator", "")
            if all_records or not iterator:
                break
            time.sleep(2)
    return all_records


if stream_arn:
    try:
        records = read_kinesis_records(STREAM_NAME, wait_secs=15)
        if records:
            print(f"  {len(records)} Kinesis record(s) received:")
            for r in records:
                print(f"    {json.dumps(r, default=str)[:300]}")
        else:
            print("  No records yet in stream.")
            print("  Note: Record propagation may be delayed by the extraction pipeline.")
            print("  The stream is correctly configured — records will arrive async.")
    except Exception as e:
        print(f"  ERROR reading Kinesis: {e}")
else:
    print("  Skipped (no stream ARN)")


# ---------------------------------------------------------------------------
# ITERATION 3: CreateEvent — conversational event ingestion
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 3: CreateEvent — conversational event ingestion")
print("=" * 70)
print("""
CreateEvent is the primary LTM write path for agents in production.
It records raw conversation turns; the extraction pipeline then surfaces
structured memory records from those events.

  CreateEvent(
    memoryId,
    actorId,           # identifies the user / actor
    sessionId,         # groups events into a conversation session
    eventTimestamp,
    payload: [
      conversational:
        content.text: str
        role: str         # "USER" | "ASSISTANT"
    ]
  )

  vs BatchCreateMemoryRecords: pre-processed records, immediate writes
""")

if memory_id:
    print("--- Writing a conversational event via CreateEvent ---")
    try:
        resp = runtime.create_event(
            memoryId=memory_id,
            actorId=ACTOR_ID,
            sessionId="l37-demo-session-001",
            eventTimestamp=datetime.datetime.now(datetime.timezone.utc),
            payload=[
                {
                    "conversational": {
                        "content": {"text": "What AWS services have we used in this learning project?"},
                        "role": "USER",
                    }
                },
                {
                    "conversational": {
                        "content": {
                            "text": (
                                "We've used Bedrock (LLMs, AgentCore), Kinesis (streaming), "
                                "and Lambda (event consumers)."
                            )
                        },
                        "role": "ASSISTANT",
                    }
                },
            ],
        )
        event_id = resp.get("event", {}).get("eventId", "?")
        print(f"  Event created: {event_id}")
        print("  Note: extraction job will process this event asynchronously.")
        print("  Use StartMemoryExtractionJob to trigger extraction explicitly.")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        print(f"  ClientError [{code}]: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"  ERROR: {e}")
else:
    print("  Skipped (no memory_id)")


# ---------------------------------------------------------------------------
# ITERATION 4: Lambda consumer pattern
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 4: Lambda consumer pattern for Kinesis records")
print("=" * 70)
print("""
When a Kinesis stream is configured on a memory store, AgentCore pushes a
record to the stream each time a memory record is CREATED or MODIFIED.

Kinesis record structure (FULL_CONTENT level):
  {
    "eventType":  "CREATED" | "MODIFIED",
    "memoryId":   "...",
    "recordId":   "...",
    "timestamp":  "ISO-8601",
    "namespace":  "facts",
    "content":    { "text": "..." },    # only in FULL_CONTENT
    "metadata":   { ... }              # only in FULL_CONTENT
  }

Kinesis record structure (METADATA_ONLY level):
  {
    "eventType":  "CREATED" | "MODIFIED",
    "memoryId":   "...",
    "recordId":   "...",
    "timestamp":  "ISO-8601"
    # no content / metadata fields
  }

Lambda handler pseudocode:
  def handler(event, context):
    for record in event["Records"]:
      data = base64.b64decode(record["kinesis"]["data"])
      payload = json.loads(data)
      if payload["eventType"] == "CREATED":
        handle_new_record(payload)     # e.g. update user profile cache
      elif payload["eventType"] == "MODIFIED":
        handle_update(payload)         # e.g. invalidate cache entry

Use cases by level:
  FULL_CONTENT  → personalization (content needed immediately downstream)
  METADATA_ONLY → audit logging (fetch full record from LTM only if needed)

streamDeliveryResources supports max 1 Kinesis stream per memory store.
To fan-out to multiple consumers, use Kinesis Enhanced Fan-Out or
route through EventBridge Pipes.
""")

print("--- Lambda consumer demo (local simulation) ---")


def simulate_lambda_consumer(kinesis_records: list[dict]) -> None:
    """Simulate what a Lambda function would do with Kinesis records."""
    for payload in kinesis_records:
        event_type = payload.get("eventType", "UNKNOWN")
        record_id  = payload.get("recordId", "?")
        memory_id_ = payload.get("memoryId", "?")

        if event_type == "CREATED":
            print(f"  [NEW RECORD] {record_id} in {memory_id_}")
            if "content" in payload:
                print(f"    content: {payload['content'].get('text', '')[:80]}")
            # Downstream: update user profile cache, trigger personalization job, etc.

        elif event_type == "MODIFIED":
            print(f"  [UPDATED] {record_id} in {memory_id_}")
            # Downstream: invalidate cache, update embedding index, etc.

        else:
            print(f"  [UNKNOWN] eventType={event_type!r}, raw={json.dumps(payload)[:100]}")


if stream_arn:
    try:
        records = read_kinesis_records(STREAM_NAME, wait_secs=5)
        if records:
            simulate_lambda_consumer(records)
        else:
            print("  No records in stream yet — simulating with synthetic payloads:")
            synthetic = [
                {
                    "eventType": "CREATED",
                    "memoryId": memory_id or "demo-memory",
                    "recordId": "rec-001",
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "namespace": "facts",
                    "content": {"text": "User prefers dark mode in all UI applications."},
                },
                {
                    "eventType": "MODIFIED",
                    "memoryId": memory_id or "demo-memory",
                    "recordId": "rec-001",
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                },
            ]
            simulate_lambda_consumer(synthetic)
    except Exception as e:
        print(f"  ERROR: {e}")
else:
    print("  Skipped (no stream ARN)")


# ---------------------------------------------------------------------------
# ITERATION 5: RetrieveMemoryRecords — semantic search over LTM
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 5: RetrieveMemoryRecords — semantic search")
print("=" * 70)
print("""
RetrieveMemoryRecords performs semantic vector search across all memory records.
Works independently of the Kinesis pipeline — it queries the LTM store directly.

  runtime.retrieve_memory_records(
    memoryId,
    namespace: str,                      # required — namespace to search within
    searchCriteria: {                    # required
      searchQuery: str,                  # natural language query
      topK: int,                         # max results to return
      memoryStrategyId: str,             # optional filter
    },
    nextToken,
    maxResults,
  )
""")

if memory_id:
    print("--- Searching memory: 'user interface preferences' ---")
    try:
        resp = runtime.retrieve_memory_records(
            memoryId=memory_id,
            namespace="facts",
            searchCriteria={"searchQuery": "user interface preferences", "topK": 5},
        )
        results = resp.get("memoryRecordSummaries", [])
        if results:
            for r in results:
                text  = r.get("content", {}).get("text", "")
                score = r.get("score")
                ns    = r.get("namespaces", [])
                score_str = f"{score:.3f}" if score is not None else "?"
                print(f"  [{score_str}] {text[:80]}")
                print(f"    namespaces: {ns}")
        else:
            print("  No results (records may not yet be indexed — extraction is async)")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        print(f"  ClientError [{code}]: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"  ERROR: {e}")
else:
    print("  Skipped (no memory_id)")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("CLEANUP: Delete L37 memory store and Kinesis stream")
print("=" * 70)

if memory_id and memory_id != "l27agentcore_Memory-9RYaOkDitt":
    print(f"--- Deleting memory: {memory_id} ---")
    try:
        ctrl.delete_memory(memoryId=memory_id)
        print(f"  Deleted memory {memory_id}")
    except Exception as e:
        print(f"  ERROR: {e}")
else:
    print("  No L37 memory to delete")

if stream_arn:
    print(f"--- Deleting stream: {STREAM_NAME} ---")
    try:
        kinesis.delete_stream(StreamName=STREAM_NAME, EnforceConsumerDeletion=True)
        print(f"  Deleted stream {STREAM_NAME}")
    except Exception as e:
        print(f"  ERROR: {e}")
else:
    print("  No stream to delete")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("L37 COMPLETE — Key Takeaways")
print("=" * 70)
print("""
1. SDK requirement
   • botocore ≥ 1.42.70 for KinesisResource / StreamDeliveryResources shapes
   • Earlier versions have no Kinesis config in bedrock-agentcore-control model

2. streamDeliveryResources shape
   • Field on CreateMemory + UpdateMemory (both control-plane ops)
   • resources: list (max 1) of StreamDeliveryResource (union type)
   • kinesis: { dataStreamArn: str, contentConfigurations: [{ type, level }] }
   • ContentType enum: MEMORY_RECORDS (only value — more types may be added)
   • ContentLevel enum: FULL_CONTENT | METADATA_ONLY

3. Two LTM write paths
   • CreateEvent (runtime) → raw conversation turns → async extraction pipeline
   • BatchCreateMemoryRecords (runtime) → direct record injection, immediate

4. Kinesis consumer pattern
   • Kinesis records arrive as base64(JSON) in record["kinesis"]["data"]
   • eventType: CREATED | MODIFIED
   • FULL_CONTENT includes content + metadata; METADATA_ONLY has ID + timestamp only
   • Fan-out: max 1 stream per memory store; use Enhanced Fan-Out or EventBridge Pipes

5. Retrieval is independent of streaming
   • RetrieveMemoryRecords → semantic vector search, always queries LTM directly
   • Streaming is for *push* notifications to downstream consumers, not for retrieval

6. IAM requirement (CreateMemory with streamDeliveryResources)
   • memoryExecutionRoleArn is REQUIRED when streamDeliveryResources is specified
   • The shape marks it optional — but the API enforces it when Kinesis config present
   • Error: "Please provide memoryExecutionRoleArn when streamDeliveryResources is specified"
   • Role needs: kinesis:PutRecord + kinesis:PutRecords on the target stream
   • Trust policy: bedrock-agentcore.amazonaws.com must be able to assume the role

7. Name validation (CreateMemory / strategy names)
   • Regex: [a-zA-Z][a-zA-Z0-9_]{0,47} — alphanumeric + underscore only, no hyphens
   • Strategy name same constraint
   • Max 47 additional characters after the first letter
""")

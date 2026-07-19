"""
Level 45h: Incremental Indexing — Production Index Lifecycle

In production, documents change. This level handles:
  1. First ingest      — hash every chunk, store hash in metadata
  2. Detect changes    — re-ingest: hash diff finds new/modified/deleted docs
  3. Update changed    — delete old vectors, add new ones (S3 Vectors has no update)
  4. Tombstone deleted — mark as deleted or purge from index

Why content hashing:
  Without hashing, re-ingesting a corpus re-embeds everything.
  With hashing, only CHANGED content triggers Bedrock embedding calls.
  Each embedding call costs money and time. Hashing makes re-index O(changed).

Index state tracking:
  Store chunk metadata including content_hash in S3 Vectors itself.
  On re-index: list_vectors → build {key: hash} map → diff against new corpus.
  No external database needed.

Lifecycle events demonstrated:
  t0: Ingest 5 sections
  t1: Edit 1 section (changed), add 1 new section, delete 1 section
  t2: Re-ingest — show exactly which vectors are added/updated/deleted
"""
import json
import re
import copy
import boto3
import hashlib
from tools import get_model

REGION         = "us-east-1"
BUCKET_NAME    = "strands-incr-l45h"
INDEX_NAME     = "docs-index"
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIM      = 1024

s3v        = boto3.client("s3vectors",       region_name=REGION)
bedrock_rt = boto3.client("bedrock-runtime", region_name=REGION)

embed_calls = 0  # track how many Bedrock calls are made

def embed(text: str) -> list[float]:
    global embed_calls
    embed_calls += 1
    body = json.dumps({"inputText": text, "dimensions": EMBED_DIM, "normalize": True})
    resp = bedrock_rt.invoke_model(modelId=EMBED_MODEL_ID, body=body)
    return json.loads(resp["body"].read())["embedding"]

def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── Corpus versions ────────────────────────────────────────────────────────────

CORPUS_V1 = [
    {"key": "sec-agent",      "section": "Agent Class",
     "text": "The Agent class manages tool orchestration and conversation history. "
             "Agents are stateful — they accumulate turns in agent.messages."},
    {"key": "sec-tools",      "section": "Tool System",
     "text": "Use @tool for native functions. MCPClient for MCP servers. "
             "Add prefix parameter to avoid name collisions."},
    {"key": "sec-memory",     "section": "Short-term Memory",
     "text": "Set callback_handler=None to disable streaming. "
             "History is session-scoped and cleared on process exit."},
    {"key": "sec-ltm",        "section": "Long-term Memory",
     "text": "create_memory_store() for cross-session persistence. "
             "Pass save_memory_tool and retrieve_memories_tool to Agent."},
    {"key": "sec-deploy",     "section": "Production Deployment",
     "text": "POST /invocations and GET /ping on port 8080. "
             "Package as Docker, push to ECR, register with BedrockAgentCoreApp."},
]

# V2: 1 section CHANGED (deploy), 1 NEW (observability), 1 DELETED (sec-memory)
CORPUS_V2 = [
    {"key": "sec-agent",      "section": "Agent Class",            # UNCHANGED
     "text": CORPUS_V1[0]["text"]},
    {"key": "sec-tools",      "section": "Tool System",            # UNCHANGED
     "text": CORPUS_V1[1]["text"]},
    # sec-memory DELETED (not in V2)
    {"key": "sec-ltm",        "section": "Long-term Memory",       # UNCHANGED
     "text": CORPUS_V1[3]["text"]},
    {"key": "sec-deploy",     "section": "Production Deployment",  # CHANGED
     "text": "POST /invocations and GET /ping on port 8080. "
             "Package as Docker, push to ECR, register with BedrockAgentCoreApp. "
             "NEW: Agents are not thread-safe — create a fresh instance per Lambda request."},
    {"key": "sec-observ",     "section": "Observability",          # NEW
     "text": "Emit tool_call_count and tool_latency_ms to CloudWatch. "
             "Use X-Ray for end-to-end latency tracing across agent chains."},
]


# ── Index management ───────────────────────────────────────────────────────────

def setup():
    try:
        s3v.get_vector_bucket(vectorBucketName=BUCKET_NAME)
    except s3v.exceptions.NotFoundException:
        s3v.create_vector_bucket(vectorBucketName=BUCKET_NAME)
    try:
        s3v.get_index(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME)
    except s3v.exceptions.NotFoundException:
        s3v.create_index(
            vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME,
            dataType="float32", dimension=EMBED_DIM, distanceMetric="cosine",
            metadataConfiguration={"nonFilterableMetadataKeys": ["text"]},
        )


def build_enriched_chunks(corpus: list[dict]) -> list[dict]:
    """Convert corpus docs to indexable chunks with content hashes."""
    chunks = []
    for doc in corpus:
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', doc["text"])
                 if len(s.strip()) >= 15]
        for i, sent in enumerate(sents):
            chunk_key = f"{doc['key']}:s{i}"
            enriched  = f"Section: {doc['section']} | {sent}"
            chunks.append({
                "key":          chunk_key,
                "section":      doc["section"],
                "parent_key":   doc["key"],
                "sentence":     sent,
                "embed_text":   enriched,
                "content_hash": content_hash(enriched),
            })
    return chunks


def get_indexed_hashes() -> dict[str, str]:
    """List all vectors in the index, return {key: content_hash}."""
    indexed: dict[str, str] = {}
    next_token = None
    while True:
        kwargs = dict(
            vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME,
            returnMetadata=True, returnData=False, maxResults=100,
        )
        if next_token:
            kwargs["nextToken"] = next_token
        resp = s3v.list_vectors(**kwargs)
        for v in resp.get("vectors", []):
            h = v.get("metadata", {}).get("content_hash", "")
            indexed[v["key"]] = h
        next_token = resp.get("nextToken")
        if not next_token:
            break
    return indexed


def ingest_incremental(new_chunks: list[dict]) -> dict:
    """
    Compare new_chunks against current index state.
    Only embed and upsert chunks that are new or changed.
    Delete vectors for chunks that no longer exist.
    Returns a summary of what happened.
    """
    indexed_hashes = get_indexed_hashes()
    new_hash_map   = {c["key"]: c for c in new_chunks}

    to_add      = []  # new or changed
    to_delete   = []  # removed from corpus
    unchanged   = []  # hash matches — skip embedding

    for chunk in new_chunks:
        k = chunk["key"]
        if k not in indexed_hashes:
            to_add.append(chunk)           # NEW
        elif indexed_hashes[k] != chunk["content_hash"]:
            to_add.append(chunk)           # CHANGED
            to_delete.append(k)            # delete old vector first
        else:
            unchanged.append(k)            # UNCHANGED — skip

    # Keys in index but not in new corpus → deleted docs
    orphaned = [k for k in indexed_hashes if k not in new_hash_map]
    to_delete.extend(orphaned)

    # Delete stale/removed vectors
    if to_delete:
        s3v.delete_vectors(
            vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME,
            keys=to_delete,
        )

    # Embed and insert new/changed chunks
    if to_add:
        vectors = []
        for c in to_add:
            vec = embed(c["embed_text"])
            vectors.append({
                "key":  c["key"],
                "data": {"float32": vec},
                "metadata": {
                    "text":         c["sentence"],
                    "section":      c["section"],
                    "parent_key":   c["parent_key"],
                    "content_hash": c["content_hash"],
                },
            })
        s3v.put_vectors(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME, vectors=vectors)

    return {
        "added":     len(to_add),
        "deleted":   len(to_delete),
        "unchanged": len(unchanged),
        "orphaned":  len(orphaned),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("L45h: Incremental Indexing — Production Index Lifecycle")
    print("=" * 60)

    setup()

    # ── T0: Initial ingest ────────────────────────────────────────────────────
    print(f"\n[T0] Initial ingest — {len(CORPUS_V1)} sections")
    embed_calls = 0
    chunks_v1 = build_enriched_chunks(CORPUS_V1)
    result_v1 = ingest_incremental(chunks_v1)
    print(f"  Corpus: {len(CORPUS_V1)} sections → {len(chunks_v1)} chunks")
    print(f"  Result: {result_v1}")
    print(f"  Embed calls: {embed_calls} (all new)")

    # Show what's indexed
    indexed = get_indexed_hashes()
    print(f"  Index state: {len(indexed)} vectors")

    # ── T1: Re-ingest same corpus (no changes) ────────────────────────────────
    print(f"\n[T1] Re-ingest SAME corpus (idempotent check)")
    embed_calls = 0
    chunks_v1b = build_enriched_chunks(CORPUS_V1)  # same data
    result_v1b = ingest_incremental(chunks_v1b)
    print(f"  Result: {result_v1b}")
    print(f"  Embed calls: {embed_calls} (should be 0 — nothing changed)")

    # ── T2: V2 corpus — 1 changed, 1 new, 1 deleted ──────────────────────────
    print(f"\n[T2] Update to V2 corpus:")
    print(f"  CHANGED:  sec-deploy (added thread-safety note)")
    print(f"  ADDED:    sec-observ (new Observability section)")
    print(f"  DELETED:  sec-memory (Short-term Memory removed)")
    embed_calls = 0
    chunks_v2 = build_enriched_chunks(CORPUS_V2)
    result_v2 = ingest_incremental(chunks_v2)
    print(f"  Corpus: {len(CORPUS_V2)} sections → {len(chunks_v2)} chunks")
    print(f"  Result: {result_v2}")
    print(f"  Embed calls: {embed_calls} (only changed + new chunks)")

    # Verify final index state
    final_indexed = get_indexed_hashes()
    print(f"\n[T3] Final index state: {len(final_indexed)} vectors")

    # Verify deleted section is gone
    memory_keys = [k for k in final_indexed if "sec-memory" in k]
    observ_keys = [k for k in final_indexed if "sec-observ" in k]
    print(f"  sec-memory keys present: {len(memory_keys)} (expected 0)")
    print(f"  sec-observ keys present: {len(observ_keys)} (expected >0)")

    # Cost comparison
    full_reingest_calls = len(chunks_v2)
    print(f"\n[T4] Embed call efficiency:")
    print(f"  Full re-ingest would need: {full_reingest_calls} embed calls")
    print(f"  Incremental actually used: {embed_calls} embed calls")
    pct = round(embed_calls / full_reingest_calls * 100)
    print(f"  Cost savings: {100 - pct}% fewer Bedrock calls")

    print("""
[5] Key patterns:

  Content hash = SHA-256[:16] of the enriched embed text.
  Store hash in metadata at ingest time.
  On re-index: list_vectors → get all key:hash pairs.
  Diff: new_hash_map vs indexed_hashes → add/update/delete.

  Three diff outcomes per chunk:
    key not in index  → NEW    → embed + put
    key in index, hash differs  → CHANGED → delete old + embed + put new
    key in index, hash same     → UNCHANGED → skip (zero embed calls)
    key in index but not in new corpus → ORPHANED → delete

  S3 Vectors has no "update" operation:
    delete_vectors(old_key) + put_vectors(new_key + new_vector)
    Keys are immutable — to change a vector you must delete + re-insert.

  list_vectors for state snapshot:
    Paginate with nextToken. maxResults=100 per page.
    Returns key + metadata (including content_hash if stored there).
    No need for a separate database to track index state.

  Production considerations:
    Run incremental index as a scheduled job (daily/hourly).
    Source of truth: content_hash in metadata — survives index rebuilds.
    For large corpora: process in batches of 500, sleep between batches
    to respect S3 Vectors TPS limits.
    """)

    print("[cleanup]...")
    try:
        s3v.delete_index(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME)
        s3v.delete_vector_bucket(vectorBucketName=BUCKET_NAME)
        print("  done")
    except Exception as e:
        print(f"  {e}")

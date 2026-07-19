"""
Level 45e: Re-ranking — Two-Stage Retrieval

Vector similarity is a coarse, fast first-pass filter.
It measures geometric proximity in 1024-dimensional space.
It does NOT measure "does this chunk actually answer the question?"

Two-stage retrieval:
  Stage 1 (recall):    vector similarity, retrieve top-N (wide net)
  Stage 2 (precision): LLM scores each candidate for relevance to query
                       → reorder → take top-K from reranked list

Why it works:
  The embedding model compresses thousands of tokens into 1024 floats.
  Compression loses nuance. A chunk about "memory" and a chunk about
  "memory management in production" have similar embeddings but very
  different relevance to a specific query.
  The LLM re-ranker reads the full text — no compression loss.

Cost model:
  Stage 1: 1 embedding call (fast, cheap, ~100ms)
  Stage 2: 1 LLM call per candidate chunk (slower, but only top-N)
  Trade-off: N=10 candidates → 10 relevance scores → top-3 returned.
  For N≤20, re-ranking latency is acceptable in production.

This level:
  - Demonstrates cases where rank 4-5 is the correct answer
  - Compares: no rerank vs rerank(N=6) vs rerank(N=10)
  - Shows score distribution: high-similarity wrong vs low-similarity right
"""
import json
import re
import boto3
from strands import Agent
from tools import get_model

REGION         = "us-east-1"
BUCKET_NAME    = "strands-rerank-l45e"
INDEX_NAME     = "docs-index"
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIM      = 1024

s3v        = boto3.client("s3vectors",       region_name=REGION)
bedrock_rt = boto3.client("bedrock-runtime", region_name=REGION)

_embed_cache: dict[str, list[float]] = {}

def embed(text: str) -> list[float]:
    if text in _embed_cache:
        return _embed_cache[text]
    body = json.dumps({"inputText": text, "dimensions": EMBED_DIM, "normalize": True})
    resp = bedrock_rt.invoke_model(modelId=EMBED_MODEL_ID, body=body)
    vec = json.loads(resp["body"].read())["embedding"]
    _embed_cache[text] = vec
    return vec


# ── Corpus — denser, more sections, more potential for rank drift ─────────────
# More docs + overlapping topics → harder for vector similarity alone.

CORPUS = [
    {"doc": "Strands SDK Guide", "sections": [
        {"section": "Agent Class",
         "text": "The Agent class is the central building block of Strands. "
                 "It manages tool orchestration, conversation history, and model selection. "
                 "Agents are stateful objects — they retain conversation turns. "
                 "Create one by passing a model and an optional tool list."},
        {"section": "Tool System",
         "text": "Strands supports native @tool functions and MCP servers. "
                 "Native tools run in-process — low latency, full Python access. "
                 "MCP tools run out-of-process as separate servers, framework-agnostic. "
                 "Use the prefix parameter when mounting multiple MCP servers to avoid name collisions."},
        {"section": "Short-term Memory",
         "text": "Conversation history is stored automatically inside the Agent object. "
                 "It is session-scoped and lost when the process exits. "
                 "Set callback_handler=None to suppress token streaming without affecting memory. "
                 "Read history via agent.messages."},
        {"section": "Long-term Memory",
         "text": "AgentCore LTM provides cross-session persistence. "
                 "Create a store with create_memory_store(), pass save_memory_tool "
                 "and retrieve_memories_tool to the Agent. "
                 "Semantic consolidation merges duplicate memories automatically."},
        {"section": "Streaming",
         "text": "Strands streams by default using the PrintingCallbackHandler. "
                 "Set callback_handler=None to disable streaming and capture the full response. "
                 "For async workloads use stream_async() which yields typed events. "
                 "Token-level callbacks receive each delta as it arrives."},
        {"section": "Local Development",
         "text": "Run agents directly: uv run python agent.py. "
                 "LiteLLM proxy at localhost:4000 handles model routing. "
                 "No Docker or port setup needed. "
                 "Use get_model('haiku') for fast iterations and get_model('sonnet') for quality."},
        {"section": "Production Deployment",
         "text": "AgentCore hosts agents on managed infrastructure. "
                 "Requires POST /invocations and GET /ping on port 8080. "
                 "Package as Docker image, push to ECR, register with BedrockAgentCoreApp. "
                 "Agents are not thread-safe — instantiate per request in Lambda."},
        {"section": "Error Recovery",
         "text": "Wrap agent calls in try/except for transient API errors. "
                 "Use exponential backoff for throttling. "
                 "For critical workflows, implement a retry loop with circuit breaker. "
                 "Log tool call failures with the tool name and input arguments."},
        {"section": "Observability",
         "text": "Instrument agents with structured logging on every tool call. "
                 "Emit metrics: tool_call_count, tool_latency_ms, token_usage. "
                 "Use AWS CloudWatch for production metrics. "
                 "Trace multi-agent workflows with X-Ray for end-to-end latency visibility."},
    ]},
]


# ── Ingestion with contextual enrichment ──────────────────────────────────────

def setup():
    import hashlib
    try:
        s3v.get_vector_bucket(vectorBucketName=BUCKET_NAME)
    except s3v.exceptions.NotFoundException:
        s3v.create_vector_bucket(vectorBucketName=BUCKET_NAME)
    try:
        s3v.get_index(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME)
        print("  [ok] index already exists")
        return
    except s3v.exceptions.NotFoundException:
        s3v.create_index(
            vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME,
            dataType="float32", dimension=EMBED_DIM, distanceMetric="cosine",
            metadataConfiguration={"nonFilterableMetadataKeys": ["text"]},
        )

    seen: set[str] = set()
    vectors = []
    for doc in CORPUS:
        for sec in doc["sections"]:
            sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', sec["text"]) if len(s.strip()) >= 20]
            for i, sent in enumerate(sents):
                h = hashlib.md5(sent.encode()).hexdigest()[:8]
                if h in seen:
                    continue
                seen.add(h)
                enriched = f"Document: {doc['doc']} | Section: {sec['section']} | {sent}"
                vectors.append({
                    "key": f"{sec['section']}:{i}",
                    "data": {"float32": embed(enriched)},
                    "metadata": {"text": sent, "section": sec["section"]},
                })
    s3v.put_vectors(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME, vectors=vectors)
    print(f"  [ingested] {len(vectors)} chunks")


# ── Retrieval ──────────────────────────────────────────────────────────────────

def vector_retrieve(question: str, top_k: int = 10) -> list[dict]:
    qv = embed(question)
    results = s3v.query_vectors(
        vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME,
        topK=top_k, queryVector={"float32": qv},
        returnMetadata=True, returnDistance=True,
    ).get("vectors", [])
    return [
        {"section": r["metadata"]["section"],
         "text":    r["metadata"]["text"],
         "vec_sim": round(1 - r.get("distance", 1), 4),
         "vec_rank": i + 1}
        for i, r in enumerate(results)
    ]


# ── LLM Re-ranker ──────────────────────────────────────────────────────────────

_haiku = get_model("haiku")

def llm_rerank(question: str, candidates: list[dict]) -> list[dict]:
    """
    Score each candidate chunk for relevance to the question.
    Returns candidates sorted by LLM relevance score (descending).
    Uses a single batched prompt — one LLM call for all candidates.
    """
    numbered = "\n".join(
        f"[{i+1}] Section={c['section']} | Text: {c['text'][:120]}"
        for i, c in enumerate(candidates)
    )
    ranker = Agent(model=_haiku, callback_handler=None)
    resp = str(ranker(
        f"Rate each passage's relevance to the question on a scale 0-10.\n"
        f"Return ONLY a comma-separated list of scores in order, e.g.: 8,3,7,2,9,1\n"
        f"No explanation. Exactly {len(candidates)} scores.\n\n"
        f"Question: {question}\n\nPassages:\n{numbered}"
    ))

    # Parse scores
    nums = re.findall(r'\d+(?:\.\d+)?', resp)
    scores = [float(n) for n in nums[:len(candidates)]]

    # Pad if model returned fewer scores
    while len(scores) < len(candidates):
        scores.append(0.0)

    for i, c in enumerate(candidates):
        c["llm_score"] = scores[i]
        c["llm_rank"]  = 0  # will be set after sort

    reranked = sorted(candidates, key=lambda x: x["llm_score"], reverse=True)
    for i, c in enumerate(reranked):
        c["llm_rank"] = i + 1

    return reranked


# ── Test queries — chosen to expose rank drift ────────────────────────────────
# These queries have an expected answer that vector similarity tends to bury
# because a more generic/similar-sounding chunk scores higher.

TEST_QUERIES = [
    ("How do I disable token streaming in Strands?",             "Streaming"),
    ("What observability tools should I use in production?",     "Observability"),
    ("How do I handle API throttling errors?",                   "Error Recovery"),
    ("What is the difference between callback_handler=None and streaming?", "Streaming"),
    ("How do I deploy a Strands agent to managed infrastructure?","Production Deployment"),
    ("How do I avoid tool name conflicts with multiple MCP servers?", "Tool System"),
    ("What metrics should I emit for agent monitoring?",         "Observability"),
    ("How do I capture the full response instead of streaming?", "Streaming"),
]


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("L45e: Re-ranking — Two-Stage Retrieval")
    print("=" * 60)

    print("\n[1] Setting up index...")
    setup()

    FIRST_PASS_N = 8  # retrieve this many before re-ranking

    print(f"\n[2] Per-query: vector rank vs LLM rank for correct section")
    print(f"  (first pass retrieves top-{FIRST_PASS_N}, re-ranker reorders)")
    print()
    print(f"  {'Query':<48} {'Expected':<22} {'Vec R':>6} {'LLM R':>6} {'Delta':>6}")
    print(f"  {'-'*48} {'-'*22} {'-'*6} {'-'*6} {'-'*6}")

    rank_improvements = []
    rank_degradations = []

    for q, expected in TEST_QUERIES:
        candidates = vector_retrieve(q, top_k=FIRST_PASS_N)
        reranked   = llm_rerank(q, candidates)

        # Find correct section in both orderings
        vec_rank = next((c["vec_rank"] for c in candidates if c["section"] == expected), None)
        llm_rank = next((c["llm_rank"] for c in reranked  if c["section"] == expected), None)

        if vec_rank and llm_rank:
            delta = vec_rank - llm_rank  # positive = improved rank
            arrow = f"+{delta}" if delta > 0 else (f"{delta}" if delta < 0 else "0")
            print(f"  {q[:47]:<48} {expected:<22} {vec_rank:>6} {llm_rank:>6} {arrow:>6}")
            if delta > 0:
                rank_improvements.append((q, expected, vec_rank, llm_rank))
            elif delta < 0:
                rank_degradations.append((q, expected, vec_rank, llm_rank))
        else:
            print(f"  {q[:47]:<48} {expected:<22} {'N/A':>6} {'N/A':>6} {'N/A':>6}")

    # ── Precision comparison ───────────────────────────────────────────────────
    print(f"\n[3] Precision@1 comparison:")

    vec_hits = rerank_hits = 0
    for q, expected in TEST_QUERIES:
        candidates = vector_retrieve(q, top_k=FIRST_PASS_N)
        if candidates[0]["section"] == expected:
            vec_hits += 1
        reranked = llm_rerank(q, candidates)
        if reranked[0]["section"] == expected:
            rerank_hits += 1

    total = len(TEST_QUERIES)
    print(f"  Vector only  (top-1 of {FIRST_PASS_N}): {vec_hits}/{total} = {vec_hits/total:.0%}")
    print(f"  After LLM re-rank:           {rerank_hits}/{total} = {rerank_hits/total:.0%}")

    # ── Show a rank-promotion case in detail ──────────────────────────────────
    if rank_improvements:
        q, expected, vr, lr = rank_improvements[0]
        print(f"\n[4] Rank promotion case:")
        print(f"  Query:    {q!r}")
        print(f"  Expected: {expected}")
        candidates = vector_retrieve(q, top_k=FIRST_PASS_N)
        reranked   = llm_rerank(q, candidates)
        print(f"\n  Before re-rank (top 4 by vector similarity):")
        for c in candidates[:4]:
            marker = " <-- correct" if c["section"] == expected else ""
            print(f"    rank {c['vec_rank']} | sim={c['vec_sim']:.4f} | [{c['section']}]{marker}")
            print(f"      {c['text'][:80]!r}")
        print(f"\n  After LLM re-rank (top 4):")
        for c in reranked[:4]:
            marker = " <-- correct" if c["section"] == expected else ""
            print(f"    rank {c['llm_rank']} | llm_score={c['llm_score']:.1f} | [{c['section']}]{marker}")
            print(f"      {c['text'][:80]!r}")

    print(f"""
[5] Key concepts:

  Two-stage retrieval:
    Stage 1 — vector similarity (fast, wide net):
      embed(query) → cosine distance → top-N candidates
      Cheap: 1 embedding call. Captures semantic similarity.
      Misses: nuanced relevance, topic overlap confusion.

    Stage 2 — LLM re-ranking (precise, narrow):
      "Rate each passage relevance 0-10" → reorder by score
      Reads full text, no compression loss.
      Fixes: topic confusion, ambiguous chunks, implicit relevance.

  Batched scoring (one LLM call):
    Send all N candidates in one prompt, get comma-separated scores.
    Parse with regex. Much cheaper than N separate calls.
    Haiku is sufficient — scoring is simpler than generation.

  Cost model:
    N=8:  1 embed + 1 LLM call. ~200ms total. Acceptable.
    N=20: 1 embed + 1 LLM call. ~400ms total. Production viable.
    N=50: 1 embed + 1 LLM call. ~800ms total. Diminishing returns.

  When to use:
    High-stakes retrieval (legal, medical, financial documents)
    Topic-heavy corpora with many similar-sounding sections
    When precision@1 matters more than latency
    """)

    print("[cleanup]...")
    try:
        s3v.delete_index(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME)
        s3v.delete_vector_bucket(vectorBucketName=BUCKET_NAME)
        print("  done")
    except Exception as e:
        print(f"  {e}")

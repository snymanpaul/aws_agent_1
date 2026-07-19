"""
Level 45d: HyDE + Query Expansion — Query-Side Retrieval Enrichment

L45c proved ingestion-side enrichment matters most.
This level covers the query-side mirror image.

Two techniques:

  HyDE (Hypothetical Document Embeddings):
    Problem: question embeddings live in a different semantic space
    than answer/document embeddings. "How do agents share tools?"
    has low cosine to "MCP tools run as separate processes."
    Fix: use an LLM to generate a HYPOTHETICAL ANSWER, embed that.
    The hypothetical answer is in document space — cosine is high.

    Q: "How do agents share tools across frameworks?"
    HyDE: "Strands supports MCP servers which run as separate
           processes and are framework-agnostic, allowing tool
           reuse across different agent implementations."
    Doc: "MCP tools run as separate processes and are framework-agnostic."
    cosine(HyDE, doc) >> cosine(Q, doc)

  Query expansion (multi-query):
    Generate N paraphrases of the query. Retrieve for each.
    Merge via Reciprocal Rank Fusion (RRF): score = Σ 1/(k + rank_i).
    Different phrasings hit different semantic neighbourhoods.

Test design:
  Baseline index: contextual enrichment (100% on L45c queries).
  Test set: 8 harder vocabulary-mismatched queries that contextual
            enrichment alone may not fully solve.
  Approaches: raw, HyDE, expansion(3), HyDE+expansion.
  Metric: precision@1.
"""
import json
import re
import boto3
from strands import Agent
from tools import get_model

REGION         = "us-east-1"
BUCKET_NAME    = "strands-hyde-l45d"
INDEX_NAME     = "ctx-index"
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIM      = 1024

s3v        = boto3.client("s3vectors",      region_name=REGION)
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

def cosine(a, b):
    return round(sum(x * y for x, y in zip(a, b)), 4)


# ── Corpus (same as L45c, contextual enrichment strategy) ────────────────────

CORPUS = [
    {"doc": "Strands SDK Guide", "sections": [
        {"section": "Agent Class",
         "text": "The Agent class is the central building block of Strands. "
                 "It manages tool orchestration, conversation history, and model selection. "
                 "Agents are stateful objects — they remember prior turns in the conversation. "
                 "To create one, pass a model and an optional list of tools."},
        {"section": "Tool System",
         "text": "It supports two types of tools: native @tool functions and MCP servers. "
                 "Native @tool functions run in-process — low latency, full Python access. "
                 "MCP tools run as separate processes and are framework-agnostic. "
                 "The tradeoff is latency versus portability."},
        {"section": "Short-term Memory",
         "text": "This is handled automatically through conversation history stored in the Agent. "
                 "It is scoped to a single session and not persisted by default. "
                 "Passing callback_handler=None suppresses streaming output but does not affect memory. "
                 "The history is accessible via agent.messages."},
        {"section": "Long-term Memory",
         "text": "It uses AgentCore's LTM API for cross-session persistence. "
                 "Call create_memory_store() first, then pass save_memory_tool "
                 "and retrieve_memories_tool to the Agent constructor. "
                 "Memories are consolidated semantically — duplicates are merged."},
        {"section": "Local Development",
         "text": "Run it directly with Python: uv run python agent.py. "
                 "No server process or port configuration is required. "
                 "Set callback_handler=None for clean output instead of streaming tokens. "
                 "LiteLLM proxy handles model routing at localhost:4000."},
        {"section": "Production Deployment",
         "text": "It requires POST /invocations and GET /ping endpoints on port 8080. "
                 "Package the agent in a Docker image, push to ECR, "
                 "and register with BedrockAgentCoreApp. "
                 "Agents are not thread-safe — create a fresh instance per request in Lambda."},
    ]},
]


# ── Ingestion (contextual enrichment — best strategy from L45c) ───────────────

def ingest_corpus():
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

    import hashlib
    seen: set[str] = set()
    vectors = []
    for doc in CORPUS:
        for sec in doc["sections"]:
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', sec["text"]) if len(s.strip()) >= 20]
            for i, sent in enumerate(sentences):
                h = hashlib.md5(sent.encode()).hexdigest()[:8]
                if h in seen:
                    continue
                seen.add(h)
                enriched = f"Document: {doc['doc']} | Section: {sec['section']} | {sent}"
                key = f"{doc['doc']}:{sec['section']}:{i}"
                vectors.append({
                    "key": key,
                    "data": {"float32": embed(enriched)},
                    "metadata": {"text": sent, "doc": doc["doc"], "section": sec["section"]},
                })
    s3v.put_vectors(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME, vectors=vectors)
    print(f"  [ingested] {len(vectors)} chunks (contextual enrichment)")


# ── Retrieval primitives ───────────────────────────────────────────────────────

def retrieve(query_text: str, top_k: int = 3) -> list[dict]:
    qv = embed(query_text)
    results = s3v.query_vectors(
        vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME,
        topK=top_k, queryVector={"float32": qv},
        returnMetadata=True, returnDistance=True,
    ).get("vectors", [])
    return [
        {"section": r["metadata"]["section"],
         "text":    r["metadata"]["text"],
         "sim":     round(1 - r.get("distance", 1), 4),
         "rank":    i + 1}
        for i, r in enumerate(results)
    ]


# ── HyDE: generate hypothetical answer, embed that ───────────────────────────

_haiku = get_model("haiku")

def hyde_retrieve(question: str, top_k: int = 3) -> list[dict]:
    """
    Generate a hypothetical document that would answer the question,
    then embed THAT instead of the question.
    """
    gen = Agent(model=_haiku, callback_handler=None)
    hyp_doc = str(gen(
        f"Write a short factual paragraph (2-3 sentences) that directly answers "
        f"this question about the Strands SDK. Be specific and technical.\n\n"
        f"Question: {question}"
    ))
    return retrieve(hyp_doc, top_k=top_k)


# ── Query Expansion: generate paraphrases, merge with RRF ────────────────────

def expand_queries(question: str, n: int = 3) -> list[str]:
    """Generate N paraphrases of the query."""
    gen = Agent(model=_haiku, callback_handler=None)
    resp = str(gen(
        f"Generate {n} different phrasings of this question. "
        f"Vary vocabulary and structure. Return ONLY the {n} questions, "
        f"one per line, no numbering or bullets.\n\nOriginal: {question}"
    ))
    lines = [l.strip() for l in resp.strip().splitlines() if l.strip()]
    return lines[:n]


def rrf_merge(results_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """
    Reciprocal Rank Fusion: score = Σ 1/(k + rank_i) across all result lists.
    k=60 is the standard constant (dampens high-rank advantage).
    """
    scores: dict[str, float] = {}
    best: dict[str, dict] = {}

    for results in results_lists:
        for item in results:
            key = item["section"]
            scores[key] = scores.get(key, 0) + 1 / (k + item["rank"])
            if key not in best or item["sim"] > best[key]["sim"]:
                best[key] = item

    merged = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    return [{"section": s, "text": best[s]["text"], "rrf_score": round(scores[s], 5),
             "sim": best[s]["sim"]} for s in merged]


def expansion_retrieve(question: str, top_k: int = 3) -> list[dict]:
    paraphrases = expand_queries(question, n=3)
    all_results = [retrieve(q, top_k=top_k) for q in [question] + paraphrases]
    return rrf_merge(all_results)


def hyde_expansion_retrieve(question: str, top_k: int = 3) -> list[dict]:
    """HyDE + expansion: generate hypothetical answer, also expand original query."""
    gen = Agent(model=_haiku, callback_handler=None)
    hyp_doc = str(gen(
        f"Write a short factual paragraph (2-3 sentences) answering this "
        f"Strands SDK question precisely: {question}"
    ))
    paraphrases = expand_queries(question, n=2)
    all_results = [
        retrieve(hyp_doc, top_k=top_k),           # HyDE
        *[retrieve(q, top_k=top_k) for q in [question] + paraphrases],  # expansion
    ]
    return rrf_merge(all_results)


# ── Test queries (vocabulary-mismatched — hard for raw embedding) ─────────────
# These use different vocabulary than the document text.

TEST_QUERIES = [
    # (question, expected_section)
    ("How do I share tool capabilities across different agent frameworks?",
     "Tool System"),
    ("What are the concurrency constraints for serverless agent hosting?",
     "Production Deployment"),
    ("Does the memory system handle redundant or duplicate information?",
     "Long-term Memory"),
    ("How do I prevent the agent from printing tokens to stdout?",
     "Short-term Memory"),
    ("What handles model abstraction and routing in local development?",
     "Local Development"),
    ("How does the agent track what happened in previous turns?",
     "Agent Class"),
    ("What persistence options exist for knowledge across session boundaries?",
     "Long-term Memory"),
    ("How do I containerise and register an agent with AWS?",
     "Production Deployment"),
]


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate(approach_fn, queries, label: str) -> dict:
    hits = 0
    sims = []
    for q, expected in queries:
        results = approach_fn(q)
        if results:
            top = results[0]
            if top["section"] == expected:
                hits += 1
                sims.append(top.get("sim", top.get("rrf_score", 0)))
    p1 = hits / len(queries)
    mean_sim = round(sum(sims) / len(sims), 4) if sims else 0.0
    return {"label": label, "precision@1": p1, "mean_sim": mean_sim,
            "hits": hits, "total": len(queries)}


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("L45d: HyDE + Query Expansion")
    print("=" * 60)

    print("\n[1] Setting up index (contextual enrichment)...")
    ingest_corpus()

    # ── Per-query detail ───────────────────────────────────────────────────────
    print("\n[2] Per-query top-1 section — 4 approaches:")
    header = f"  {'Query (truncated)':<42} {'Expected':<22} {'Raw':>6} {'HyDE':>6} {'Exp':>6} {'H+E':>6}"
    print(header)
    print(f"  {'-'*42} {'-'*22} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")

    approach_results = {q: {} for q, _ in TEST_QUERIES}

    for q, expected in TEST_QUERIES:
        raw_r  = retrieve(q, top_k=3)
        hyde_r = hyde_retrieve(q, top_k=3)
        exp_r  = expansion_retrieve(q, top_k=3)
        he_r   = hyde_expansion_retrieve(q, top_k=3)

        def mark(results):
            top = results[0] if results else {}
            hit = "✓" if top.get("section") == expected else "✗"
            sim = top.get("sim", top.get("rrf_score", 0))
            return f"{hit}{sim:.3f}"

        approach_results[q] = {
            "raw": raw_r, "hyde": hyde_r, "exp": exp_r, "he": he_r
        }

        print(f"  {q[:41]:<42} {expected:<22} {mark(raw_r):>6} {mark(hyde_r):>6} "
              f"{mark(exp_r):>6} {mark(he_r):>6}")

    # ── Precision summary ──────────────────────────────────────────────────────
    print(f"\n[3] Precision@1 summary:")
    print(f"  {'Approach':<22} {'Precision':>10} {'Hits':>6}")
    print(f"  {'-'*22} {'-'*10} {'-'*6}")

    approaches = [
        ("Raw query",         lambda q: retrieve(q, 3)),
        ("HyDE",              lambda q: hyde_retrieve(q, 3)),
        ("Query expansion",   lambda q: expansion_retrieve(q, 3)),
        ("HyDE + expansion",  lambda q: hyde_expansion_retrieve(q, 3)),
    ]
    for label, fn in approaches:
        ev = evaluate(fn, TEST_QUERIES, label)
        print(f"  {label:<22} {ev['precision@1']:>9.0%}   {ev['hits']}/{ev['total']}")

    # ── Show a specific improvement case ───────────────────────────────────────
    print(f"\n[4] Case study — vocabulary mismatch:")
    case_q, case_exp = TEST_QUERIES[0]  # "share tool capabilities across frameworks"
    print(f"  Query: {case_q!r}")
    print(f"  Expected: {case_exp}")
    r = approach_results[case_q]

    print(f"\n  Raw top-1:  [{r['raw'][0]['section']}] sim={r['raw'][0]['sim']} | {r['raw'][0]['text'][:70]!r}")
    print(f"  HyDE top-1: [{r['hyde'][0]['section']}] sim={r['hyde'][0]['sim']} | {r['hyde'][0]['text'][:70]!r}")

    print(f"""
[5] Key concepts:

  HyDE — embed hypothetical answer, not the question:
    Question space and document space are different embeddings.
    A short hypothetical answer resembles real document text much
    more closely than the question phrasing does.
    Best for: vocabulary mismatch, technical jargon gaps.

  Query expansion — paraphrase + RRF merge:
    RRF score = Σ 1/(60 + rank_i) across all result lists.
    Sections that rank highly across multiple phrasings score highest.
    Best for: semantic sparsity, queries with many valid phrasings.

  RRF (k=60):
    Standard constant. Lower k → higher reward for top ranks.
    Robust to variation in individual list quality.
    Does NOT require calibrated similarity scores across lists —
    only relative rank matters. Safe to combine any retrievers.

  When to use:
    HyDE       → when query vocab ≠ document vocab
    Expansion  → when one phrasing might miss, many phrasings cover
    HyDE+Exp   → production default; marginal cost, consistent gains
    """)

    print("[cleanup]...")
    try:
        s3v.delete_index(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME)
        s3v.delete_vector_bucket(vectorBucketName=BUCKET_NAME)
        print("  done")
    except Exception as e:
        print(f"  {e}")

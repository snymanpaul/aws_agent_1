"""
Level 45g: Hybrid Search — Semantic + BM25 Keyword + RRF

Semantic search finds meaning. Keyword search finds exact terms.
Neither alone covers all queries:

  Semantic misses:  "callback_handler=None" (exact param name)
                    "BedrockAgentCoreApp" (proper noun/class name)
                    "POST /invocations" (URL pattern)
                    "port 8080" (specific number)
                    Version strings, error codes, API names

  Keyword misses:   "How do I suppress agent output?" (no keyword overlap)
                    "What handles model routing?" (synonym of "LiteLLM proxy")
                    Vocabulary mismatch — different words, same meaning

  Hybrid covers both:
    semantic_results + keyword_results → RRF merge → best of both worlds

BM25 (Best Match 25):
  Classic IR scoring function. Counts term frequency (TF) with saturation
  (more occurrences help but with diminishing returns) and inverse document
  frequency (IDF — rare terms score higher than common terms).
  Pure Python, no additional service needed.

RRF (Reciprocal Rank Fusion):
  score = Σ 1/(k + rank_i) across retriever outputs.
  k=60 is the standard constant.
  Only uses RANK — does not require calibrated scores between retrievers.
  Safe to combine semantic (cosine distance) and lexical (BM25) scores.
"""
import json
import re
import math
import boto3
import hashlib
from collections import defaultdict
from strands import Agent
from tools import get_model

REGION         = "us-east-1"
BUCKET_NAME    = "strands-hybrid-l45g"
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


# ── Corpus ─────────────────────────────────────────────────────────────────────

CORPUS = [
    {"doc": "Strands SDK Guide", "sections": [
        {"section": "Agent Class",
         "text": "The Agent class manages tool orchestration and conversation history. "
                 "Create with Agent(model=model, tools=[...], callback_handler=None). "
                 "Agents are stateful — conversation turns accumulate in agent.messages."},
        {"section": "Tool System",
         "text": "Use @tool decorator for native Python tools. "
                 "MCPClient(lambda: stdio_client(params)) for MCP servers. "
                 "Set prefix='name_' when mounting multiple MCP servers to avoid collisions."},
        {"section": "Short-term Memory",
         "text": "Set callback_handler=None to disable streaming. "
                 "History accessible via agent.messages. "
                 "Session-scoped — cleared when process exits."},
        {"section": "Long-term Memory",
         "text": "create_memory_store() creates a persistent store. "
                 "Pass save_memory_tool and retrieve_memories_tool to Agent. "
                 "Semantic consolidation deduplicates memories across sessions."},
        {"section": "Production Deployment",
         "text": "BedrockAgentCoreApp requires POST /invocations and GET /ping on port 8080. "
                 "Push Docker image to ECR. Register agent with AWS AgentCore. "
                 "Lambda: instantiate Agent per request — not thread-safe."},
        {"section": "Error Recovery",
         "text": "Wrap in try/except for ThrottlingException and ServiceUnavailableException. "
                 "Exponential backoff: wait 2^n seconds between retries. "
                 "Circuit breaker pattern prevents cascade failures."},
        {"section": "Observability",
         "text": "Emit tool_call_count, tool_latency_ms, token_usage_input, token_usage_output. "
                 "Use CloudWatch Metrics for production monitoring. "
                 "Trace with AWS X-Ray for end-to-end latency across agent chains."},
    ]},
]


# ── BM25 implementation (pure Python, no external libraries) ──────────────────

class BM25:
    """
    BM25 scoring. k1=1.5 (term frequency saturation), b=0.75 (length normalisation).
    Standard values that work well across most document collections.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b  = b
        self.docs: list[dict] = []   # [{tokens, section, text}]
        self.idf: dict[str, float] = {}
        self.avg_dl: float = 0.0

    def tokenize(self, text: str) -> list[str]:
        # Lowercase, split on non-alphanumeric, keep numbers
        tokens = re.findall(r'[a-z0-9_/]+', text.lower())
        return tokens

    def index(self, documents: list[dict]):
        """documents: list of {section, text}"""
        self.docs = []
        for doc in documents:
            tokens = self.tokenize(doc["text"])
            self.docs.append({**doc, "tokens": tokens, "tf": self._tf(tokens)})

        # Average document length
        self.avg_dl = sum(len(d["tokens"]) for d in self.docs) / len(self.docs)

        # IDF: log((N - df + 0.5) / (df + 0.5) + 1)
        df: dict[str, int] = defaultdict(int)
        N = len(self.docs)
        for doc in self.docs:
            for tok in set(doc["tokens"]):
                df[tok] += 1
        self.idf = {
            tok: math.log((N - freq + 0.5) / (freq + 0.5) + 1)
            for tok, freq in df.items()
        }

    def _tf(self, tokens: list[str]) -> dict[str, int]:
        tf: dict[str, int] = defaultdict(int)
        for t in tokens:
            tf[t] += 1
        return dict(tf)

    def query(self, question: str, top_k: int = 5) -> list[dict]:
        q_tokens = self.tokenize(question)
        scores = []
        for doc in self.docs:
            dl = len(doc["tokens"])
            score = 0.0
            for qt in q_tokens:
                if qt not in self.idf:
                    continue
                tf = doc["tf"].get(qt, 0)
                idf = self.idf[qt]
                # BM25 formula
                num   = tf * (self.k1 + 1)
                denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avg_dl)
                score += idf * (num / denom)
            scores.append({"section": doc["section"], "text": doc["text"],
                           "bm25_score": round(score, 4)})
        scores.sort(key=lambda x: x["bm25_score"], reverse=True)
        for i, s in enumerate(scores):
            s["rank"] = i + 1
        return scores[:top_k]


# ── S3 Vectors setup ──────────────────────────────────────────────────────────

_bm25 = BM25()  # module-level BM25 instance

def setup():
    try:
        s3v.get_vector_bucket(vectorBucketName=BUCKET_NAME)
    except s3v.exceptions.NotFoundException:
        s3v.create_vector_bucket(vectorBucketName=BUCKET_NAME)

    try:
        s3v.get_index(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME)
        print("  [ok] index already exists")
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
                sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', sec["text"])
                         if len(s.strip()) >= 20]
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
        print(f"  [ingested] {len(vectors)} chunks (semantic index)")

    # Build BM25 index over full section texts (coarser units for keyword search)
    docs_for_bm25 = [
        {"section": sec["section"], "text": sec["text"]}
        for doc in CORPUS for sec in doc["sections"]
    ]
    _bm25.index(docs_for_bm25)
    print(f"  [bm25] indexed {len(docs_for_bm25)} sections")


# ── Retrieval functions ────────────────────────────────────────────────────────

def semantic_retrieve(question: str, top_k: int = 5) -> list[dict]:
    qv = embed(question)
    results = s3v.query_vectors(
        vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME,
        topK=top_k, queryVector={"float32": qv},
        returnMetadata=True, returnDistance=True,
    ).get("vectors", [])
    seen_sections: set[str] = set()
    deduped = []
    for i, r in enumerate(results):
        sec = r["metadata"]["section"]
        if sec not in seen_sections:
            seen_sections.add(sec)
            deduped.append({
                "section": sec, "text": r["metadata"]["text"],
                "sim": round(1 - r.get("distance", 1), 4), "rank": len(deduped) + 1,
            })
    return deduped


def keyword_retrieve(question: str, top_k: int = 5) -> list[dict]:
    return _bm25.query(question, top_k=top_k)


def rrf_merge(lists: list[list[dict]], k: int = 60) -> list[dict]:
    scores: dict[str, float] = {}
    best: dict[str, dict]    = {}
    for lst in lists:
        for item in lst:
            sec = item["section"]
            scores[sec] = scores.get(sec, 0) + 1 / (k + item["rank"])
            if sec not in best:
                best[sec] = item
    ranked = sorted(scores, key=lambda s: scores[s], reverse=True)
    return [{"section": s, "text": best[s]["text"],
             "rrf_score": round(scores[s], 5)} for s in ranked]


def hybrid_retrieve(question: str, top_k: int = 3) -> list[dict]:
    sem = semantic_retrieve(question, top_k=top_k + 2)
    kw  = keyword_retrieve(question, top_k=top_k + 2)
    return rrf_merge([sem, kw])[:top_k]


# ── Test queries — chosen to expose each retriever's blind spots ───────────────

# (question, expected_section, why_it_challenges_one_retriever)
TEST_QUERIES = [
    # Semantic challenge: proper noun, exact class name
    ("How do I use BedrockAgentCoreApp?",
     "Production Deployment",
     "exact class name — keyword wins"),
    # Keyword challenge: synonym-heavy, no keyword overlap
    ("How do I make my agent remember things across different conversations?",
     "Long-term Memory",
     "no direct keyword overlap — semantic wins"),
    # Semantic challenge: exact parameter name
    ("What is the callback_handler parameter for?",
     "Short-term Memory",
     "exact param name — keyword wins"),
    # Keyword challenge: paraphrase
    ("How do I monitor my agent in production?",
     "Observability",
     "semantic covers 'monitor' ↔ 'observability'"),
    # Both needed: exact exception names + semantic
    ("How do I handle ThrottlingException?",
     "Error Recovery",
     "exact exception class name — keyword wins"),
    # Both needed: URL pattern + context
    ("What endpoints must my agent expose on port 8080?",
     "Production Deployment",
     "exact URL patterns — keyword wins"),
    # Semantic only: no keyword overlap
    ("How do I stop token-by-token output?",
     "Short-term Memory",
     "semantic: 'stop output' ↔ 'callback_handler=None'"),
    # Both needed: MCPClient exact name + context
    ("Show me how to instantiate MCPClient.",
     "Tool System",
     "exact class name — keyword wins"),
]


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("L45g: Hybrid Search — Semantic + BM25 + RRF")
    print("=" * 60)

    print("\n[1] Setting up indexes...")
    setup()

    print(f"\n[2] Per-query top-1 — semantic vs keyword vs hybrid:")
    print(f"\n  {'Query':<44} {'Expected':<22} {'Sem':>4} {'KW':>4} {'Hyb':>4}")
    print(f"  {'-'*44} {'-'*22} {'-'*4} {'-'*4} {'-'*4}")

    sem_hits = kw_hits = hyb_hits = 0

    for q, expected, why in TEST_QUERIES:
        sem_r  = semantic_retrieve(q, top_k=3)
        kw_r   = keyword_retrieve(q, top_k=3)
        hyb_r  = hybrid_retrieve(q, top_k=3)

        def mark(results):
            return "✓" if results and results[0]["section"] == expected else "✗"

        s_hit = sem_r and sem_r[0]["section"] == expected
        k_hit = kw_r  and kw_r[0]["section"]  == expected
        h_hit = hyb_r and hyb_r[0]["section"] == expected

        if s_hit: sem_hits += 1
        if k_hit: kw_hits  += 1
        if h_hit: hyb_hits += 1

        # Flag cases where hybrid fixes a failure
        fixed = " ← hybrid wins" if h_hit and (not s_hit or not k_hit) else ""
        print(f"  {q[:43]:<44} {expected:<22} {mark(sem_r):>4} {mark(kw_r):>4} {mark(hyb_r):>4}{fixed}")

    total = len(TEST_QUERIES)
    print(f"\n[3] Precision@1 summary:")
    print(f"  Semantic:  {sem_hits}/{total} = {sem_hits/total:.0%}")
    print(f"  Keyword:   {kw_hits}/{total}  = {kw_hits/total:.0%}")
    print(f"  Hybrid:    {hyb_hits}/{total} = {hyb_hits/total:.0%}")

    # ── Show one case where each retriever fails and hybrid saves ─────────────
    print(f"\n[4] Case studies:")

    # Find a case where keyword wins but semantic fails
    for q, expected, why in TEST_QUERIES:
        sem_r = semantic_retrieve(q, top_k=3)
        kw_r  = keyword_retrieve(q, top_k=3)
        hyb_r = hybrid_retrieve(q, top_k=3)
        sem_hit = sem_r and sem_r[0]["section"] == expected
        kw_hit  = kw_r  and kw_r[0]["section"]  == expected
        if kw_hit and not sem_hit:
            print(f"\n  KEYWORD wins, SEMANTIC misses ({why}):")
            print(f"  Query: {q!r}")
            print(f"  Semantic top-1: [{sem_r[0]['section']}] sim={sem_r[0]['sim']:.4f}")
            print(f"  Keyword top-1:  [{kw_r[0]['section']}]  bm25={kw_r[0]['bm25_score']:.4f}")
            print(f"  Hybrid  top-1:  [{hyb_r[0]['section']}]  rrf={hyb_r[0]['rrf_score']:.5f}")
            break

    for q, expected, why in TEST_QUERIES:
        sem_r = semantic_retrieve(q, top_k=3)
        kw_r  = keyword_retrieve(q, top_k=3)
        hyb_r = hybrid_retrieve(q, top_k=3)
        sem_hit = sem_r and sem_r[0]["section"] == expected
        kw_hit  = kw_r  and kw_r[0]["section"]  == expected
        if sem_hit and not kw_hit:
            print(f"\n  SEMANTIC wins, KEYWORD misses ({why}):")
            print(f"  Query: {q!r}")
            print(f"  Semantic top-1: [{sem_r[0]['section']}] sim={sem_r[0]['sim']:.4f}")
            print(f"  Keyword top-1:  [{kw_r[0]['section']}]  bm25={kw_r[0]['bm25_score']:.4f}")
            print(f"  Hybrid  top-1:  [{hyb_r[0]['section']}]  rrf={hyb_r[0]['rrf_score']:.5f}")
            break

    print(f"""
[5] Key concepts:

  BM25 parameters:
    k1=1.5: TF saturation. Repeated terms help but with diminishing returns.
    b=0.75: Length normalisation. Long docs don't dominate just from word count.
    IDF: rare terms (class names, error codes) score higher than common words.

  Why RRF over score fusion (weighted sum):
    Semantic similarity and BM25 scores are NOT on the same scale.
    Normalising them requires calibration — brittle, query-dependent.
    RRF uses only RANK, which is always 1..N for any retriever.
    k=60: a chunk at rank 1 scores 1/61 ≈ 0.016; at rank 10 scores 1/70 ≈ 0.014.
    The gap between ranks 1 and 10 is small — RRF is robust to noisy retrievers.

  BM25 corpus grain:
    Here BM25 indexes full sections (coarser), semantic indexes sentences (finer).
    This is intentional: BM25 benefits from more term context per unit.
    In production, index the same chunks in both for an exact apples/apples comparison.

  Hybrid retrieval is the production default:
    Exact terms (API names, params, error codes) → keyword handles it.
    Semantic paraphrases and synonyms → semantic handles it.
    Combined via RRF → neither failure mode dominates.
    """)

    print("[cleanup]...")
    try:
        s3v.delete_index(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME)
        s3v.delete_vector_bucket(vectorBucketName=BUCKET_NAME)
        print("  done")
    except Exception as e:
        print(f"  {e}")

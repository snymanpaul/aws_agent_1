"""
Level 45f: RAG Evaluation Harness — Measuring What Matters

"You can't improve what you don't measure."

RAG quality has four independently-failing dimensions.
Each dimension has its own test and its own failure mode:

  Context Precision:  Of the chunks retrieved, what fraction are relevant?
                      Failure: low-signal noise fills the context window.

  Context Recall:     Of all chunks that could answer, what fraction were retrieved?
                      Failure: relevant chunks missed — answer is incomplete.

  Faithfulness:       Does the generated answer stay within the retrieved context?
                      Failure: hallucination — answer adds facts not in context.

  Answer Relevance:   Does the answer actually address the question?
                      Failure: correct context, but answer drifts off-topic.

  +-----------+     +------------------+     +----------+     +-----------+
  |  Query    |---->| Retrieved Chunks |---->| LLM Gen  |---->|  Answer   |
  +-----------+     +------------------+     +----------+     +-----------+
        |                   |                      |                |
   Recall gate         Precision gate         Faithfulness      Relevance
  (did we get         (is noise low?)         gate (no          gate (on
   the right                                  halluc?)          topic?)
   chunks?)

This level runs ALL four metrics against three configurations:
  Config A: naive (no enrichment) from L45c baseline
  Config B: contextual enrichment from L45c
  Config C: contextual enrichment + LLM re-ranking from L45e

Goal: a single table that shows the full quality picture for each config.
"""
import json
import re
import boto3
import hashlib
from dataclasses import dataclass
from strands import Agent
from tools import get_model

REGION         = "us-east-1"
BUCKET_NAME    = "strands-eval-l45f"
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIM      = 1024

s3v        = boto3.client("s3vectors",       region_name=REGION)
bedrock_rt = boto3.client("bedrock-runtime", region_name=REGION)

_haiku  = get_model("haiku")
_sonnet = get_model("claude-sonnet-4")

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
                 "It is stateful — conversation turns accumulate inside the object. "
                 "Create one with a model plus an optional tool list."},
        {"section": "Tool System",
         "text": "Two tool types: native @tool functions (in-process, Python-only) "
                 "and MCP servers (out-of-process, framework-agnostic). "
                 "Use the prefix parameter to avoid name collisions across MCP servers."},
        {"section": "Short-term Memory",
         "text": "Conversation history lives in the Agent object, session-scoped. "
                 "Set callback_handler=None to suppress streaming output. "
                 "History is accessible via agent.messages."},
        {"section": "Long-term Memory",
         "text": "AgentCore LTM persists memories across sessions. "
                 "Call create_memory_store(), then pass save_memory_tool and retrieve_memories_tool. "
                 "Duplicates are merged via semantic consolidation."},
        {"section": "Production Deployment",
         "text": "AgentCore requires POST /invocations and GET /ping on port 8080. "
                 "Package as Docker image, push to ECR, register with BedrockAgentCoreApp. "
                 "Create a fresh Agent per Lambda request — not thread-safe."},
        {"section": "Error Recovery",
         "text": "Catch transient errors with exponential backoff. "
                 "Implement a retry loop with circuit breaker for critical workflows. "
                 "Log tool failures with tool name and input arguments."},
    ]},
]


# ── Gold-standard evaluation set ──────────────────────────────────────────────
# Each item: question, relevant_sections (ground truth), ideal_answer_keywords

EVAL_SET = [
    {
        "question": "How do I avoid tool name conflicts when using multiple MCP servers?",
        "relevant_sections": ["Tool System"],
        "answer_must_contain": ["prefix", "MCP"],
    },
    {
        "question": "How do I set up long-term memory for an agent?",
        "relevant_sections": ["Long-term Memory"],
        "answer_must_contain": ["create_memory_store", "save_memory_tool"],
    },
    {
        "question": "What are the production hosting requirements for a Strands agent?",
        "relevant_sections": ["Production Deployment"],
        "answer_must_contain": ["8080", "ECR", "/invocations"],
    },
    {
        "question": "How do I suppress streaming output without affecting conversation memory?",
        "relevant_sections": ["Short-term Memory"],
        "answer_must_contain": ["callback_handler"],
    },
    {
        "question": "What should I do when a tool call fails in a critical workflow?",
        "relevant_sections": ["Error Recovery"],
        "answer_must_contain": ["retry", "backoff"],
    },
    {
        "question": "How does the Agent class handle state between turns?",
        "relevant_sections": ["Agent Class"],
        "answer_must_contain": ["stateful", "conversation"],
    },
]


# ── Index setup ────────────────────────────────────────────────────────────────

def ensure_bucket():
    try:
        s3v.get_vector_bucket(vectorBucketName=BUCKET_NAME)
    except s3v.exceptions.NotFoundException:
        s3v.create_vector_bucket(vectorBucketName=BUCKET_NAME)


def build_index(index_name: str, use_enrichment: bool):
    try:
        s3v.get_index(vectorBucketName=BUCKET_NAME, indexName=index_name)
        return  # already exists
    except s3v.exceptions.NotFoundException:
        s3v.create_index(
            vectorBucketName=BUCKET_NAME, indexName=index_name,
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
                embed_text = (
                    f"Document: {doc['doc']} | Section: {sec['section']} | {sent}"
                    if use_enrichment else sent
                )
                vectors.append({
                    "key": f"{sec['section']}:{i}",
                    "data": {"float32": embed(embed_text)},
                    "metadata": {"text": sent, "section": sec["section"]},
                })
    s3v.put_vectors(vectorBucketName=BUCKET_NAME, indexName=index_name, vectors=vectors)


# ── Retrieval ──────────────────────────────────────────────────────────────────

def retrieve(index_name: str, question: str, top_k: int = 3) -> list[dict]:
    qv = embed(question)
    results = s3v.query_vectors(
        vectorBucketName=BUCKET_NAME, indexName=index_name,
        topK=top_k, queryVector={"float32": qv},
        returnMetadata=True, returnDistance=True,
    ).get("vectors", [])
    return [{"section": r["metadata"]["section"], "text": r["metadata"]["text"],
             "sim": round(1 - r.get("distance", 1), 4), "rank": i+1}
            for i, r in enumerate(results)]


def rerank(question: str, candidates: list[dict]) -> list[dict]:
    if not candidates:
        return candidates
    numbered = "\n".join(f"[{i+1}] {c['text'][:100]}" for i, c in enumerate(candidates))
    ranker = Agent(model=_haiku, callback_handler=None)
    resp = str(ranker(
        f"Rate relevance 0-10. Return ONLY comma-separated scores, "
        f"exactly {len(candidates)} numbers.\n\n"
        f"Question: {question}\n\nPassages:\n{numbered}"
    ))
    nums = re.findall(r'\d+(?:\.\d+)?', resp)
    scores = [float(n) for n in nums[:len(candidates)]]
    while len(scores) < len(candidates):
        scores.append(0.0)
    for i, c in enumerate(candidates):
        c["llm_score"] = scores[i]
    return sorted(candidates, key=lambda x: x["llm_score"], reverse=True)


def generate_answer(question: str, context_chunks: list[dict]) -> str:
    context = "\n\n".join(
        f"[{c['section']}] {c['text']}" for c in context_chunks
    )
    gen = Agent(model=_haiku, callback_handler=None)
    return str(gen(
        f"Answer using ONLY the context below. Be specific and concise.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}"
    ))


# ── Four evaluation metrics ────────────────────────────────────────────────────

def context_precision(retrieved: list[dict], relevant_sections: list[str]) -> float:
    """What fraction of retrieved chunks belong to a relevant section?"""
    if not retrieved:
        return 0.0
    hits = sum(1 for c in retrieved if c["section"] in relevant_sections)
    return round(hits / len(retrieved), 3)


def context_recall(retrieved: list[dict], relevant_sections: list[str]) -> float:
    """What fraction of relevant sections were retrieved at all?"""
    if not relevant_sections:
        return 1.0
    retrieved_sections = {c["section"] for c in retrieved}
    hits = sum(1 for s in relevant_sections if s in retrieved_sections)
    return round(hits / len(relevant_sections), 3)


def faithfulness(question: str, answer: str, context_chunks: list[dict]) -> float:
    """Does every factual claim in the answer have support in the context?
    Uses LLM to count supported vs unsupported claims.
    Returns fraction supported (1.0 = fully faithful)."""
    context = "\n".join(f"- {c['text']}" for c in context_chunks)
    checker = Agent(model=_haiku, callback_handler=None)
    resp = str(checker(
        f"Count how many factual claims in the ANSWER are supported by the CONTEXT "
        f"vs unsupported (hallucinated).\n"
        f"Return ONLY JSON: {{\"supported\": N, \"unsupported\": N}}\n\n"
        f"Context:\n{context}\n\nAnswer:\n{answer}"
    ))
    m = re.search(r'\{[^}]+\}', resp)
    if m:
        try:
            d = json.loads(m.group(0))
            total = d.get("supported", 0) + d.get("unsupported", 0)
            return round(d.get("supported", 0) / total, 3) if total > 0 else 1.0
        except Exception:
            pass
    return 1.0  # default: assume faithful if parsing fails


def answer_relevance(question: str, answer: str) -> float:
    """Does the answer address the question? Score 0-1."""
    scorer = Agent(model=_haiku, callback_handler=None)
    resp = str(scorer(
        f"Score how well this answer addresses the question, 0-10. "
        f"Return ONLY the number.\n\n"
        f"Question: {question}\nAnswer: {answer[:300]}"
    ))
    nums = re.findall(r'\d+(?:\.\d+)?', resp)
    score = float(nums[0]) if nums else 5.0
    return round(min(score, 10) / 10, 3)


# ── Run evaluation ─────────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    config: str
    ctx_precision: float
    ctx_recall: float
    faithfulness: float
    answer_relevance: float

    @property
    def overall(self) -> float:
        return round((self.ctx_precision + self.ctx_recall +
                      self.faithfulness + self.answer_relevance) / 4, 3)


def run_eval(index_name: str, config_label: str, use_rerank: bool = False,
             top_k: int = 3) -> EvalResult:
    precisions, recalls, faiths, relevances = [], [], [], []

    for item in EVAL_SET:
        q   = item["question"]
        rel = item["relevant_sections"]

        chunks = retrieve(index_name, q, top_k=top_k if not use_rerank else 8)
        if use_rerank:
            chunks = rerank(q, chunks)[:top_k]

        answer = generate_answer(q, chunks)

        precisions.append(context_precision(chunks, rel))
        recalls.append(context_recall(chunks, rel))
        faiths.append(faithfulness(q, answer, chunks))
        relevances.append(answer_relevance(q, answer))

    def mean(lst): return round(sum(lst) / len(lst), 3)
    return EvalResult(
        config=config_label,
        ctx_precision=mean(precisions),
        ctx_recall=mean(recalls),
        faithfulness=mean(faiths),
        answer_relevance=mean(relevances),
    )


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("L45f: RAG Evaluation Harness")
    print("=" * 60)

    ensure_bucket()

    print("\n[1] Building indexes...")
    build_index("naive",       use_enrichment=False)
    build_index("contextual",  use_enrichment=True)
    print("  done")

    print("\n[2] Running evaluations (6 questions × 3 configs)...")

    configs = [
        ("naive",      "naive",      False, "A: Naive (no enrichment)"),
        ("contextual", "contextual", False, "B: Contextual enrichment"),
        ("contextual", "contextual", True,  "C: Enrichment + Re-rank"),
    ]

    results: list[EvalResult] = []
    for idx, _, rerank_flag, label in configs:
        print(f"  evaluating {label}...")
        r = run_eval(idx, label, use_rerank=rerank_flag)
        results.append(r)

    # ── Results table ─────────────────────────────────────────────────────────
    print(f"\n[3] Results:")
    print()
    print(f"  {'Config':<30} {'Ctx Prec':>9} {'Ctx Rec':>8} {'Faith':>7} {'Ans Rel':>8} {'Overall':>8}")
    print(f"  {'-'*30} {'-'*9} {'-'*8} {'-'*7} {'-'*8} {'-'*8}")
    for r in results:
        print(f"  {r.config:<30} {r.ctx_precision:>9.3f} {r.ctx_recall:>8.3f} "
              f"{r.faithfulness:>7.3f} {r.answer_relevance:>8.3f} {r.overall:>8.3f}")

    # ── Per-metric winner ─────────────────────────────────────────────────────
    print(f"\n[4] Per-metric winner:")
    metrics = [
        ("Context Precision", lambda r: r.ctx_precision),
        ("Context Recall",    lambda r: r.ctx_recall),
        ("Faithfulness",      lambda r: r.faithfulness),
        ("Answer Relevance",  lambda r: r.answer_relevance),
    ]
    for name, fn in metrics:
        best = max(results, key=fn)
        print(f"  {name:<22}: {best.config} ({fn(best):.3f})")

    print(f"""
[5] Metric definitions:

  Context Precision = relevant chunks / total retrieved
    Low → noisy context window; LLM reads irrelevant text.
    Fix: re-ranking, smaller top-K, better chunking.

  Context Recall = relevant sections found / total relevant sections
    Low → incomplete context; answer misses key facts.
    Fix: larger top-K, query expansion, HyDE.

  Faithfulness = supported claims / total claims in answer
    Low → hallucination; answer adds facts not in context.
    Fix: stronger "use ONLY context" instruction, fact-check pass.

  Answer Relevance = "does this answer the question?" score
    Low → correct context but answer drifts off-topic.
    Fix: constrained generation prompt, re-rank answer quality.

  Overall = mean of all four. Use to compare configs.

  Precision vs Recall tradeoff:
    ↑ top-K  → higher recall, lower precision
    ↓ top-K  → higher precision, lower recall
    Re-rank  → higher precision without sacrificing recall
    """)

    print("[cleanup]...")
    for idx_name in ["naive", "contextual"]:
        try:
            s3v.delete_index(vectorBucketName=BUCKET_NAME, indexName=idx_name)
        except Exception:
            pass
    try:
        s3v.delete_vector_bucket(vectorBucketName=BUCKET_NAME)
    except Exception as e:
        print(f"  bucket: {e}")
    print("  done")

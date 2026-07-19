"""
Level 45 (iter 2): Agentic RAG — Iterative Retrieval with Self-Evaluation

Naive RAG:   embed(question) → retrieve(topK=3) → answer
             One shot. No awareness of gaps. Misses cross-cutting topics.

Agentic RAG: Agent decides WHEN to retrieve, WHAT to retrieve, WHETHER
             enough was retrieved, then reformulates + searches again.

             The agent is the retrieval loop controller.

What this level adds over iter 1:
  - Larger KB: 14 docs spanning 7 topics with cross-topic references
  - Side-by-side comparison: naive vs agentic on same complex questions
  - evaluate_context tool: agent self-assesses sufficiency before answering
  - Multi-hop: question about X surfaces entity → second query about that entity
  - Search count + answer quality metrics

Why this matters:
  A question like "How does Strands handle multi-agent coordination and what
  are the tradeoffs between MCP tools and native @tool functions in production?"
  spans 3 topics. Naive RAG retrieves 3 docs, might hit only 1-2 topics.
  Agentic RAG searches 3 times (multi-agent, mcp, tools), merges context,
  and produces an answer that addresses all parts.
"""
import json
import time
import boto3
from dataclasses import dataclass, field
from strands import Agent, tool
from strands.models.openai import OpenAIModel
from tools import get_model

# ── AWS setup ─────────────────────────────────────────────────────────────────

REGION         = "us-east-1"
BUCKET_NAME    = "strands-kb-l45adv"
INDEX_NAME     = "docs-index"
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIM      = 1024

s3v        = boto3.client("s3vectors",     region_name=REGION)
bedrock_rt = boto3.client("bedrock-runtime", region_name=REGION)


def embed(text: str) -> list[float]:
    body = json.dumps({"inputText": text, "dimensions": EMBED_DIM, "normalize": True})
    resp = bedrock_rt.invoke_model(modelId=EMBED_MODEL_ID, body=body)
    return json.loads(resp["body"].read())["embedding"]


# ── Richer knowledge base — cross-topic references ────────────────────────────

DOCUMENTS = [
    # tools
    {"key": "t1", "topic": "tools", "text":
     "The @tool decorator converts any Python function into an agent tool. "
     "The docstring becomes the tool description, type hints define the schema. "
     "Native @tool functions run in-process — low latency, full Python access, "
     "direct access to AWS SDKs and local state."},
    {"key": "t2", "topic": "tools", "text":
     "MCP (Model Context Protocol) tools are out-of-process servers that expose "
     "capabilities over stdio or SSE. Use MCPClient with a lambda returning "
     "stdio_client or sse_client. MCP tools are language-agnostic and "
     "reusable across different agent frameworks, not just Strands."},
    {"key": "t3", "topic": "tools", "text":
     "Tradeoffs between @tool and MCP: native @tool has lower latency (in-process) "
     "but is Python-only and coupled to the agent codebase. MCP tools are portable "
     "across frameworks, can be versioned/deployed independently, but add "
     "serialization overhead and a subprocess boundary."},

    # multi-agent
    {"key": "m1", "topic": "multi-agent", "text":
     "Agents-as-tools: wrap a Strands Agent in a @tool function and pass it to "
     "another Agent. The outer (orchestrator) agent delegates subtasks to inner "
     "(specialist) agents. This is the primary multi-agent pattern in Strands."},
    {"key": "m2", "topic": "multi-agent", "text":
     "The Swarm pattern runs multiple agents in parallel on the same task. "
     "Use Swarm([a1, a2, ...]) with positional args. Set "
     "repetitive_handoff_detection_window to prevent ping-pong loops between agents."},
    {"key": "m3", "topic": "multi-agent", "text":
     "Graph-based orchestration (GraphAgent) models multi-agent workflows as a "
     "directed graph: nodes are agents or tools, edges are data dependencies. "
     "Supports conditional branching and parallel branches. More explicit control "
     "than swarm but more setup."},

    # deployment
    {"key": "d1", "topic": "deployment", "text":
     "AgentCore is AWS's managed hosting for Strands agents. Use BedrockAgentCoreApp. "
     "Requires POST /invocations and GET /ping on port 8080. Deploy by pushing "
     "a Docker image to ECR then registering the agent. Auto-scales to zero."},
    {"key": "d2", "topic": "deployment", "text":
     "AG-UI enables Strands agents to stream state to web frontends via SSE. "
     "create_strands_app() wraps an agent in FastAPI with /invocations and /ping. "
     "Compatible with CopilotKit React components. Emits typed events: "
     "RUN_STARTED, TOOL_CALL_START, TEXT_MESSAGE_CONTENT, STATE_SNAPSHOT."},
    {"key": "d3", "topic": "deployment", "text":
     "Thread safety: Strands Agent objects are NOT thread-safe. In parallel workloads "
     "(async, multi-thread), create a fresh Agent instance per thread or request. "
     "For AWS Lambda, create the Agent inside the handler function, not at module level."},

    # memory
    {"key": "mem1", "topic": "memory", "text":
     "AgentCore Long-Term Memory (LTM) persists facts across sessions. "
     "create_memory_store() creates a named store. The agent uses save_memory_tool "
     "and retrieve_memories_tool. Memories are consolidated semantically — "
     "similar facts are merged rather than duplicated."},
    {"key": "mem2", "topic": "memory", "text":
     "S3 Vectors provides durable vector storage for RAG knowledge bases. "
     "Unlike in-memory Chroma, S3 Vectors persists across Lambda cold starts "
     "and agent restarts. Pair with Titan v2 embeddings (1024-dim, cosine). "
     "Metadata filtering lets agents scope retrieval to specific topics or sources."},

    # patterns
    {"key": "p1", "topic": "patterns", "text":
     "Reflexion loop: attempt → evaluate (pure Python or LLM) → reflect → retry. "
     "Accumulate reflection_context between rounds. Stop on score threshold "
     "or retry budget. The evaluator MUST be deterministic (same input, same score) "
     "or the loop is non-convergent."},
    {"key": "p2", "topic": "patterns", "text":
     "SOPs (Standard Operating Procedures) are markdown strings passed as system_prompt. "
     "Use RFC 2119 language: MUST = required, SHOULD = strong preference, MAY = optional. "
     "Pure-Python regex checks MUST compliance — no LLM cost. "
     "SOPs are human-readable Reflexion exit criteria."},

    # safety
    {"key": "s1", "topic": "safety", "text":
     "Strands safety layer: use a guard agent that inspects tool calls before execution. "
     "Deny-list patterns block dangerous commands (rm -rf, DROP TABLE). "
     "Rate limiting prevents runaway tool loops. Safety checks should be in a "
     "separate agent to avoid prompt-injection from the primary task."},
]


# ── Infrastructure setup (idempotent) ─────────────────────────────────────────

def ensure_infra():
    try:
        s3v.get_vector_bucket(vectorBucketName=BUCKET_NAME)
    except s3v.exceptions.NotFoundException:
        s3v.create_vector_bucket(vectorBucketName=BUCKET_NAME)
        print(f"  [created] bucket")

    try:
        s3v.get_index(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME)
    except s3v.exceptions.NotFoundException:
        s3v.create_index(
            vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME,
            dataType="float32", dimension=EMBED_DIM, distanceMetric="cosine",
            metadataConfiguration={"nonFilterableMetadataKeys": ["text"]},
        )
        print(f"  [created] index ({EMBED_DIM}d cosine)")


def ingest(docs: list[dict]):
    keys = [d["key"] for d in docs]
    try:
        existing_resp = s3v.get_vectors(
            vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME,
            keys=keys, returnData=False, returnMetadata=False,
        )
        existing = {v["key"] for v in existing_resp.get("vectors", []) if "error" not in v}
    except Exception:
        existing = set()

    to_add = [d for d in docs if d["key"] not in existing]
    if not to_add:
        print(f"  [ok] all {len(docs)} docs already ingested")
        return

    vectors = []
    for d in to_add:
        vectors.append({
            "key": d["key"],
            "data": {"float32": embed(d["text"])},
            "metadata": {"text": d["text"], "topic": d["topic"]},
        })
    s3v.put_vectors(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME, vectors=vectors)
    print(f"  [ingested] {len(vectors)} new docs")


# ── Retrieval primitives ───────────────────────────────────────────────────────

@dataclass
class SearchSession:
    """Accumulates search results across multiple calls — shared by tools."""
    searches: int = 0
    retrieved_texts: list[str] = field(default_factory=list)

# Module-level session — tools close over this
_session = SearchSession()

def _query_s3(question: str, topic: str = "", top_k: int = 3) -> list[dict]:
    """Core retrieval — returns list of {text, topic, similarity}."""
    vec = embed(question)
    kwargs = dict(
        vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME,
        topK=top_k, queryVector={"float32": vec},
        returnMetadata=True, returnDistance=True,
    )
    if topic:
        kwargs["filter"] = {"topic": {"$eq": topic}}
    results = s3v.query_vectors(**kwargs).get("vectors", [])
    return [
        {
            "text":       r["metadata"]["text"],
            "topic":      r["metadata"]["topic"],
            "similarity": round(1 - r.get("distance", 1), 3),
        }
        for r in results
    ]


# ── Naive RAG — single retrieval, no agent ────────────────────────────────────

def naive_rag(question: str, model) -> tuple[str, int]:
    """Embed question → retrieve topK=3 → answer in one LLM call. No tools."""
    results = _query_s3(question, top_k=3)
    context = "\n\n".join(
        f"[{r['topic']}, sim={r['similarity']}] {r['text']}" for r in results
    )
    agent = Agent(model=model, callback_handler=None)
    answer = str(agent(
        f"Answer this question using ONLY the context below:\n\n"
        f"CONTEXT:\n{context}\n\nQUESTION: {question}"
    ))
    return answer, 1  # always 1 retrieval


# ── Agentic RAG — iterative, self-evaluating agent ────────────────────────────

@tool
def search_docs(question: str, topic: str = "", top_k: int = 3) -> str:
    """
    Search the Strands knowledge base for relevant documentation.

    Args:
        question: What you want to know. Be specific — rephrase between calls
                  if first results are weak.
        topic:    Optional filter — one of: tools, multi-agent, deployment,
                  memory, patterns, safety. Leave empty to search all topics.
        top_k:    Number of results (1-5). Default 3.
    """
    global _session
    _session.searches += 1
    top_k = max(1, min(5, top_k))
    results = _query_s3(question, topic=topic, top_k=top_k)

    if not results:
        return f"No results for '{question}'" + (f" in topic '{topic}'" if topic else "")

    parts = []
    for r in results:
        _session.retrieved_texts.append(r["text"])
        parts.append(f"[{r['topic']}, sim={r['similarity']}] {r['text']}")

    return "\n\n".join(parts)


@tool
def evaluate_context(question: str, accumulated_context: str) -> str:
    """
    Evaluate whether the retrieved context is sufficient to answer the question.
    Call this after one or more search_docs calls to decide whether to search
    more or proceed to answering.

    Returns a JSON object with:
      - sufficient: bool
      - covered_aspects: list of question aspects that are answered
      - missing_aspects: list of aspects not yet covered
      - suggested_queries: follow-up search queries for missing aspects
    """
    model = get_model("haiku")  # cheap eval — no need for sonnet
    eval_agent = Agent(model=model, callback_handler=None)
    resp = str(eval_agent(
        f"Evaluate whether this context sufficiently answers the question.\n"
        f"Return ONLY valid JSON with keys: sufficient (bool), "
        f"covered_aspects (list of str), missing_aspects (list of str), "
        f"suggested_queries (list of str, empty if sufficient=true).\n\n"
        f"QUESTION: {question}\n\n"
        f"CONTEXT:\n{accumulated_context}"
    ))
    # Extract JSON from response
    import re
    m = re.search(r'\{.*\}', resp, re.DOTALL)
    return m.group(0) if m else resp


@tool
def list_topics() -> str:
    """List all available topics in the knowledge base."""
    return (
        "Topics: tools (native @tool vs MCP), multi-agent (agents-as-tools, swarm, graph), "
        "deployment (AgentCore, AG-UI, thread safety), memory (LTM, S3 Vectors), "
        "patterns (Reflexion, SOPs), safety (guard agents, rate limiting)"
    )


def build_agentic_rag_agent(model) -> Agent:
    return Agent(
        model=model,
        tools=[search_docs, evaluate_context, list_topics],
        system_prompt=(
            "You are a documentation assistant with access to a Strands knowledge base.\n"
            "For any question:\n"
            "1. Use list_topics to understand scope if the question is broad.\n"
            "2. Call search_docs at least once. For multi-part questions, search each part.\n"
            "3. Call evaluate_context to check if you have enough — if not, search again.\n"
            "4. Only answer after evaluate_context returns sufficient=true, or after 4 searches.\n"
            "5. In your answer, cite [topic, sim=X] for every claim you make."
        ),
        callback_handler=None,
    )


# ── Test questions ─────────────────────────────────────────────────────────────

QUESTIONS = [
    {
        "label": "Simple (1 topic)",
        "q": "What is the Reflexion loop and when should I use it?",
        "expected_topics": ["patterns"],
    },
    {
        "label": "Multi-part (3 topics — tools + multi-agent + deployment)",
        "q": (
            "What are the tradeoffs between native @tool functions and MCP tools, "
            "and which multi-agent coordination pattern works best for production "
            "deployments on AgentCore?"
        ),
        "expected_topics": ["tools", "multi-agent", "deployment"],
    },
    {
        "label": "Multi-hop (memory → RAG pattern surfaces S3 Vectors entity → retrieval details)",
        "q": (
            "How do I build a Strands agent whose knowledge base survives Lambda cold starts, "
            "and what embedding model should I use?"
        ),
        "expected_topics": ["memory", "deployment"],
    },
]


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("L45 (iter 2): Agentic RAG — Iterative vs Naive")
    print("=" * 60)

    # Setup
    print("\n[1] Infrastructure...")
    ensure_infra()
    print("[2] Ingesting KB...")
    ingest(DOCUMENTS)

    sonnet = get_model("claude-sonnet-4")
    haiku  = get_model("haiku")

    results_table = []

    for i, q in enumerate(QUESTIONS, 1):
        print(f"\n{'=' * 60}")
        print(f"Q{i}: {q['label']}")
        print(f"{'=' * 60}")
        print(f"  {q['q']}")
        print(f"  Expected topics: {q['expected_topics']}")

        # ── Naive RAG ─────────────────────────────────────────
        print(f"\n  --- NAIVE RAG (single retrieval, no agent) ---")
        naive_answer, naive_searches = naive_rag(q["q"], haiku)
        print(f"  Searches: {naive_searches}")
        print(f"  Answer: {naive_answer[:300]}{'...' if len(naive_answer) > 300 else ''}")

        # ── Agentic RAG ───────────────────────────────────────
        print(f"\n  --- AGENTIC RAG (iterative, self-evaluating) ---")
        _session = SearchSession()  # reset session counter
        agent = build_agentic_rag_agent(sonnet)
        agentic_answer = str(agent(q["q"]))
        agentic_searches = _session.searches
        print(f"  Searches: {agentic_searches}")
        print(f"  Answer: {agentic_answer[:400]}{'...' if len(agentic_answer) > 400 else ''}")

        results_table.append({
            "q": q["label"],
            "naive_searches":   naive_searches,
            "agentic_searches": agentic_searches,
        })

    # ── Summary table ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("RESULTS SUMMARY")
    print(f"{'=' * 60}")
    print(f"{'Question':<40} {'Naive':>7} {'Agentic':>9}")
    print(f"{'-' * 40} {'-' * 7} {'-' * 9}")
    for row in results_table:
        print(f"{row['q']:<40} {row['naive_searches']:>7} {row['agentic_searches']:>9}")

    print(f"""
KEY CONCEPTS DEMONSTRATED

  Naive RAG (single-shot):
    embed(Q) → query(topK=3) → fill context → answer
    Problem: one query can only surface one topical cluster.
    Multi-part questions get partial answers.

  Agentic RAG (iterative):
    Agent controls the retrieval loop:
      - calls search_docs once per question aspect
      - calls evaluate_context to check sufficiency
      - reformulates and searches again if gaps found
      - cites sources in final answer
    Result: better coverage for multi-part, cross-topic questions.

  Self-evaluation tool:
    evaluate_context(question, accumulated_context)
    → {{sufficient: bool, missing_aspects: [...], suggested_queries: [...]}}
    Haiku does the evaluation cheaply. If not sufficient, agent searches again.
    This is Reflexion (L42) applied to retrieval.

  Multi-hop pattern:
    Q about "Lambda cold starts" → surfaces S3 Vectors memory doc
    → agent recognises it mentions embeddings → searches "Titan embeddings"
    → assembles answer from two linked retrievals.
    """)

    # Cleanup
    print("[cleanup] Removing index and bucket...")
    try:
        s3v.delete_index(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME)
        s3v.delete_vector_bucket(vectorBucketName=BUCKET_NAME)
        print("  done")
    except Exception as e:
        print(f"  {e}")

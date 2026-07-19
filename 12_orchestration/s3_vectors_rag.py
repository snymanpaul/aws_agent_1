"""
Level 45: Agentic RAG with S3 Vectors

S3 Vectors is AWS's managed vector store — billion-scale, no infrastructure to
run, pay-per-query. This level wires it to a Strands agent to build a knowledge
base that persists across sessions and scales beyond single-machine limits.

vs L13 (ChromaDB RAG):
  L13: Local Chroma, single-machine, text only, manual persistence
  L45: S3 Vectors, AWS-managed, durable, filtereable metadata

Concepts demonstrated:
  1. Create vector bucket + index (idempotent — skip if already exists)
  2. Embed + ingest documents into S3 Vectors
  3. Strands agent with query_knowledge_base tool backed by S3 Vectors
  4. Metadata filtering (filter by topic/source in the vector query)
  5. Cross-session durability — data persists between runs

Architecture:
  Documents (text)
       |
       v embed (Titan v2, 1024-dim)
       |
       v put_vectors (S3 Vectors bucket/index)
       |
  Agent query
       |
       v embed(question) → query_vectors(topK=5) → ranked results
       |
       v synthesize answer

Knowledge base: AWS Strands Agents documentation snippets
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import boto3
import re
from strands import Agent, tool
from tools import get_model

# ── AWS clients ───────────────────────────────────────────────────────────────

REGION         = "us-east-1"
BUCKET_NAME    = "strands-kb-l45"
INDEX_NAME     = "docs-index"
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIM      = 1024

AWS_PROFILE = os.environ.get("AWS_PROFILE")
_session = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)
s3v    = _session.client("s3vectors")
bedrock_rt = _session.client("bedrock-runtime")


# ── Embedding helper ──────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    """Call Titan Text Embeddings v2 via Bedrock."""
    body = json.dumps({"inputText": text, "dimensions": EMBED_DIM, "normalize": True})
    resp = bedrock_rt.invoke_model(modelId=EMBED_MODEL_ID, body=body)
    return json.loads(resp["body"].read())["embedding"]


# ── Idempotent setup: bucket + index ─────────────────────────────────────────

def ensure_bucket_and_index():
    """Create the vector bucket and index if they don't exist yet."""
    # Bucket
    try:
        s3v.get_vector_bucket(vectorBucketName=BUCKET_NAME)
        print(f"  [ok] bucket '{BUCKET_NAME}' already exists")
    except s3v.exceptions.NotFoundException:
        s3v.create_vector_bucket(vectorBucketName=BUCKET_NAME)
        print(f"  [created] bucket '{BUCKET_NAME}'")

    # Index
    try:
        s3v.get_index(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME)
        print(f"  [ok] index '{INDEX_NAME}' already exists")
    except s3v.exceptions.NotFoundException:
        s3v.create_index(
            vectorBucketName=BUCKET_NAME,
            indexName=INDEX_NAME,
            dataType="float32",
            dimension=EMBED_DIM,
            distanceMetric="cosine",
            metadataConfiguration={
                # Keys that can be used in metadata filters during queries.
                # Any key NOT listed here is stored but cannot be filtered on.
                # We want to filter by topic and source, so don't exclude them.
                "nonFilterableMetadataKeys": ["text"],  # store text but don't filter on it
            },
        )
        print(f"  [created] index '{INDEX_NAME}' (cosine, {EMBED_DIM}d)")


# ── Knowledge base documents ──────────────────────────────────────────────────

DOCUMENTS = [
    {
        "key": "doc-001",
        "text": "Strands Agents is an open-source SDK for building AI agents with AWS. "
                "It provides a simple Agent class that handles tool orchestration, "
                "conversation history, and multi-agent coordination out of the box.",
        "topic": "overview",
        "source": "strands-docs",
    },
    {
        "key": "doc-002",
        "text": "The @tool decorator in Strands converts any Python function into an agent tool. "
                "The function's docstring becomes the tool description. Type hints define "
                "the parameter schema. The agent calls tools autonomously based on task needs.",
        "topic": "tools",
        "source": "strands-docs",
    },
    {
        "key": "doc-003",
        "text": "Strands supports multi-agent orchestration via agents-as-tools: wrap one Agent "
                "inside a @tool function and pass it to another Agent. The outer agent can "
                "delegate subtasks to specialist inner agents transparently.",
        "topic": "multi-agent",
        "source": "strands-docs",
    },
    {
        "key": "doc-004",
        "text": "AgentCore is AWS's managed hosting platform for Strands agents. Use "
                "BedrockAgentCoreApp to deploy. It requires POST /invocations and GET /ping "
                "endpoints on port 8080. Deploy via ECR image push + agent registration.",
        "topic": "deployment",
        "source": "strands-docs",
    },
    {
        "key": "doc-005",
        "text": "Reflexion is an iterative self-improvement loop: the agent attempts a task, "
                "an evaluator scores the result, a reflector generates critique, and the "
                "agent retries with accumulated context. Stop when score threshold is met "
                "or retry budget exhausted.",
        "topic": "patterns",
        "source": "strands-docs",
    },
    {
        "key": "doc-006",
        "text": "AG-UI is an SSE event protocol for streaming agent state to a frontend. "
                "create_strands_app() wraps a Strands agent in a FastAPI app with "
                "/invocations (SSE) and /ping endpoints. Works with CopilotKit and custom React.",
        "topic": "frontend",
        "source": "strands-docs",
    },
    {
        "key": "doc-007",
        "text": "Strands Memory uses AgentCore's long-term memory API. create_memory_store() "
                "creates a namespaced store. The agent automatically consolidates conversation "
                "turns into semantic memories via save_memory_tool.",
        "topic": "memory",
        "source": "strands-docs",
    },
    {
        "key": "doc-008",
        "text": "MCP (Model Context Protocol) integration in Strands uses MCPClient. "
                "Initialize with a lambda returning a stdio_client or sse_client. "
                "Use the prefix parameter when mounting multiple MCP servers to avoid "
                "tool name collisions.",
        "topic": "mcp",
        "source": "strands-docs",
    },
]


def ingest_documents(documents: list[dict]):
    """Embed and store documents. Check existing keys first to avoid re-embedding."""
    # Check which keys already exist
    all_keys = [d["key"] for d in documents]
    try:
        existing = s3v.get_vectors(
            vectorBucketName=BUCKET_NAME,
            indexName=INDEX_NAME,
            keys=all_keys,
            returnData=False,
            returnMetadata=False,
        )
        existing_keys = {v["key"] for v in existing.get("vectors", []) if not v.get("error")}
    except Exception:
        existing_keys = set()

    to_ingest = [d for d in documents if d["key"] not in existing_keys]
    if not to_ingest:
        print(f"  [ok] all {len(documents)} documents already ingested")
        return

    print(f"  Embedding {len(to_ingest)} new documents...")
    vectors = []
    for doc in to_ingest:
        vec = embed(doc["text"])
        vectors.append({
            "key": doc["key"],
            "data": {"float32": vec},
            "metadata": {
                "text":   doc["text"],
                "topic":  doc["topic"],
                "source": doc["source"],
            },
        })
        print(f"    embedded {doc['key']} ({doc['topic']})")

    s3v.put_vectors(
        vectorBucketName=BUCKET_NAME,
        indexName=INDEX_NAME,
        vectors=vectors,
    )
    print(f"  [done] ingested {len(vectors)} vectors")


# ── Agent tools ───────────────────────────────────────────────────────────────

@tool
def query_knowledge_base(question: str, topic_filter: str = "") -> str:
    """
    Search the Strands documentation knowledge base for relevant information.
    Returns the top matching passages with their topics.

    Args:
        question: The question or topic to search for.
        topic_filter: Optional topic to restrict search (overview, tools,
                      multi-agent, deployment, patterns, frontend, memory, mcp).
                      Leave empty to search all topics.
    """
    query_vec = embed(question)

    kwargs = dict(
        vectorBucketName=BUCKET_NAME,
        indexName=INDEX_NAME,
        topK=3,
        queryVector={"float32": query_vec},
        returnMetadata=True,
        returnDistance=True,
    )

    # Apply metadata filter if topic specified
    if topic_filter:
        kwargs["filter"] = {"topic": {"$eq": topic_filter}}

    resp = s3v.query_vectors(**kwargs)
    results = resp.get("vectors", [])

    if not results:
        return f"No results found for '{question}'" + (f" in topic '{topic_filter}'" if topic_filter else "")

    parts = []
    for r in results:
        meta = r.get("metadata", {})
        dist = r.get("distance", 0)
        similarity = round(1 - dist, 3)  # cosine: distance 0 = identical
        text = meta.get("text", "")
        topic = meta.get("topic", "?")
        parts.append(f"[{topic}, similarity={similarity}] {text}")

    return "\n\n".join(parts)


@tool
def list_topics() -> str:
    """List all available topics in the knowledge base."""
    return "Available topics: overview, tools, multi-agent, deployment, patterns, frontend, memory, mcp"


# ── Build agent ───────────────────────────────────────────────────────────────

def build_agent() -> Agent:
    return Agent(
        model=get_model("claude-sonnet-4"),
        tools=[query_knowledge_base, list_topics],
        system_prompt=(
            "You are a Strands Agents documentation assistant. "
            "Use query_knowledge_base to find relevant information before answering. "
            "Always cite the topic and similarity score from search results. "
            "If unsure, search multiple times with different phrasings."
        ),
        callback_handler=None,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("L45: Agentic RAG with S3 Vectors")
    print("=" * 60)

    # Setup
    print("\n[1] Ensuring vector bucket and index...")
    ensure_bucket_and_index()

    print("\n[2] Ingesting knowledge base documents...")
    ingest_documents(DOCUMENTS)

    # Build agent
    agent = build_agent()

    print("\n" + "=" * 60)
    print("QUERY 1 — General question (searches all topics)")
    print("=" * 60)
    q1 = "How do I deploy a Strands agent to AWS?"
    print(f"  Q: {q1}")
    r1 = agent(q1)
    print(f"  A: {r1}")

    print("\n" + "=" * 60)
    print("QUERY 2 — Topic-filtered search")
    print("=" * 60)
    q2 = "What is the @tool decorator and how does it work?"
    print(f"  Q: {q2}")
    r2 = agent(q2)
    print(f"  A: {r2}")

    print("\n" + "=" * 60)
    print("QUERY 3 — Cross-session: data already there (idempotent re-run)")
    print("=" * 60)
    q3 = "Explain the Reflexion pattern for self-improving agents."
    print(f"  Q: {q3}")
    r3 = agent(q3)
    print(f"  A: {r3}")

    print("\n" + "=" * 60)
    print("KEY CONCEPTS DEMONSTRATED")
    print("=" * 60)
    print("""
  S3 Vectors vs ChromaDB (L13):
    S3 Vectors  — AWS-managed, serverless, durable, filterable metadata
    ChromaDB    — local process, manual persistence, simpler setup

  Idempotent setup:
    get_vector_bucket → 404 → create_vector_bucket
    get_index        → 404 → create_index
    get_vectors(all keys) before put_vectors → skip already-ingested docs

  Metadata filtering:
    metadataConfiguration.nonFilterableMetadataKeys = ["text"]
    → text field stored but excluded from filter index (large, free-text)
    → topic, source filterable: filter={"topic": {"$eq": "deployment"}}

  Vector item shape (PutVectors):
    {"key": str, "data": {"float32": [float,...]}, "metadata": {k: v}}

  QueryVectors:
    queryVector={"float32": [float,...]}, topK=N, returnMetadata=True
    Returns vectors sorted by distance (cosine: 0=identical, 2=opposite)
    """)

    # ── Cleanup (comment out to keep data for cross-session demo) ──────────────
    print("[cleanup] Deleting index and bucket...")
    try:
        s3v.delete_index(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME)
        print(f"  deleted index '{INDEX_NAME}'")
        s3v.delete_vector_bucket(vectorBucketName=BUCKET_NAME)
        print(f"  deleted bucket '{BUCKET_NAME}'")
    except Exception as e:
        print(f"  cleanup error: {e}")

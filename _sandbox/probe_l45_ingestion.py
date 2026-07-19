"""
L45 Probe: Ingestion pipeline — demonstrate the dangling-reference problem.

Shows how the same chunk text, when embedded with vs without document/section
context, produces very different cosine distances for the same query.
"""
import json, boto3

bedrock_rt = boto3.client("bedrock-runtime", region_name="us-east-1")

def embed(text: str) -> list[float]:
    body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})
    resp = bedrock_rt.invoke_model(modelId="amazon.titan-embed-text-v2:0", body=body)
    return json.loads(resp["body"].read())["embedding"]

def cosine(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    return round(dot, 4)  # normalized vectors: dot product = cosine similarity

# The dangling-reference chunk — ambiguous "It"
CHUNK = "It supports two types of tools: native @tool decorated functions and MCP servers. Native tools run in-process with low latency. MCP tools run as separate processes and are framework-agnostic."

# Contextually enriched version — same content, added document/section prefix
ENRICHED = "Document: Strands SDK Architecture | Section: Tool System | " + CHUNK

# Queries
QUERIES = [
    "What does the Strands tool system support?",
    "What tool types are available in Strands?",
    "How do native tools differ from MCP tools?",
    "What is the tool system?",  # hardest — no "it" / no "strands" in chunk
]

print("Embedding chunks and queries...\n")
chunk_vec    = embed(CHUNK)
enriched_vec = embed(ENRICHED)

print(f"{'Query':<45} {'Naive sim':>10} {'Enriched sim':>13} {'Delta':>7}")
print("-" * 78)
for q in QUERIES:
    qv = embed(q)
    naive_sim    = cosine(chunk_vec, qv)
    enriched_sim = cosine(enriched_vec, qv)
    delta = round(enriched_sim - naive_sim, 4)
    flag = "+" if delta > 0.01 else (" " if abs(delta) < 0.005 else "-")
    print(f"{q:<45} {naive_sim:>10.4f} {enriched_sim:>13.4f} {flag}{abs(delta):>6.4f}")

print("\n\nFixed-size chunking problem:")
long_text = (
    "The Agent class manages tool orchestration and conversation history. "
    "It also handles model selection and streaming. "
    "To create an agent you need a model and optionally a list of tools. "
    "The model can be any LiteLLM-compatible provider. "
    "Tools are decorated with @tool and their docstring becomes the description."
)
# Fixed 100-char chunks
chunks_fixed = [long_text[i:i+100] for i in range(0, len(long_text), 100)]
# Sentence chunks
import re
chunks_sentence = [s.strip() for s in re.split(r'(?<=[.!?])\s+', long_text) if s.strip()]

print(f"\n  Fixed 100-char chunks ({len(chunks_fixed)}):")
for i, c in enumerate(chunks_fixed):
    print(f"    [{i}] {c!r}")

print(f"\n  Sentence chunks ({len(chunks_sentence)}):")
for i, c in enumerate(chunks_sentence):
    print(f"    [{i}] {c!r}")

q = "How do I create an agent?"
qv = embed(q)
print(f"\n  Query: {q!r}")
print(f"  Fixed chunk similarities:")
for i, c in enumerate(chunks_fixed):
    sim = cosine(embed(c), qv)
    print(f"    [{i}] {sim:.4f} | {c[:60]!r}")
print(f"  Sentence chunk similarities:")
for i, c in enumerate(chunks_sentence):
    sim = cosine(embed(c), qv)
    print(f"    [{i}] {sim:.4f} | {c[:60]!r}")

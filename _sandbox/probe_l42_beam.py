"""
L42 Beam probe: can we run K agents concurrently with asyncio.to_thread?
Questions:
1. Does asyncio.to_thread work for Agent.__call__ (blocking LLM call)?
2. How long does K=3 parallel take vs K=3 sequential?
3. Are K separate Agent instances needed (thread safety)?
"""
import asyncio
import time
from strands import Agent
from tools import get_model

fast_model = get_model("haiku")

# ── Q1+Q2: parallel vs sequential timing ──────────────────────────────────────
print("=== Q1+Q2: parallel Actor calls ===")

ACTOR_SYSTEM = """You are an expert Python programmer.
Write clean, correct Python functions.
Return ONLY a ```python code block — no explanation, no prose."""

PROMPT = """Write a Python function called `compress_rle` that does run-length encoding.
Rules:
- Single chars: just the char (no count prefix)
- Multiple chars: count + char
- Examples: "aaa" → "3a", "abc" → "abc", "aabbc" → "2a2bc"
Return ONLY a ```python code block."""

async def run_parallel(k: int) -> list:
    """Run k agents concurrently — each gets its own Agent instance."""
    actors = [
        Agent(model=fast_model, system_prompt=ACTOR_SYSTEM, tools=[], callback_handler=None)
        for _ in range(k)
    ]
    t0 = time.time()
    results = await asyncio.gather(*[asyncio.to_thread(a, PROMPT) for a in actors])
    elapsed = time.time() - t0
    print(f"  Parallel K={k}: {elapsed:.2f}s")
    return [str(r) for r in results]

def run_sequential(k: int) -> list:
    """Run k agents one after another — single Agent instance reused."""
    actor = Agent(model=fast_model, system_prompt=ACTOR_SYSTEM, tools=[], callback_handler=None)
    t0 = time.time()
    results = [str(actor(PROMPT)) for _ in range(k)]
    elapsed = time.time() - t0
    print(f"  Sequential K={k}: {elapsed:.2f}s")
    return results

results_par = asyncio.run(run_parallel(3))
results_seq = run_sequential(3)

print(f"\n  Got {len(results_par)} parallel results, {len(results_seq)} sequential results")
print(f"  First parallel result (first 80 chars): {results_par[0][:80]}")

# ── Q3: verify each result has extractable code ───────────────────────────────
import re
print("\n=== Q3: code extraction from each candidate ===")
def extract_code(response: str) -> str | None:
    block = re.search(r'```python\s*(.*?)```', response, re.DOTALL)
    return block.group(1).strip() if block else None

for i, r in enumerate(results_par):
    code = extract_code(r)
    print(f"  Candidate {i+1}: {'✓ extracted' if code else '✗ no code'} ({len(code.splitlines()) if code else 0} lines)")

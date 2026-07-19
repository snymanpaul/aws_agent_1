"""
L42 Probe: Reflexion patterns
Questions:
1. Can we exec() LLM-generated code safely enough for a demo?
2. Does accumulated context in a system prompt actually help across attempts?
3. What's the right structured output shape for the Reflector?
"""
import re
import traceback
from pydantic import BaseModel
from strands import Agent
from tools import get_model

fast_model = get_model("haiku")

# ── Q1: safe code extraction + exec ───────────────────────────────────────────
print("=== Q1: code extraction + exec ===")

sample_response = """
Here's the implementation:

```python
def normalize_scores(values: list) -> list:
    if not values:
        return []
    mn, mx = min(values), max(values)
    if mn == mx:
        return [0.5] * len(values)
    return [round((v - mn) / (mx - mn), 4) for v in values]
```
"""

def extract_function(response: str, fn_name: str) -> str | None:
    """Pull the first ```python block, fall back to def fn_name."""
    block = re.search(r'```python\s*(.*?)```', response, re.DOTALL)
    if block:
        return block.group(1).strip()
    # fallback: grab from def fn_name to end
    m = re.search(rf'(def {fn_name}\b.*)', response, re.DOTALL)
    return m.group(1).strip() if m else None

def run_function(code: str, fn_name: str, args, expected):
    """exec code in restricted namespace, call fn, compare to expected."""
    ns = {"__builtins__": {"round": round, "min": min, "max": max, "len": len, "list": list}}
    try:
        exec(code, ns)
        fn = ns.get(fn_name)
        if fn is None:
            return False, f"function '{fn_name}' not found after exec"
        result = fn(*args)
        passed = result == expected
        return passed, f"got {result!r}, expected {expected!r}"
    except Exception as e:
        return False, f"exception: {e}"

code = extract_function(sample_response, "normalize_scores")
print(f"Extracted:\n{code}\n")

tests = [
    (([1, 2, 3, 4, 5],), [0.0, 0.25, 0.5, 0.75, 1.0]),
    (([],), []),
    (([5, 5, 5],), [0.5, 0.5, 0.5]),
    (([10, 20],), [0.0, 1.0]),
    (([3],), [0.5]),
]
for args, expected in tests:
    passed, msg = run_function(code, "normalize_scores", args, expected)
    print(f"  {'✓' if passed else '✗'} normalize_scores({args[0]}) → {msg}")

# ── Q2: Reflector structured output shape ─────────────────────────────────────
print("\n=== Q2: Reflector structured output ===")

class ReflectionOutput(BaseModel):
    score: float           # 0.0 – 1.0 based on test results
    passed: int
    total: int
    what_failed: list[str] # one line per failing test
    improvement_advice: str  # concrete, actionable next-attempt guidance

reflector = Agent(model=fast_model, tools=[], callback_handler=None)

failure_summary = """
Function: normalize_scores
Failed tests:
  - normalize_scores([3]) → got [0.0], expected [0.5]  (single element not treated as all-equal)
  - normalize_scores([5,5,5]) → got [0.0,0.0,0.0], expected [0.5,0.5,0.5]  (all-equal not handled)
Passed: 3/5
"""

result = reflector(
    f"Given these test failures for a Python function:\n{failure_summary}\n"
    f"Analyse what went wrong and give specific improvement advice.",
    structured_output_model=ReflectionOutput,
)
r = result.structured_output
print(f"Score: {r.score}, passed {r.passed}/{r.total}")
print(f"What failed: {r.what_failed}")
print(f"Advice: {r.improvement_advice[:200]}")

"""
Probe: diverse strategy prompting — do different strategy hints cause
different implementations with different failure modes on flatten()?

chain.from_iterable → only 1 level → fails on deep nesting
recursive loop     → correct
generator          → correct but may have import issues
"""
import re
from strands import Agent
from tools import get_model

haiku = get_model("haiku")

ACTOR_BASE = """You are an expert Python programmer.
Write clean, correct Python functions.
Return ONLY a ```python code block — no explanation, no prose."""

TASK = """Write a Python function called `flatten` that recursively flattens
a nested list into a single flat list.

Signature: flatten(nested: list) -> list

Rules:
  - Any element that is a list should be flattened recursively
  - Non-list elements are kept as-is
  - Return a new flat list

Examples:
  flatten([1, [2, 3], 4])        → [1, 2, 3, 4]
  flatten([1, [2, [3, 4]], 5])   → [1, 2, 3, 4, 5]
  flatten([])                     → []
  flatten([1, 2, 3])              → [1, 2, 3]
"""

TEST_CASES = [
    (([1, [2, 3], 4],),          [1, 2, 3, 4]),
    (([1, [2, [3, 4]], 5],),     [1, 2, 3, 4, 5]),
    (([],),                       []),
    (([1, 2, 3],),                [1, 2, 3]),
    (([[[1]], [[2]]],),            [1, 2]),            # 3-deep
    (([1, [2, [3, [4, [5]]]]],),  [1, 2, 3, 4, 5]),   # 5-deep
    (([[[], [1]], 2],),            [1, 2]),             # empty nested + mixed
]

STRATEGIES = [
    "Use a manual for-loop with isinstance(item, list) check and recursion.",
    "Use itertools.chain.from_iterable with a recursive approach.",
    "Use a generator function (yield from) to produce a flat sequence.",
]

def extract_code(response: str) -> str | None:
    block = re.search(r'```python\s*(.*?)```', str(response), re.DOTALL)
    return block.group(1).strip() if block else None

def run_test(code, test_cases):
    import itertools
    safe = {"len": len, "range": range, "list": list, "isinstance": isinstance,
            "itertools": itertools, "chain": itertools.chain,
            "None": None, "True": True, "False": False, "any": any}
    ns = {"__builtins__": safe}
    exec(code, ns)
    fn = ns.get("flatten")
    if fn is None:
        return 0, ["function not found"]
    passes, fails = 0, []
    for args, expected in test_cases:
        try:
            r = fn(*args)
            if r == expected:
                passes += 1
            else:
                fails.append(f"flatten({args[0]}) → got {r}, expected {expected}")
        except Exception as e:
            fails.append(f"flatten({args[0]}) → exception: {e}")
    return passes, fails

for i, strategy in enumerate(STRATEGIES, 1):
    system = ACTOR_BASE + f"\n\nImplementation strategy: {strategy}"
    actor = Agent(model=haiku, system_prompt=system, tools=[], callback_handler=None)
    raw = actor(TASK)
    code = extract_code(str(raw))
    try:
        p, fails = run_test(code, TEST_CASES)
        print(f"Strategy {i} ({strategy[:40]}...): {p}/{len(TEST_CASES)}")
        for f in fails:
            print(f"  ✗ {f}")
    except Exception as e:
        print(f"Strategy {i}: exec error — {e}")
        print(f"  Code: {code[:120] if code else 'None'}")

"""
Probe: interleave with hidden edge cases (unequal lengths, 3+ lists).
Spec only shows equal-length 2-list examples.
Haiku using zip() will truncate to shortest — missing tail elements.
"""
import re
from strands import Agent
from tools import get_model

haiku = get_model("haiku")

ACTOR_SYSTEM = """You are an expert Python programmer.
Write clean, correct Python functions.
Return ONLY a ```python code block — no explanation, no prose."""

TASK = """Write a Python function called `interleave` that interleaves multiple lists.

Signature: interleave(lists: list[list]) -> list

Rules:
  - Take elements from each list in round-robin order
  - Continue until all lists are exhausted
  - Return a flat list

Examples:
  interleave([[1, 2, 3], [4, 5, 6]])  → [1, 4, 2, 5, 3, 6]
  interleave([[1], [2], [3]])          → [1, 2, 3]
  interleave([[]])                     → []
"""

TEST_CASES = [
    (([[1,2,3],[4,5,6]],),     [1,4,2,5,3,6]),          # equal, 2 lists
    (([[1],[2],[3]],),          [1,2,3]),                 # single items, 3 lists
    (([[]], ),                  []),                      # single empty
    (([[1,2],[3,4,5]],),       [1,3,2,4,5]),             # unequal — zip() fails here
    (([[1,2],[3,4,5],[6]],),   [1,3,6,2,4,5]),           # 3 lists, unequal
    (([[1]],),                  [1]),                     # single list, one item
    (([[], [1,2]],),            [1,2]),                   # first empty
    (([[1,2],[],[3,4]],),       [1,3,2,4]),               # middle empty
]

def extract_code(response: str) -> str | None:
    block = re.search(r'```python\s*(.*?)```', str(response), re.DOTALL)
    return block.group(1).strip() if block else None

def run_test(code, test_cases):
    safe = {"len": len, "range": range, "list": list, "max": max,
            "enumerate": enumerate, "zip": zip, "None": None,
            "True": True, "False": False, "any": any, "all": all}
    ns = {"__builtins__": safe}
    exec(code, ns)
    fn = ns["interleave"]
    passes, fails = 0, []
    for args, expected in test_cases:
        try:
            r = fn(*args)
            if r == expected:
                passes += 1
            else:
                fails.append(f"interleave({args[0]}) → got {r}, expected {expected}")
        except Exception as e:
            fails.append(f"interleave({args[0]}) → exception: {e}")
    return passes, fails

actor = Agent(model=haiku, system_prompt=ACTOR_SYSTEM, tools=[], callback_handler=None)

for run in range(1, 4):
    raw = actor(TASK)
    code = extract_code(str(raw))
    try:
        p, fails = run_test(code, TEST_CASES)
        print(f"Run {run}: {p}/{len(TEST_CASES)} passed")
        for f in fails:
            print(f"  ✗ {f}")
    except Exception as e:
        print(f"Run {run}: exec error — {e}")
        print(f"Code snippet: {code[:200] if code else 'None'}")

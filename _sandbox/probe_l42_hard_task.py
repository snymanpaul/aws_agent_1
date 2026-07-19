"""
Probe: find a task that haiku reliably fails on first attempt.

Candidates:
Q1. find_all_occurrences with overlapping matches (spec doesn't say "overlapping")
Q2. format_table with exact spacing/separator requirements
Q3. evaluate_rpn with edge cases (empty, single token, div-by-zero)
"""
import re
from strands import Agent
from tools import get_model

haiku = get_model("haiku")

ACTOR_SYSTEM = """You are an expert Python programmer.
Write clean, correct Python functions.
Return ONLY a ```python code block — no explanation, no prose."""

def extract_code(response: str, fn_name: str) -> str | None:
    block = re.search(r'```python\s*(.*?)```', str(response), re.DOTALL)
    if block:
        return block.group(1).strip()
    m = re.search(rf'(def {fn_name}\b.*)', str(response), re.DOTALL)
    return m.group(1).strip() if m else None

def eval_code(code, fn_name, test_cases):
    safe = {"len": len, "range": range, "str": str, "list": list, "int": int,
            "float": float, "re": re, "isinstance": isinstance, "any": any,
            "all": all, "sorted": sorted, "None": None, "True": True, "False": False}
    ns = {"__builtins__": safe}
    try:
        exec(code, ns)
    except Exception as e:
        return 0.0, [f"exec failed: {e}"]
    fn = ns.get(fn_name)
    if fn is None:
        return 0.0, [f"function not found"]
    fails = []
    passes = 0
    for args, expected in test_cases:
        try:
            r = fn(*args)
            if r == expected:
                passes += 1
            else:
                fails.append(f"{fn_name}({', '.join(repr(a) for a in args)}) → got {r!r}, expected {expected!r}")
        except Exception as e:
            fails.append(f"{fn_name}({', '.join(repr(a) for a in args)}) → exception: {e}")
    return passes / len(test_cases), fails

# ── Q1: overlapping substring search ──────────────────────────────────────────
print("=== Q1: find_all_occurrences (overlapping) ===")

TASK_Q1 = """Write a Python function called `find_all_occurrences` that finds all starting
positions where a pattern appears in text.

Signature: find_all_occurrences(text: str, pattern: str) -> list[int]

Return a sorted list of all starting indices where pattern appears.
Return [] if pattern is not found or if text is empty.
Raise ValueError if pattern is empty.

Examples:
  find_all_occurrences("hello", "ll")  → [2]
  find_all_occurrences("abcabc", "abc") → [0, 3]
  find_all_occurrences("hello", "xyz")  → []
"""

TEST_Q1 = [
    (("hello", "ll"), [2]),
    (("abcabc", "abc"), [0, 3]),
    (("hello", "xyz"), []),
    (("aaaa", "aa"), [0, 1, 2]),    # overlapping — key test
    (("aaaa", "a"), [0, 1, 2, 3]),
    (("abab", "ab"), [0, 2]),
    (("", "a"), []),
]

actor = Agent(model=haiku, system_prompt=ACTOR_SYSTEM, tools=[], callback_handler=None)
raw = actor(TASK_Q1)
code = extract_code(str(raw), "find_all_occurrences")
score, fails = eval_code(code, "find_all_occurrences", TEST_Q1)
print(f"Score: {score:.2f}")
for f in fails:
    print(f"  ✗ {f}")
if score == 1.0:
    print("  ✓ all passed")

# ── Q2: format_table ──────────────────────────────────────────────────────────
print("\n=== Q2: format_table ===")

TASK_Q2 = """Write a Python function called `format_table` that formats data as an ASCII table.

Signature: format_table(headers: list[str], rows: list[list]) -> str

Format:
  | col1  | col2 |
  |-------|------|
  | val1  | val2 |

Rules:
  - Each column is wide enough to fit the widest value in that column (header or data)
  - Values are left-aligned with exactly one space of padding on each side
  - Header and data rows use | separator
  - Separator row uses |----|...| with dashes filling the column width + 2 spaces
  - Return as a single string with newlines between rows (no trailing newline)

Example:
  format_table(["Name", "Age"], [["Alice", "30"], ["Bob", "25"]])
  →
  | Name  | Age |
  |-------|-----|
  | Alice | 30  |
  | Bob   | 25  |
"""

TEST_Q2 = [
    ((["Name", "Age"], [["Alice", "30"], ["Bob", "25"]]),
     "| Name  | Age |\n|-------|-----|\n| Alice | 30  |\n| Bob   | 25  |"),
    ((["X"], [["1"]]),
     "| X |\n|---|\n| 1 |"),
    ((["Col"], [["longer_value"]]),
     "| Col          |\n|--------------|\n| longer_value |"),
]

raw = actor(TASK_Q2)
code = extract_code(str(raw), "format_table")
safe2 = {"len": len, "range": range, "str": str, "list": list, "max": max,
         "None": None, "True": True, "False": False}
ns2 = {"__builtins__": safe2}
try:
    exec(code, ns2)
    fn2 = ns2.get("format_table")
    for args, expected in TEST_Q2:
        r = fn2(*args)
        ok = r == expected
        if not ok:
            print(f"  ✗ got:\n{r!r}\n     expected:\n{expected!r}")
        else:
            print(f"  ✓ passed")
except Exception as e:
    print(f"  exec failed: {e}")

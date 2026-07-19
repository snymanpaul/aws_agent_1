"""
Probe: does haiku reliably pass format_table with exact string matching?
Run 3 times to check for variation.
"""
import re
from strands import Agent
from tools import get_model

haiku = get_model("haiku")

ACTOR_SYSTEM = """You are an expert Python programmer.
Write clean, correct Python functions.
Return ONLY a ```python code block — no explanation, no prose."""

TASK = """Write a Python function called `format_table` that formats data as an ASCII table.

Signature: format_table(headers: list[str], rows: list[list]) -> str

Format rules:
  - Each column width = max(len(header), max(len(cell) for cells in column))
  - Each cell is left-aligned, padded with spaces to column width
  - Cell format:  "| {cell:<width} "  for each col, then "|" at end of row
  - Separator row: "|" + ("-" * (col_width + 2) + "|") for each col
  - Rows: header row, separator row, then data rows
  - Return single string, rows joined by "\\n", no trailing newline

Example:
  format_table(["Name", "Age"], [["Alice", "30"], ["Bob", "25"]])

Expected output (exactly):
  | Name  | Age |
  |-------|-----|
  | Alice | 30  |
  | Bob   | 25  |
"""

TEST_CASES = [
    ((["Name", "Age"], [["Alice", "30"], ["Bob", "25"]]),
     "| Name  | Age |\n|-------|-----|\n| Alice | 30  |\n| Bob   | 25  |"),
    ((["X"], [["1"]]),
     "| X |\n|---|\n| 1 |"),
    ((["Item", "Qty", "Price"], [["apple", "5", "1.20"], ["banana", "12", "0.50"]]),
     "| Item   | Qty | Price |\n|--------|-----|-------|\n| apple  | 5   | 1.20  |\n| banana | 12  | 0.50  |"),
]

def extract_code(response: str) -> str | None:
    block = re.search(r'```python\s*(.*?)```', str(response), re.DOTALL)
    return block.group(1).strip() if block else None

def run_test(code, test_cases):
    safe = {"len": len, "range": range, "str": str, "list": list, "max": max,
            "enumerate": enumerate, "zip": zip, "None": None, "True": True, "False": False}
    ns = {"__builtins__": safe}
    exec(code, ns)
    fn = ns["format_table"]
    passes = 0
    for args, expected in test_cases:
        r = fn(*args)
        if r == expected:
            passes += 1
        else:
            # Show diff
            exp_lines = expected.split('\n')
            got_lines = r.split('\n')
            for i, (e, g) in enumerate(zip(exp_lines, got_lines)):
                if e != g:
                    print(f"    line {i}: got  {g!r}")
                    print(f"    line {i}: want {e!r}")
    return passes

actor = Agent(model=haiku, system_prompt=ACTOR_SYSTEM, tools=[], callback_handler=None)

for run in range(1, 4):
    raw = actor(TASK)
    code = extract_code(str(raw))
    try:
        p = run_test(code, TEST_CASES)
        print(f"Run {run}: {p}/{len(TEST_CASES)} passed")
    except Exception as e:
        print(f"Run {run}: exec error — {e}")

"""
Fix 6 wrong cat:question entries in observations.jsonl.

These topics were written as cat:question but should be cat:insight
(infra-blocked and out-of-scope resolutions are observations, not open questions):
  - lambda-streaming-response
  - adot-integration-path
  - memory-execution-role-iam
  - kinesis-push-timing
  - bidi-response-complete-realtime
  - cloud-latency-in-robot-loop

Also removes the 6 "-correction" suffix entries added as a workaround
(now redundant since we're fixing the originals).
"""

import json
from pathlib import Path

JSONL_PATH = Path(".claude/learnings/observations.jsonl")

FIX_TOPICS = {
    "lambda-streaming-response",
    "adot-integration-path",
    "memory-execution-role-iam",
    "kinesis-push-timing",
    "bidi-response-complete-realtime",
    "cloud-latency-in-robot-loop",
}

REMOVE_TOPICS = {t + "-correction" for t in FIX_TOPICS}

lines_in = JSONL_PATH.read_text().splitlines(keepends=True)

fixed = 0
removed = 0
out_lines = []

for i, raw in enumerate(lines_in, start=1):
    # Lines that aren't valid JSON are kept as-is (pre-existing issue on line 263)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        out_lines.append(raw)
        continue

    topic = obj.get("topic", "")

    if topic in REMOVE_TOPICS:
        removed += 1
        print(f"  REMOVE  line {i}: {topic}")
        continue

    if topic in FIX_TOPICS and obj.get("cat") == "question":
        obj["cat"] = "insight"
        fixed += 1
        print(f"  FIX     line {i}: {topic}  question -> insight")
        out_lines.append(json.dumps(obj) + "\n")
        continue

    out_lines.append(raw)

JSONL_PATH.write_text("".join(out_lines))

total_after = len(out_lines)
question_count = sum(
    1 for line in out_lines
    if '"cat":"question"' in line
)

print(f"\nFixed {fixed} entries, removed {removed} entries")
print(f"Total lines: {total_after}")
print(f"Question count: {question_count}")

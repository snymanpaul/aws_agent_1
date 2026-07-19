"""
Restore the 6 ORIGINAL question entries that were wrongly changed to cat:insight.

The previous fix script was too broad — it changed ALL entries with the 6 topics,
including the original pre-2026-03-19 question entries that should stay as cat:question.

Rule: entries with these topics AND ts != "2026-03-19T00:00:00Z" are originals → restore to cat:question.
Entries with ts == "2026-03-19T00:00:00Z" are today's NEW resolution entries → stay as cat:insight.
"""

import json
from pathlib import Path

JSONL_PATH = Path(".claude/learnings/observations.jsonl")

ORIGINAL_QUESTION_TOPICS = {
    "lambda-streaming-response",
    "adot-integration-path",
    "memory-execution-role-iam",
    "kinesis-push-timing",
    "bidi-response-complete-realtime",
    "cloud-latency-in-robot-loop",
}

TODAY_TS = "2026-03-19T00:00:00Z"  # my new resolution entries

lines_in = JSONL_PATH.read_text().splitlines(keepends=True)
restored = 0
out_lines = []

for i, raw in enumerate(lines_in, start=1):
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        out_lines.append(raw)
        continue

    topic = obj.get("topic", "")
    ts = obj.get("ts", "")

    if topic in ORIGINAL_QUESTION_TOPICS and ts != TODAY_TS and obj.get("cat") == "insight":
        obj["cat"] = "question"
        restored += 1
        print(f"  RESTORE  line {i}: {topic}  insight -> question  (ts={ts})")
        out_lines.append(json.dumps(obj) + "\n")
        continue

    out_lines.append(raw)

JSONL_PATH.write_text("".join(out_lines))

question_count = sum(1 for line in out_lines if '"cat":"question"' in line)
print(f"\nRestored {restored} entries")
print(f"Total lines: {len(out_lines)}")
print(f"Question count: {question_count}")

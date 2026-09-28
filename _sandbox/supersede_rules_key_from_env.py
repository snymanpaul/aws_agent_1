"""Supersede obs-1008 and obs-1019 so the rendered CLAUDE.md rules read the LiteLLM proxy key
from LITELLM_API_KEY instead of carrying it (stage 1 of the key rotation, Paul, 2026-09-28).

Only the key's source changes. obs-1008 keeps its evidence link: the measured run
(follow_rate_n5.json) tested OpenAIModel-with-base_url against LiteLLMModel, and that part of
the rule is unchanged. Every other field is carried over. Re-running is a no-op.

    uv run python _sandbox/supersede_rules_key_from_env.py
    uv run python tools/render_claude_md.py --write
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.obs_log import append, read  # noqa: E402

KEY = 'os.environ["LITELLM_API_KEY"]'
EDITS = {
    "obs-1008": [
        ("```python\nfrom strands.models.openai import OpenAIModel\n",
         "```python\nimport os\n\nfrom strands.models.openai import OpenAIModel\n"),
        ('"api_key": "sk-local"})', f'"api_key": {KEY}}})'),
    ],
    "obs-1019": [
        ('"api_key":"sk-local"})', f'"api_key":{KEY}}})'),
    ],
}
NOTE = " Re-issued 2026-09-28 with the proxy key read from LITELLM_API_KEY instead of written inline."

entries = read()
new = []
for old_id, edits in EDITS.items():
    if any(e.get("supersedes") == old_id for e in entries):
        print(f"{old_id} already superseded; skipping")
        continue
    prior = next(e for e in entries if e["id"] == old_id)
    body = prior["rule_body"]
    for before, after in edits:
        assert body.count(before) == 1, f"{old_id}: expected exactly one {before!r}"
        body = body.replace(before, after)
    assert "sk-local" not in body, f"{old_id}: key still present after edits"
    entry = {k: v for k, v in prior.items() if k not in ("id", "status", "supersedes", "ts", "repo")}
    entry.update(status="promoted", supersedes=old_id, ts="2026-09-28T00:00:00Z", rule_body=body,
                 obs=prior["obs"] + NOTE)
    new.append(entry)

if new:
    print(append(new))

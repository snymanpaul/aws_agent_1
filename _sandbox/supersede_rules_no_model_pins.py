"""Supersede obs-1020 and obs-1021 so the rendered CLAUDE.md rules name no model release
(Paul, 2026-09-30: CLAUDE.md must not pin model releases, because releases retire).

Only the model names change. obs-1020 keeps its evidence link: the measured run
(follow_rate_n5.json) is scored by `followed_model_provider`, which checks OpenAIModel with
base_url against LiteLLMModel and never reads the model id. Every other field is carried
over. Re-running is a no-op.

    uv run python _sandbox/supersede_rules_no_model_pins.py
    uv run python tools/render_claude_md.py --write
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.obs_log import append, read  # noqa: E402

EDITS = {
    "obs-1020": [
        ('model_id="claude-sonnet-4"', 'model_id="<model>"'),
    ],
    "obs-1021": [
        ('OpenAIModel(model_id="gemini-2.5-flash"', 'OpenAIModel(model_id="<gemini model>"'),
        ("fall back to `gemini-2.5-flash`.",
         "fall back to a Gemini model from the proxy's `/v1/models`."),
    ],
}
PINNED = ("claude-sonnet-4", "gemini-2.5-flash")
NOTE = " Re-issued 2026-09-30 with no model release named, because releases retire."

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
    for name in PINNED:
        assert name not in body, f"{old_id}: {name} still present after edits"
    entry = {k: v for k, v in prior.items() if k not in ("id", "status", "supersedes", "ts", "repo")}
    entry.update(status="promoted", supersedes=old_id, ts="2026-09-30T00:00:00Z", rule_body=body,
                 obs=prior["obs"] + NOTE)
    new.append(entry)

if new:
    print(append(new))

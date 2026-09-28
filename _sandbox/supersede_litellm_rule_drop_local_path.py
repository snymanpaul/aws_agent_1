"""Supersede obs-0996 so the rendered LiteLLM rule in CLAUDE.md carries no local laptop path.

Paul, 2026-09-28: "remove local laptop file paths from CLAUDE.md". The only one was in this
rule's body (a home-directory path to the proxy's config file), inside the generated block, so
it is changed here and re-rendered rather than hand-edited. Every other field is carried over.
The path is matched by pattern so this public file does not repeat it.

Applied once, as obs-1019. Re-running is a no-op: it exits if obs-0996 is already superseded.

    uv run python _sandbox/supersede_litellm_rule_drop_local_path.py
    uv run python tools/render_claude_md.py --write
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.obs_log import append, read  # noqa: E402

OLD = re.compile(r"with its config mounted from `~/[^`]*litellm_config\.yaml` \(that repo has its own "
                 r"CLAUDE\.md\)\. Manage it with \*\*podman, not docker\*\*: don't `docker compose` from that dir\.")
NEW = ("with its config mounted from `litellm_config.yaml` in the separate `litellm-proxy` repo "
       "(it has its own CLAUDE.md). Manage it with **podman, not docker**: don't `docker compose` "
       "from that repo.")

entries = read()
if any(e.get("supersedes") == "obs-0996" for e in entries):
    raise SystemExit("obs-0996 is already superseded; nothing to do")
prior = next(e for e in entries if e["id"] == "obs-0996")
assert OLD.search(prior["rule_body"]), "obs-0996 body no longer holds the path this script replaces"

entry = {k: v for k, v in prior.items() if k not in ("id", "status", "supersedes", "ts", "repo")}
entry.update(status="promoted", supersedes="obs-0996", ts="2026-09-28T00:00:00Z",
             rule_body=OLD.sub(NEW, prior["rule_body"]),
             obs=prior["obs"] + " Re-issued 2026-09-28 without the local laptop path, at Paul's request.")
print(append([entry]))

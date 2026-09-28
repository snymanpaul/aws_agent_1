#!/bin/sh
# Stage 1 of the LiteLLM proxy key rotation (2026-09-28): every tracked use of the key reads
# LITELLM_API_KEY from the environment, with no default, so the repo stops carrying the key.
#
#   sh _sandbox/litellm_key_from_env.sh
#
# Exact-string swaps only (perl -pi), listed below. Left as they are, on purpose:
#   - .claude/learnings/observations.jsonl: append-only; the rendered rule is superseded
#     by a new observation instead.
#   - tests/instruction_following/follow_rate_n5.json: recorded model outputs.
#   - tests/instruction_following/run_follow_rate.py prompt text ("with the api key
#     sk-local"): part of a preregistered experiment. Its client code IS converted.
#   - _sandbox/append_2026_06_obs.py: verbatim source of a frozen observation.
# Two forms need judgement and are done by hand afterwards: a default parameter
# (evaluated at import) and the TypeScript files.
set -eu
cd "$(git rev-parse --show-toplevel)"

files=$(git grep -lI 'sk-local' -- '*.py' '*.yaml' \
    ':(exclude).claude/learnings/observations.jsonl' \
    ':(exclude)_sandbox/append_2026_06_obs.py')

# shellcheck disable=SC2086
perl -pi -e '
    s/"api_key": "sk-local"/"api_key": os.environ["LITELLM_API_KEY"]/g;
    s/api_key="sk-local"/api_key=os.environ["LITELLM_API_KEY"]/g;
    s/os\.environ\.get\("LITELLM_API_KEY", "sk-local"\)/os.environ["LITELLM_API_KEY"]/g;
    s/"Authorization": "Bearer sk-local"/"Authorization": "Bearer " + os.environ["LITELLM_API_KEY"]/g;
    s/^(\s*)API_KEY = "sk-local"/$1API_KEY = os.environ["LITELLM_API_KEY"]/;
    s/\(default: sk-local\)/(default: the LITELLM_API_KEY environment variable)/;
    s/^(\s*)LITELLM_API_KEY: sk-local$/$1LITELLM_API_KEY: \${LITELLM_API_KEY}/;
' $files

echo "== still holding sk-local (expected: the hand-done forms and the preregistered prompt):"
git grep -nI 'sk-local' -- '*.py' '*.yaml' '*.ts' \
    ':(exclude).claude/learnings/observations.jsonl' ':(exclude)_sandbox/append_2026_06_obs.py' || true

echo "== changed .py files that use os.environ but do not import os:"
for f in $(git diff --name-only -- '*.py'); do
    if grep -q 'os\.environ' "$f" && ! grep -qE '^\s*import os\b|^\s*import .*\bos\b|^from os ' "$f"; then
        echo "  $f"
    fi
done

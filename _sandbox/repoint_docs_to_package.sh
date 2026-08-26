#!/bin/sh
# Repoint the docs from tools/<gate>.py paths to the agent-build-gates package and its
# console scripts, after R2 moved the four gates out of tools/.
#
# tools/ keeps models.py and install_hooks.sh, so references to those stay as they are.
#
# Run: sh repoint_docs_to_package.sh <repo-root>
set -eu
REPO="${1:?usage: repoint_docs_to_package.sh <repo-root>}"
cd "$REPO"

# Command invocations become console scripts.
sed -i '' \
  -e "s|uv run python tools/no_sim_check.py \$(git ls-files '\*.py')|uv run no-sim-check \$(git ls-files '*.py')|" \
  -e 's|uv run python tools/no_sim_check.py <path>|uv run no-sim-check <path>|' \
  -e 's|uv run python tools/ship_gate.py|uv run ship-gate|' \
  README.md CLAUDE.md METHOD.md

# Module paths become package references.
sed -i '' \
  -e 's|`tools/no_sim_check.py`|`agent_build_gates.no_sim_check`|g' \
  -e 's|`tools/check_no_aws_ids.py`|`agent_build_gates.check_no_aws_ids`|g' \
  -e 's|`tools/eval_harness.py`|`agent_build_gates.eval_harness`|g' \
  -e 's|`tools/ship_gate.py`|`agent_build_gates.ship_gate`|g' \
  README.md CLAUDE.md METHOD.md

# The test-file path moved with the tests.
sed -i '' 's|`tests/test_no_sim_check.py`|`packages/agent-build-gates/tests/`|g' README.md CLAUDE.md METHOD.md

echo "remaining tools/<gate> references:"
grep -n 'tools/no_sim_check\|tools/check_no_aws_ids\|tools/eval_harness\|tools/ship_gate' \
  README.md CLAUDE.md METHOD.md || echo "  none"

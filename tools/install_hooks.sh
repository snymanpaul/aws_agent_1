#!/bin/sh
# Install the repo's git pre-commit guard. Run once per clone: sh tools/install_hooks.sh
#
# The hook blocks a commit whose staged files carry AWS account info, or whose staged
# .py files carry a substituted integration. Both run against the staged files only, so
# the cost is proportional to the change rather than the repo.
#
# CI (.github/workflows/gates.yml) runs the same two checks repo-wide plus the test
# suite. The hook is the fast local copy, not the source of truth.
set -eu
ROOT="$(git rev-parse --show-toplevel)"
HOOK="$ROOT/.git/hooks/pre-commit"

cat > "$HOOK" <<'EOF'
#!/bin/sh
# AWS-account tripwire (tools/check_no_aws_ids.py) over staged .md/.py.
staged=$(git diff --cached --name-only --diff-filter=ACM -- '*.md' '*.py')
if [ -n "$staged" ]; then
  # shellcheck disable=SC2086
  uv run python tools/check_no_aws_ids.py $staged || exit 1
fi

# Anti-simulation tripwire (tools/no_sim_check.py) over staged .py.
staged_py=$(git diff --cached --name-only --diff-filter=ACM -- '*.py')
if [ -n "$staged_py" ]; then
  # shellcheck disable=SC2086
  uv run python tools/no_sim_check.py $staged_py || exit 1
fi

exit 0
EOF

chmod +x "$HOOK"
echo "installed pre-commit hook -> $HOOK"
echo "  checks: check_no_aws_ids (staged .md/.py), no_sim_check (staged .py)"

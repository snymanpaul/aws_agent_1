#!/bin/sh
# Install the repo's git pre-commit guard. Run once per clone: sh tools/install_hooks.sh
# The hook blocks any commit whose staged .md/.py files carry AWS account info.
set -eu
ROOT="$(git rev-parse --show-toplevel)"
HOOK="$ROOT/.git/hooks/pre-commit"

cat > "$HOOK" <<'EOF'
#!/bin/sh
# AWS-account tripwire (tools/check_no_aws_ids.py) over staged .md/.py.
staged=$(git diff --cached --name-only --diff-filter=ACM -- '*.md' '*.py')
[ -z "$staged" ] && exit 0
# shellcheck disable=SC2086
uv run python tools/check_no_aws_ids.py $staged
EOF

chmod +x "$HOOK"
echo "installed pre-commit hook -> $HOOK"

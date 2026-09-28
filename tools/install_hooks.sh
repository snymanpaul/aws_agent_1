#!/bin/sh
# Install the repo's git pre-commit guard. Run once per clone: sh tools/install_hooks.sh
#
# The hook blocks a commit whose staged files carry AWS account info or a substituted
# integration (both gates from the agent-build-gates workspace package), a local machine
# path (tools/check_no_local_paths.sh), or a secret (gitleaks with .gitleaks.toml).
# Staged files only, so the cost is proportional to the change.
#
# CI (.github/workflows/gates.yml) runs the same two checks repo-wide plus the test
# suite. The hook is the fast local copy, not the source of truth.
#
# The hook adds a third check that CI cannot: a local denylist of literal strings that
# must never reach this public repo. check_no_aws_ids covers account ids, profile strings
# and account-bearing ARNs, and a control on 2026-08-27 confirmed it does NOT catch
# internal team or project names. Those cannot be hardcoded into a published gate without
# publishing the very names being protected, so they live in `.git-denylist`, which is
# gitignored and therefore local to each clone. Absent file means the check is skipped.
set -eu
ROOT="$(git rev-parse --show-toplevel)"
HOOK="$ROOT/.git/hooks/pre-commit"

cat > "$HOOK" <<'EOF'
#!/bin/sh
# AWS-account tripwire over staged .md/.py.
staged=$(git diff --cached --name-only --diff-filter=ACM -- '*.md' '*.py')
if [ -n "$staged" ]; then
  # shellcheck disable=SC2086
  uv run check-no-aws-ids $staged || exit 1
fi

# Anti-simulation tripwire over staged .py.
staged_py=$(git diff --cached --name-only --diff-filter=ACM -- '*.py')
if [ -n "$staged_py" ]; then
  # shellcheck disable=SC2086
  uv run no-sim-check $staged_py || exit 1
fi

# Local machine paths (home directories, ~/Code, /Volumes, macOS per-user temp) in any
# staged file. Same script CI runs over every tracked file.
all_staged_paths=$(git diff --cached --name-only --diff-filter=ACM)
if [ -n "$all_staged_paths" ]; then
  # shellcheck disable=SC2086
  sh "$(git rev-parse --show-toplevel)/tools/check_no_local_paths.sh" $all_staged_paths || exit 1
fi

# Secrets in the staged changes, with the repo's .gitleaks.toml. Fails closed when gitleaks
# is missing: a secret scan that silently does not run is worse than a blocked commit.
if ! command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks not found: install it (brew install gitleaks) or the commit cannot be scanned" >&2
  exit 1
fi
gitleaks git --staged --config "$(git rev-parse --show-toplevel)/.gitleaks.toml" --redact --no-banner || exit 1

# Local denylist: literal strings that must never reach this public repo and that
# check_no_aws_ids does not cover, such as another team's project names. One term per
# line; blank lines and # comments ignored. The file is gitignored, so the terms stay
# local while the check stays mechanical. Applies to ALL staged files, not just .md/.py.
DENYLIST="$(git rev-parse --show-toplevel)/.git-denylist"
if [ -f "$DENYLIST" ]; then
  all_staged=$(git diff --cached --name-only --diff-filter=ACM)
  if [ -n "$all_staged" ]; then
    hits=0
    while IFS= read -r term; do
      case "$term" in ''|'#'*) continue ;; esac
      for f in $all_staged; do
        [ -f "$f" ] || continue
        if grep -qiF -- "$term" "$f"; then
          echo "denylist: '$term' found in staged file $f" >&2
          hits=$((hits + 1))
        fi
      done
    done < "$DENYLIST"
    if [ "$hits" -gt 0 ]; then
      echo "denylist: $hits hit(s). These strings must not reach a public repo." >&2
      exit 1
    fi
  fi
fi

exit 0
EOF

chmod +x "$HOOK"
echo "installed pre-commit hook -> $HOOK"
echo "  checks: check_no_aws_ids (staged .md/.py), no_sim_check (staged .py),"
echo "          check_no_local_paths + gitleaks (all staged files), .git-denylist (if present)"

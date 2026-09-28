#!/bin/sh
# Tripwire: no local machine paths in files bound for this public repo.
#
#   sh tools/check_no_local_paths.sh FILE...          # exit 1 and list hits, 0 when clean
#
# What counts: absolute home directories (/Users/<name>/, /home/<name>/), home-relative
# project folders (~/Code, ~/Documents, ~/Desktop, ~/Downloads, ~/Docs), mounted volumes
# (/Volumes/), and macOS per-user temp (/private/var/folders, /private/tmp). Plain /tmp is
# not flagged: it is the same on every machine and says nothing about this one.
#
# Escapes, both scoped to one line:
#   - a line containing `localpath:ok` (write `# localpath:ok <reason>` in code,
#     `<!-- localpath:ok <reason> -->` in Markdown) for text that must discuss a path;
#   - the observation log's historical entries listed in FROZEN_OBS below. The log is
#     append-only and those lines were public before this check existed; they cannot be
#     edited, so they are named here instead of silently skipped. New entries are checked.
#
# The pre-commit hook passes staged files; CI passes every tracked file.

PATTERN='/Users/[^/[:space:]]+/|/home/[^/[:space:]]+/|~/(Code|Documents|Desktop|Downloads|Docs)([/[:space:]`"'"'"')]|$)|/Volumes/|/private/(var/folders|tmp)'
FROZEN_OBS='"id": "obs-(0717|0750|0972|0973|0996|1015)"'

hits=0
for f in "$@"; do
    [ -f "$f" ] || continue
    [ "$f" = "tools/check_no_local_paths.sh" ] && continue   # this file names the patterns
    out=$(grep -nIE "$PATTERN" "$f" 2>/dev/null | grep -v 'localpath:ok' | grep -vE "$FROZEN_OBS")
    if [ -n "$out" ]; then
        printf '%s\n' "$out" | while IFS= read -r line; do
            printf '%s:%s\n' "$f" "$(printf '%s' "$line" | cut -c1-160)"
        done
        hits=$((hits + $(printf '%s\n' "$out" | wc -l)))
    fi
done

if [ "$hits" -gt 0 ]; then
    echo "check_no_local_paths: $hits local path(s). Rewrite them, or mark a line that must keep one with localpath:ok <reason>." >&2
    exit 1
fi
echo "check_no_local_paths: scanned $# file(s), clean."

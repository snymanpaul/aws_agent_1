#!/bin/sh
# Replace literal \n with <br/> INSIDE ```mermaid blocks only.
#
# Why: verified against mmdc (mermaid 11) that `\n` in a node label is not a line
# break. It renders as the two characters backslash and n, so every occurrence is a
# diagram that renders wrong. `<br/>` is the break mermaid honours. Proof:
#
#   flowchart TD
#       A[first line\nsecond line]      ->  SVG text "first line\nsecond line"
#       C[br first<br/>br second]       ->  two tspans
#
# Scoping matters. Prose outside a mermaid block may legitimately contain \n (Python
# snippets, JSON, shell), so the rewrite is fence-scoped and never touches a line
# outside one.
#
#   sh _sandbox/fix_mermaid_literal_newlines.sh --dry-run   # report only
#   sh _sandbox/fix_mermaid_literal_newlines.sh             # rewrite in place

set -u
cd "$(dirname "$0")/.." || exit 1

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

files=0
lines=0

for f in $(git ls-files '*.md'); do
    n=$(awk '
        /^```mermaid[[:space:]]*$/ { inblock=1; next }
        inblock && /^```[[:space:]]*$/ { inblock=0; next }
        inblock && /\\n/ { c++ }
        END { print c+0 }
    ' "$f")
    [ "$n" -gt 0 ] || continue

    files=$((files + 1))
    lines=$((lines + n))
    printf '%4d  %s\n' "$n" "$f"

    [ "$DRY" -eq 1 ] && continue

    awk '
        /^```mermaid[[:space:]]*$/ { inblock=1; print; next }
        inblock && /^```[[:space:]]*$/ { inblock=0; print; next }
        inblock { gsub(/\\n/, "<br/>") }
        { print }
    ' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
done

if [ "$DRY" -eq 1 ]; then
    printf '\ndry run: %d line(s) across %d file(s) would change\n' "$lines" "$files"
else
    printf '\nrewrote %d line(s) across %d file(s)\n' "$lines" "$files"
    remaining=$(sh "$0" --dry-run | tail -1 | awk '{print $3}')
    printf 'remaining after rewrite: %s\n' "${remaining:-0}"
fi

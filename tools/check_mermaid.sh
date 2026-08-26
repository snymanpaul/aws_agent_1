#!/bin/sh
# Validate every ```mermaid block in tracked markdown by actually rendering it.
#
# A diagram that does not parse is worse than no diagram: it renders as an error box
# in the reader's face. `mmdc` is the reference renderer, so this is a real check
# rather than a syntax guess.
#
#   sh _sandbox/check_mermaid.sh
#
# Exits non-zero and names the file and block index of anything that fails to render.
#
# Two things this got wrong on the first pass, both of the same kind, a checker that
# under-reports being worse than no checker:
#
#   1. Temp names were built with `tr '/' '_'`, so a path under a dot-directory
#      (.claude/learnings/...) produced a leading-dot filename, and the `*.mmd` glob
#      does not match dotfiles. 48 of 133 blocks were silently skipped. Fixed by
#      prefixing every temp name and by enumerating with `find` rather than a glob.
#   2. The extracted-block count was never reconciled against the fence count, so the
#      skip was invisible. It is now checked explicitly and fails the run.

set -u
cd "$(dirname "$0")/.." || exit 1

command -v mmdc >/dev/null 2>&1 || {
    echo "mmdc not found. Install with: npm i -g @mermaid-js/mermaid-cli" >&2
    exit 127
}

# mmdc drives Chromium through puppeteer and takes its puppeteer settings as a FILE
# (-p/--puppeteerConfigFile), not an environment variable. CI runners cannot use the
# Chromium sandbox, so the workflow writes a config and points PUPPETEER_CONFIG at it;
# locally the variable is unset and the default applies.
PUPPETEER_ARGS=""
if [ -n "${PUPPETEER_CONFIG:-}" ]; then
    if [ -f "${PUPPETEER_CONFIG}" ]; then
        PUPPETEER_ARGS="-p ${PUPPETEER_CONFIG}"
    else
        echo "PUPPETEER_CONFIG is set to '${PUPPETEER_CONFIG}' but that file does not exist" >&2
        exit 2
    fi
fi

TMP=$(mktemp -d) || exit 1
trap 'rm -rf "$TMP"' EXIT

# Extract each block to its own file. The `blk_` prefix keeps paths that begin with a
# dot from producing hidden temp files.
for f in $(git ls-files '*.md'); do
    awk -v out="$TMP" -v name="blk_$(echo "$f" | tr '/' '_')" '
        /^```mermaid[[:space:]]*$/ { inblock=1; n++; next }
        inblock && /^```[[:space:]]*$/ { inblock=0; next }
        inblock { print > (out "/" name "." n ".mmd") }
    ' "$f"
done

# Reconcile before rendering. If these disagree, the extractor is dropping blocks and
# every "0 failed" below would be a false green.
extracted=$(find "$TMP" -name '*.mmd' | wc -l | tr -d ' ')
fences=$(git grep -c -F '```mermaid' -- '*.md' | awk -F: '{s+=$2} END {print s+0}')
if [ "$extracted" -ne "$fences" ]; then
    echo "EXTRACTION MISMATCH: $extracted block(s) extracted, $fences fence(s) in tracked markdown" >&2
    echo "The checker is dropping blocks. Fix the extractor before trusting a pass." >&2
    exit 2
fi

fail=0
total=0

for m in $(find "$TMP" -name '*.mmd' | sort); do
    total=$((total + 1))
    # PUPPETEER_ARGS is intentionally unquoted: it is either empty or two words.
    if mmdc $PUPPETEER_ARGS -i "$m" -o "$m.svg" >/dev/null 2>"$m.err"; then
        :
    else
        fail=$((fail + 1))
        printf '  FAIL  %s\n' "$(basename "$m" .mmd)"
        grep -iE 'error|expecting|got' "$m.err" | head -4 | sed 's/^/          /'
    fi
done

printf '\nmermaid: %d block(s) from %d fence(s), %d failed\n' "$total" "$fences" "$fail"
[ "$fail" -eq 0 ] || exit 1

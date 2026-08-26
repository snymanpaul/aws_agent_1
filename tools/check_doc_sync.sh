#!/bin/sh
# Detect drift between this repo's research reports and the working documents they
# were adapted from, which live in a sibling directory outside version control.
#
# The pairs are not byte-identical by design: the sibling docs are the raw research,
# the reports here are adapted to this repo's format and framing. What has to stay in
# sync is the substance. This script cannot check substance, so it checks the next best
# thing: whether the source has changed since the target was last reconciled with it.
#
# Local tool. The sibling directory does not exist in CI, and the script exits 0 with a
# note in that case rather than failing a build over a path that was never going to be
# there.
#
#   sh tools/check_doc_sync.sh            # report drift, exit 1 if any
#   sh tools/check_doc_sync.sh --update   # re-record hashes after reconciling
#
# Point DATA_ENG_DOCS at the source directory if it is not the default sibling.
set -eu

ROOT="$(git rev-parse --show-toplevel)"
MANIFEST="$ROOT/tools/doc_sync.manifest"
SRC_DIR="${DATA_ENG_DOCS:-$ROOT/../aws_data_engineering/docs}"

if [ ! -d "$SRC_DIR" ]; then
  echo "doc_sync: source directory not present ($SRC_DIR), nothing to compare."
  echo "  Set DATA_ENG_DOCS to check against it."
  exit 0
fi

UPDATE=0
[ "${1:-}" = "--update" ] && UPDATE=1

drift=0
checked=0
tmp="$(mktemp)"

# manifest format: <sha256-of-source>  <source-basename>  <target-path-in-this-repo>
while IFS= read -r line; do
  case "$line" in ''|\#*) printf '%s\n' "$line" >> "$tmp"; continue ;; esac

  recorded=$(echo "$line" | awk '{print $1}')
  src_name=$(echo "$line" | awk '{print $2}')
  target=$(echo "$line" | awk '{print $3}')
  checked=$((checked + 1))

  src_path="$SRC_DIR/$src_name"
  if [ ! -f "$src_path" ]; then
    echo "MISSING SOURCE  $src_name"
    drift=$((drift + 1))
    printf '%s\n' "$line" >> "$tmp"
    continue
  fi
  if [ ! -f "$ROOT/$target" ]; then
    echo "MISSING TARGET  $target"
    drift=$((drift + 1))
    printf '%s\n' "$line" >> "$tmp"
    continue
  fi

  current=$(shasum -a 256 "$src_path" | awk '{print $1}')
  if [ "$current" = "$recorded" ]; then
    echo "in sync        $src_name"
    printf '%s\n' "$line" >> "$tmp"
  elif [ "$UPDATE" -eq 1 ]; then
    echo "re-recorded    $src_name"
    printf '%s  %s  %s\n' "$current" "$src_name" "$target" >> "$tmp"
  else
    echo "SOURCE CHANGED $src_name"
    echo "                 reconcile -> $target, then: sh tools/check_doc_sync.sh --update"
    drift=$((drift + 1))
    printf '%s\n' "$line" >> "$tmp"
  fi
done < "$MANIFEST"

mv "$tmp" "$MANIFEST"

echo
if [ "$drift" -gt 0 ] && [ "$UPDATE" -eq 0 ]; then
  echo "doc_sync: $checked pair(s), $drift needing attention."
  exit 1
fi
echo "doc_sync: $checked pair(s), all reconciled."

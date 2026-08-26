#!/bin/sh
# Remove em-dashes from the two remaining root docs, choosing punctuation that reads
# correctly. Special cases run before the bulk pass, same approach as strip_em_dashes.sh.
#
# Run: sh strip_em_dashes_2.sh <repo-root>
set -eu
REPO="${1:?usage: strip_em_dashes_2.sh <repo-root>}"
cd "$REPO"

# A dash joining two independent clauses takes a comma, not a colon.
sed -i '' \
  -e 's|\*\* — and it makes|**, and it makes|' \
  -e 's|classic API — verified in source|classic API, verified in source|' \
  -e 's|## 5. Proposed extension — Tier 22:|## 5. Proposed extension, Tier 22:|' \
  LEARNING_PLAN_v148_impact.md

sed -i '' \
  -e 's|\*\* — because the repo|**, because the repo|' \
  LEARNING_PLAN_agentic_memory_evals.md

# Everything left is a definition dash in a heading, list label or table cell.
sed -i '' 's| — |: |g' LEARNING_PLAN_v148_impact.md LEARNING_PLAN_agentic_memory_evals.md

echo "remaining em-dashes:"
for f in LEARNING_PLAN_v148_impact.md LEARNING_PLAN_agentic_memory_evals.md; do
  printf '  %-42s %s\n' "$f" "$(grep -c '—' "$f" || true)"
done

#!/bin/sh
# Remove every em-dash from three repo docs, choosing the punctuation that reads
# correctly rather than substituting one character blindly.
#
# Order matters: the special cases below need a comma, semicolon or parentheses,
# so they run BEFORE the bulk pass that turns the remaining definition dashes
# (table cells, link lists, headings) into colons.
#
# Run: sh strip_em_dashes.sh /path/to/repo
set -eu
REPO="${1:?usage: strip_em_dashes.sh <repo-root>}"
cd "$REPO"

# ---------------------------------------------------------------- CLAUDE.md
# A colon would clash with the trailing colon or read as a definition.
sed -i '' \
  -e 's|for LiteLLM — \*\*not\*\*|for LiteLLM, **not**|' \
  -e 's|real MCP calls — never simulate|real MCP calls, never simulate|' \
  -e 's|from `bedrock_agentcore` — do \*\*not\*\*|from `bedrock_agentcore`, do **not**|' \
  CLAUDE.md

# --------------------------------------------------------- NEXT_STEPS_PLAN.md
# Sentence already carries a colon, so a second one would read badly.
sed -i '' \
  -e 's|pre-commit hook — extend that hook|pre-commit hook; extend that hook|' \
  NEXT_STEPS_PLAN.md

# ----------------------------------------------------------- LEARNING_PLAN.md
# Paired dashes become parentheses; headings that already contain a colon take a
# comma so they do not end up with two.
sed -i '' \
  -e 's|account\*\* — the correct agentic account — after|account** (the correct agentic account) after|' \
  -e 's|(L76, local — no AWS)|(L76, local, no AWS)|' \
  -e 's|Tier 20: AgentCore Platform — Cloud Catalog (2026-06-02 session) — live AWS|Tier 20: AgentCore Platform, Cloud Catalog (2026-06-02 session), live AWS|' \
  -e 's|increment (2026-06-02) — DONE|increment (2026-06-02), DONE|' \
  -e 's|(L77-93) — DONE|(L77-93), DONE|' \
  -e 's|Tier 22: Platform Convergence — post-v1.48|Tier 22: Platform Convergence, post-v1.48|' \
  -e 's|Tier 19: State, Control \& Token Economics (2026-06-02 session) — Gemini-verified|Tier 19: State, Control \& Token Economics (2026-06-02 session), Gemini-verified|' \
  LEARNING_PLAN.md

# ------------------------------------------------------------------ bulk pass
# Every remaining em-dash is a spaced definition dash in a table cell, link list
# or heading, where a colon is the right replacement.
sed -i '' 's| — |: |g' CLAUDE.md LEARNING_PLAN.md NEXT_STEPS_PLAN.md

# ------------------------------------------------------- ASCII art width fix
# The bulk pass shortened one boxed diagram line by a character; restore the
# column so the box still lines up.
sed -i '' 's;^|     (serve_ag_ui: native)        |$;|     (serve_ag_ui: native)         |;' LEARNING_PLAN.md

echo "remaining em-dashes:"
for f in CLAUDE.md LEARNING_PLAN.md NEXT_STEPS_PLAN.md; do
  printf '  %-24s %s\n' "$f" "$(grep -c '—' "$f" || true)"
done

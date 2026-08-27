#!/bin/sh
# Create the two GitHub Environments release.yml expects.
#
# `pypi` carries a required reviewer, which the PyPA guide states as an obligation:
# "For security reasons, you must require manual approval on each run for the pypi
# environment." That approval gate is the only thing standing between a tag push and an
# irreversible upload, since a PyPI version cannot be reused once published.
#
# `testpypi` deliberately has NO reviewer. It runs first in the workflow and exists to
# catch a bad build before the gated step, so gating it too would just train the habit
# of clicking approve twice.
#
# A named script rather than ad-hoc curl so the settings are reviewable and re-runnable,
# and so the reviewer id is visible rather than buried in shell history.
#
#   sh _sandbox/setup_release_environments.sh

set -eu

REPO=snymanpaul/aws_agent_1
REVIEWER_ID=5826275   # snymanpaul, from `gh api user`

echo "creating environment: testpypi (no approval gate, runs first)"
gh api -X PUT "repos/$REPO/environments/testpypi" --silent

echo "creating environment: pypi (required reviewer: $REVIEWER_ID)"
# -F sends typed values (integer/bool), -f sends strings. wait_timer and the reviewer id
# must be integers, so both use -F; the API rejects "0" as a string.
gh api -X PUT "repos/$REPO/environments/pypi" \
  -F "wait_timer=0" \
  -F "prevent_self_review=false" \
  -f "reviewers[][type]=User" \
  -F "reviewers[][id]=$REVIEWER_ID" \
  --silent

echo
echo "verifying:"
gh api "repos/$REPO/environments" -q '.environments[] | "  \(.name)"'
echo
echo "protection rules on pypi:"
gh api "repos/$REPO/environments/pypi" \
  -q '.protection_rules[] | "  type=\(.type) reviewers=\([.reviewers[]?.reviewer.login] | join(","))"'
echo "protection rules on testpypi:"
gh api "repos/$REPO/environments/testpypi" \
  -q 'if (.protection_rules | length) == 0 then "  none (intended)" else (.protection_rules[] | "  type=\(.type)") end'

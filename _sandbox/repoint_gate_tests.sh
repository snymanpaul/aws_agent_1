#!/bin/sh
# NOTE: the perl regex in this script did NOT match and the repoint was done by hand
# with explicit edits instead. Kept as the record of an approach that failed: a
# multiline regex over a code shape is more fragile than three targeted edits.
# Replace the importlib-by-path shims in the three gate test files with real imports.
#
# The shims existed for one reason: tools/__init__.py imported models.py, which imported
# strands, so `from tools import no_sim_check` dragged the whole SDK into a test of a
# string scanner. Now that the gates are their own zero-dependency package, that reason
# is gone and the tests can import the way any consumer would.
#
# Run: sh repoint_gate_tests.sh <package-root>
set -eu
PKG="${1:?usage: repoint_gate_tests.sh <package-root>}"
cd "$PKG/tests"

python_shim_removed() {
  # $1 = file, $2 = alias, $3 = module name
  perl -0pi -e "s/^import importlib\.util\n//m" "$1"
  perl -0pi -e "s/^REPO_ROOT = pathlib\.Path\(__file__\)\.resolve\(\)\.parents\[1\]\n.*?_uut\", [A-Z_]+_PATH\)\n    module = importlib\.util\.module_from_spec\(spec\)\n    spec\.loader\.exec_module\(module\)\n    return module\n\n\n$2 = _load_[a-z_]+\(\)\n/from agent_build_gates import $3 as $2\n/s" "$1"
}

python_shim_removed test_no_sim_check.py nsc no_sim_check
python_shim_removed test_eval_harness.py eh eval_harness
python_shim_removed test_ship_gate.py sg ship_gate

echo "repointed:"
grep -n 'from agent_build_gates import' test_no_sim_check.py test_eval_harness.py test_ship_gate.py

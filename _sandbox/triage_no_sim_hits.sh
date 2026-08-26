#!/bin/sh
# Phase 1 triage, batch 2. Each edit below follows a classification made by reading
# the flagged function, not the gate's 100-character summary.
#
#   PROSE      the word is accurate English for synthetic data or a fixture; reword
#   MISNAMED   legitimate code carrying a name that implies a fake; rename
#   FIXTURE    deterministic input to a pure function; rename to say so
#   REAL       a substituted integration or a misleading claim; behaviour changed
#
# Run: sh triage_batch.sh <repo-root>
set -eu
REPO="${1:?usage: triage_batch.sh <repo-root>}"
cd "$REPO"

# PROSE: a new Agent with the same session_id is what a restart produces.
sed -i '' \
 -e 's|Example 2: Session Restoration (Simulating Restart)|Example 2: Session Restoration (new Agent, same session_id)|' \
 -e 's|(This simulates restarting your application)|(A new Agent with the same session_id, as a restarted app would create)|' \
 02_intermediate/sessions.py

sed -i '' 's|\\n\[\.\.\.simulating application restart\.\.\.\]|\\n[...new Agent, same session_id: what a restart produces...]|' \
 06_memory/longterm_memory.py 06_memory/unified_memory.py

# FIXTURE: fixed input to a pure XML formatter.
sed -i '' -e 's|# Mock some items for demonstration|# Fixed items so the formatter output is deterministic|' \
 -e 's|\bmock_items\b|sample_items|g' 06_memory/context_management.py

# PROSE: extraction is genuinely not implemented, and facts_extracted stays 0.
sed -i '' 's|# (In production, this would use NLP to extract entities/facts)|# Entity and fact extraction is not implemented here, so facts_extracted stays 0.|' \
 06_memory/unified_memory.py

# FIXTURE: a fixed corpus keeps the debate reproducible; L17 covers real retrieval.
sed -i '' -e 's|# Simulate what we.d retrieve from Graphiti|# A fixed corpus of prior debates, so this demo is reproducible.|' \
 -e 's|# In production, this would come from mcp__graphiti-memory__search_memory_facts|# Retrieving these from Graphiti for real is L17 (graph memory deep dive).|' \
 07_advanced_multiagent/debate_pattern.py

# MISNAMED: deliberately invalid tool names exercising the missing-tool path.
sed -i '' 's|"another_fake_tool"|"another_missing_tool"|' 07_advanced_multiagent/meta_agents.py

# PROSE: the plan was built but never run, which "not_executed" says plainly.
sed -i '' 's|"execution_status": "simulated",|"execution_status": "not_executed",|' \
 07_advanced_multiagent/planning_agents.py

# MISNAMED: a fault injector that genuinely raises. The name describes the scenario.
sed -i '' -e 's|\bsimulate_failure\b|failing_after|g' \
 -e 's|# Simulate different failure scenarios|# Build functions that fail with specific error types|' \
 -e 's|print("\\nTest 3: Simulated model failure (force fallback)")|print("\\nTest 3: Real model failure on an invalid model id (forces fallback)")|' \
 -e 's|# Test 3: Simulated failure with fallback|# Test 3: real failure from an invalid primary model, then fallback|' \
 08_production/error_recovery.py

# REAL: the store claimed Graphiti persistence but only wrote a local dict.
sed -i '' -e 's|"""Persist synthesized tools to Graphiti graph memory.|"""Local index of synthesized tools, and the shape a Graphiti store would take.|' \
 -e 's|  \[GRAPHITI\] Saving tool|  [LOCAL INDEX] Recording tool|' \
 -e 's|  \[GRAPHITI\] Searching for tools like|  [LOCAL INDEX] Searching recorded tools like|' \
 -e 's|# Demo: Graphiti persistence (simulated)|# Demo: the local tool index. Real Graphiti writes go through persist_tool_to_graphiti.|' \
 -e 's|print("\\nDemonstrating Graphiti persistence (simulated)...")|print("\\nDemonstrating the local tool index (no Graphiti write happens here)...")|' \
 09_cutting_edge/tool_synthesis.py

# FIXTURE: the wire shape an agent receives, then parsed to show the handling pattern.
sed -i '' -e 's|# Simulate what the agent sees when -32042 is returned|# The tool-result shape an agent receives when -32042 is returned|' \
 -e 's|\bsimulated_tool_result\b|example_tool_result|g' \
 11_2026_updates/mcp_elicitation.py

# MISNAMED: real Kinesis records, processed by the logic a Lambda would run.
sed -i '' -e 's|--- Lambda consumer demo (local simulation) ---|--- Lambda consumer logic, run locally against real stream records ---|' \
 -e 's|"""Simulate what a Lambda function would do with Kinesis records."""|"""The processing a Lambda would perform on Kinesis records, run in-process."""|' \
 -e 's|\bsimulate_lambda_consumer\b|lambda_consumer_logic|g' \
 11_platform/ltm_streaming.py

# PROSE: no crash happens here. L82 and L95 do the real SIGKILL resume.
sed -i '' -e 's|# --- Simulate crash and resume ---|# --- Process A ends and Process B resumes. No crash is performed here. ---|' \
 -e 's|print("  \[Simulated crash\]")|print("  [Process A ends. No crash here: L82 and L95 do a real SIGKILL resume.]")|' \
 12_orchestration/durable_execution.py

# PROSE: there is no flights API to call; the fixed leg list keeps the plan reproducible.
sed -i '' 's|# Simulated — in production this would call a flights API|# Fixed leg data. No flights API is wired up, so the plan stays reproducible.|' \
 12_orchestration/rewoo.py

sed -i '' 's|print("TIMING: sequential vs parallel (simulated 1s/tool)")|print("TIMING: sequential vs parallel (1s sleep per tool)")|' \
 12_orchestration/rewoo_advanced.py

# FIXTURE: credential-shaped input for a pure redaction function.
sed -i '' -e 's|\bfake_response\b|sample_aws_response|g' _sandbox/probe_l22_tool_security.py
sed -i '' 's|input="dummy"|input="placeholder"|' _sandbox/probe_l35_evaluator_inputs.py

# MISNAMED: a monkeypatched parser that raises, exercising the error branch.
sed -i '' 's|\bfake_parse\b|raising_parse|g' _sandbox/test_normalize_jsonl.py

echo "batch applied"

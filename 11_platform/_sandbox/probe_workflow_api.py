"""
Probe: Validate workflow tool API before writing L31.

Checks:
1. Import path for workflow tool
2. Direct agent.tool.workflow() call vs natural language invocation
3. What response looks like (dict structure)
4. That model_provider=None falls back to parent agent model

Run: uv run python 11_platform/_sandbox/probe_workflow_api.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands import Agent
from strands_tools import workflow
from tools import get_model

model = get_model("haiku")

agent = Agent(model=model, tools=[workflow], callback_handler=None)

# --- Probe 1: create a minimal 2-task workflow ---
print("=== Probe 1: create workflow ===")
result = agent.tool.workflow(
    action="create",
    workflow_id="probe_test_l31",
    tasks=[
        {
            "task_id": "step_a",
            "description": "Reply with the single word: ALPHA",
            "priority": 5,
        },
        {
            "task_id": "step_b",
            "description": "Reply with the single word: BETA",
            "dependencies": ["step_a"],
            "priority": 4,
        },
    ],
)
print(f"type: {type(result)}")
print(f"keys: {list(result.keys()) if isinstance(result, dict) else 'not a dict'}")
if isinstance(result, dict):
    content = result.get("content", [])
    for item in content:
        print(item.get("text", "")[:300])

# --- Probe 2: start and let it execute ---
print("\n=== Probe 2: start workflow ===")
result = agent.tool.workflow(action="start", workflow_id="probe_test_l31")
if isinstance(result, dict):
    content = result.get("content", [])
    for item in content:
        print(item.get("text", "")[:300])

# --- Probe 3: check status ---
print("\n=== Probe 3: status ===")
result = agent.tool.workflow(action="status", workflow_id="probe_test_l31")
if isinstance(result, dict):
    content = result.get("content", [])
    for item in content:
        print(item.get("text", "")[:500])

# --- Probe 4: list all workflows ---
print("\n=== Probe 4: list ===")
result = agent.tool.workflow(action="list")
if isinstance(result, dict):
    content = result.get("content", [])
    for item in content:
        print(item.get("text", "")[:300])

# --- Probe 5: delete ---
print("\n=== Probe 5: delete ===")
result = agent.tool.workflow(action="delete", workflow_id="probe_test_l31")
if isinstance(result, dict):
    content = result.get("content", [])
    for item in content:
        print(item.get("text", ""))

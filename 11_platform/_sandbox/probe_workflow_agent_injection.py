"""
Probe: Does agent.tool.workflow() properly inject the 'agent' parameter?
When called directly (vs via LLM tool use), is 'agent' populated?

Also: does the workflow hang on task failure due to dep loop?

Run: uv run python 11_platform/_sandbox/probe_workflow_agent_injection.py
"""

import sys
import os
import logging

# Enable WARNING logging to see what's happening
logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s: %(message)s")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands import Agent, tool
from strands_tools import workflow
from tools import get_model

# Instrument the workflow function to capture the 'agent' parameter
original_workflow = workflow.__wrapped__ if hasattr(workflow, '__wrapped__') else None

# Check agent injection by wrapping
@tool
def check_agent_injection(dummy: str = "x") -> str:
    """Dummy tool just to compare parameter injection."""
    return f"dummy called: {dummy}"

model = get_model("haiku")
agent = Agent(model=model, tools=[workflow, check_agent_injection], callback_handler=None)

# --- Probe: inspect what happens when we call agent.tool.workflow ---
print("=== Checking agent parameter injection ===")

# Monkeypatch _create_task_agent to log what model_provider it sees
from strands_tools import workflow as wf_module
import strands_tools.workflow as wf_pkg

# Patch to log
original_create = wf_pkg.WorkflowManager._create_task_agent

def patched_create(self, task):
    mp = task.get("model_provider")
    pa = self.parent_agent
    print(f"  _create_task_agent: model_provider={mp!r}, parent_agent={type(pa).__name__ if pa else None}")
    if pa is not None:
        print(f"    parent_agent.model type: {type(pa.model).__name__}")
    return original_create(self, task)

wf_pkg.WorkflowManager._create_task_agent = patched_create

# Also patch WorkflowManager.__init__ to log what parent_agent is received
original_init = wf_pkg.WorkflowManager.__init__

def patched_init(self, parent_agent=None):
    print(f"  WorkflowManager.__init__: parent_agent={type(parent_agent).__name__ if parent_agent else None}")
    original_init(self, parent_agent)

wf_pkg.WorkflowManager.__init__ = patched_init

# Reset the global manager to force re-init
wf_pkg._manager = None

print("\n--- Create workflow ---")
result = agent.tool.workflow(
    action="create",
    workflow_id="probe_inject_test",
    tasks=[
        {
            "task_id": "only_task",
            "description": "Reply with just the word: OK",
            "priority": 5,
        },
    ],
)
for item in result.get("content", []):
    print(item.get("text", ""))

print("\n--- Start workflow (should call _create_task_agent) ---")
result = agent.tool.workflow(action="start", workflow_id="probe_inject_test")
for item in result.get("content", []):
    print(item.get("text", "")[:300])

print("\n--- Delete ---")
result = agent.tool.workflow(action="delete", workflow_id="probe_inject_test")
for item in result.get("content", []):
    print(item.get("text", ""))

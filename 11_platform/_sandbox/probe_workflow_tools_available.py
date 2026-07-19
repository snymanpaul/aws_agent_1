"""
Probe: What strands_tools are importable in this env?
Also test: can a task with "tools": ["nonexistent"] get no tools (avoid workflow inheritance)?

Run: uv run python 11_platform/_sandbox/probe_workflow_tools_available.py
"""

import sys
import os
import logging
logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Check what's importable from strands_tools
import importlib
import pkgutil
import strands_tools

print("strands_tools available tools:")
for name, mod in sorted(vars(strands_tools).items()):
    if not name.startswith("_") and callable(mod):
        print(f"  {name}")

# Try specific tools that might be useful
for tool_name in ["calculator", "python_repl", "shell", "file_read", "file_write", "retrieve"]:
    try:
        mod = importlib.import_module(f"strands_tools.{tool_name}")
        print(f"  strands_tools.{tool_name}: importable")
    except ImportError as e:
        print(f"  strands_tools.{tool_name}: NOT available — {e}")

print()
print("=== Testing: task with tools=['__no_tool__'] gets no tools ===")
from strands import Agent, tool
from strands_tools import workflow
from tools import get_model

# Patch _create_task_agent to report what tools task gets
import strands_tools.workflow as wf_pkg
original = wf_pkg.WorkflowManager._create_task_agent
def patched(self, task):
    agent_obj = original(self, task)
    tool_names = list(agent_obj.tool_registry.registry.keys()) if hasattr(agent_obj, 'tool_registry') else []
    print(f"  Task '{task['task_id']}' tools: {tool_names}")
    return agent_obj
wf_pkg.WorkflowManager._create_task_agent = patched
wf_pkg._manager = None

model = get_model("haiku")
parent_agent = Agent(model=model, tools=[workflow], callback_handler=None)

# Test with no "tools" key → should inherit all (including workflow)
print("\n1. No 'tools' key specified:")
result = parent_agent.tool.workflow(
    action="create",
    workflow_id="probe_tools_test_1",
    tasks=[{"task_id": "t1", "description": "Reply: DONE", "priority": 5}]
)
parent_agent.tool.workflow(action="start", workflow_id="probe_tools_test_1")
parent_agent.tool.workflow(action="delete", workflow_id="probe_tools_test_1")

# Test with "tools": [] → should also inherit all (empty list is falsy)
wf_pkg._manager = None
print("\n2. 'tools': [] (empty list):")
result = parent_agent.tool.workflow(
    action="create",
    workflow_id="probe_tools_test_2",
    tasks=[{"task_id": "t2", "description": "Reply: DONE", "priority": 5, "tools": []}]
)
parent_agent.tool.workflow(action="start", workflow_id="probe_tools_test_2")
parent_agent.tool.workflow(action="delete", workflow_id="probe_tools_test_test_2")

# Test with "tools": ["__none__"] → should get empty tools (warning logged)
wf_pkg._manager = None
print("\n3. 'tools': ['__none__'] (non-existent tool name):")
result = parent_agent.tool.workflow(
    action="create",
    workflow_id="probe_tools_test_3",
    tasks=[{"task_id": "t3", "description": "Reply: DONE", "priority": 5, "tools": ["__none__"]}]
)
parent_agent.tool.workflow(action="start", workflow_id="probe_tools_test_3")
parent_agent.tool.workflow(action="delete", workflow_id="probe_tools_test_3")

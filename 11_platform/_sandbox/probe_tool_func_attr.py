"""
Probe: What attribute exposes the raw callable on a @tool-decorated function?
Run: uv run python 11_platform/_sandbox/probe_tool_func_attr.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands import tool

@tool
def my_tool(x: int) -> int:
    """Double x."""
    return x * 2

print(f"type: {type(my_tool)}")
print(f"attrs: {[a for a in dir(my_tool) if not a.startswith('__')]}")
# try calling it directly
try:
    print(f"direct call my_tool(3): {my_tool(3)}")
except Exception as e:
    print(f"direct call failed: {e}")

"""Smoke-import the upgraded SDK stack and print the versions that resolved.

Run: uv run python _sandbox/probe_upgrade_2026-09-10_imports.py
"""
from importlib.metadata import version

import a2a  # noqa: F401
import bedrock_agentcore  # noqa: F401
import mcp  # noqa: F401
import strands_tools  # noqa: F401
from strands import Agent  # noqa: F401
from strands.models.openai import OpenAIModel  # noqa: F401

for dist in (
    "strands-agents", "strands-agents-tools", "strands-agents-evals",
    "bedrock-agentcore", "mcp", "a2a-sdk", "ag-ui-strands", "strands-shell",
):
    print(f"{dist:<28} {version(dist)}")
print("imports OK")

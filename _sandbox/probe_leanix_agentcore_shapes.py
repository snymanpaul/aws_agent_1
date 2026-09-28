"""Probe: input shapes for a direct-code AgentCore runtime (LeanIX discovery test agent).

Reads the botocore service model only. No AWS call, no credentials needed.

    uv run python _sandbox/probe_leanix_agentcore_shapes.py
"""

import boto3


def walk(shape, depth=0, seen=None, max_depth=4):
    seen = seen or set()
    pad = "  " * depth
    if shape.name in seen or depth > max_depth:
        print(f"{pad}... ({shape.name})")
        return
    seen = seen | {shape.name}
    if shape.type_name == "structure":
        req = set(shape.required_members)
        for name, member in shape.members.items():
            extra = f" enum={member.enum}" if getattr(member, "enum", None) else ""
            print(f"{pad}{name}{' *' if name in req else ''}: {member.type_name}{extra}")
            if member.type_name in ("structure", "list", "map"):
                walk(member, depth + 1, seen, max_depth)
    elif shape.type_name == "list":
        walk(shape.member, depth, seen, max_depth)
    elif shape.type_name == "map":
        walk(shape.value, depth, seen, max_depth)


model = boto3.session.Session().client("bedrock-agentcore-control", region_name="us-east-1").meta.service_model
for op in ("CreateAgentRuntime", "DeleteAgentRuntime"):
    print(f"== {op} input")
    walk(model.operation_model(op).input_shape)

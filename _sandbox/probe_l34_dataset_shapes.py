"""Probe: bedrock-agentcore-control dataset/evaluation operation shapes (L34).

Enumerates the dataset + evaluation operations and the CreateDataset input shape
so the L34 DatasetClient extension is written against the real API, not a guess.
    AWS_PROFILE=... uv run python _sandbox/probe_l34_dataset_shapes.py
"""
import os
import boto3

AWS_PROFILE = os.environ.get("AWS_PROFILE")
REGION = "us-east-1"

session = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)
client = session.client("bedrock-agentcore-control")
sm = client.meta.service_model

ops = sorted(
    o for o in sm.operation_names
    if any(k in o.lower() for k in ("dataset", "evaluat", "job"))
)
print(f"=== dataset/eval/job operations ({REGION}) ===")
for o in ops:
    print(f"  {o}")


def dump_shape(op_name: str) -> None:
    try:
        op = sm.operation_model(op_name)
    except Exception as e:  # noqa: BLE001
        print(f"\n[{op_name}] not found: {e}")
        return
    inp = op.input_shape
    print(f"\n=== {op_name} input ===")
    if inp is None:
        print("  (no input)")
        return
    required = set(inp.required_members or [])
    for name, shape in inp.members.items():
        mark = "*" if name in required else " "
        enum = f" enum={shape.enum}" if getattr(shape, "enum", None) else ""
        members = ""
        if shape.type_name == "structure":
            members = f" {{{', '.join(shape.members)}}}"
        print(f"  {mark} {name}: {shape.type_name}{enum}{members}")


for candidate in ("CreateDataset", "GetDataset", "StartEvaluationJob",
                  "CreateEvaluationJob", "StartEvaluation"):
    if candidate in sm.operation_names:
        dump_shape(candidate)

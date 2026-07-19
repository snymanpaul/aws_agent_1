"""Probe: dataset example structure + how datasets connect to evaluation (L34)."""
import os
import boto3

session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name="us-east-1")
sm = session.client("bedrock-agentcore-control").meta.service_model


def drill(shape, depth=0, seen=None, max_depth=4):
    seen = seen or set()
    pad = "  " * depth
    if shape is None or depth > max_depth:
        return
    if shape.type_name == "structure":
        for n, s in shape.members.items():
            req = "*" if n in (shape.required_members or []) else " "
            enum = f" enum={s.enum}" if getattr(s, "enum", None) else ""
            print(f"{pad}{req} {n}: {s.type_name}{enum}")
            key = (n, s.type_name)
            if key not in seen and s.type_name in ("structure", "list"):
                seen.add(key)
                drill(s, depth + 1, seen, max_depth)
    elif shape.type_name == "list":
        print(f"{pad}  [item]: {shape.member.type_name}")
        drill(shape.member, depth + 1, seen, max_depth)


print("=== CreateDataset.source (inlineExamples item structure) ===")
src = sm.operation_model("CreateDataset").input_shape.members["source"]
drill(src, 1)

print("\n=== AddDatasetExamples input ===")
drill(sm.operation_model("AddDatasetExamples").input_shape, 1)

# Which operations reference a dataset id/arn (the eval connection)?
print("\n=== ops whose input mentions 'dataset' (besides Dataset CRUD) ===")
for op_name in sm.operation_names:
    inp = sm.operation_model(op_name).input_shape
    if inp and inp.type_name == "structure":
        hits = [m for m in inp.members if "dataset" in m.lower()]
        if hits and "Dataset" not in op_name:
            print(f"  {op_name}: {hits}")

print("\n=== CreateOnlineEvaluationConfig input (does it take a dataset?) ===")
drill(sm.operation_model("CreateOnlineEvaluationConfig").input_shape, 1, max_depth=2)

"""Drill into nested structures: sessionSpans, llmAsAJudge sub-shapes."""
import boto3
import json

ctrl = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
runtime = boto3.client("bedrock-agentcore", region_name="us-east-1")


def drill(shape, indent=0):
    pad = "  " * indent
    for k, v in shape.members.items():
        req = "(required)" if k in (shape.required_members or []) else ""
        print(f"{pad}{k}: {v.type_name} {req}")
        if v.type_name == "structure":
            drill(v, indent + 1)
        elif v.type_name == "list":
            print(f"{pad}  [member]: {v.member.type_name}")
            if v.member.type_name == "structure":
                drill(v.member, indent + 2)
        elif v.type_name == "map":
            print(f"{pad}  [key]: {v.key.type_name}  [value]: {v.value.type_name}")


print("=== runtime.Evaluate full deep ===")
drill(runtime.meta.service_model.operation_model("Evaluate").input_shape)

print("\n=== CreateEvaluator.evaluatorConfig deep ===")
op = ctrl.meta.service_model.operation_model("CreateEvaluator")
drill(op.input_shape.members["evaluatorConfig"])

print("\n=== CreateOnlineEvaluationConfig.rule deep ===")
op2 = ctrl.meta.service_model.operation_model("CreateOnlineEvaluationConfig")
drill(op2.input_shape.members["rule"])

print("\n=== CreateOnlineEvaluationConfig.dataSourceConfig deep ===")
drill(op2.input_shape.members["dataSourceConfig"])

# Check what roles/permissions might be needed for online eval
print("\n=== Existing IAM roles with 'agentcore' in name ===")
iam = boto3.client("iam", region_name="us-east-1")
try:
    paginator = iam.get_paginator("list_roles")
    for page in paginator.paginate():
        for role in page["Roles"]:
            if "agentcore" in role["RoleName"].lower():
                print(f"  {role['RoleName']}")
except Exception as e:
    print(f"  {e}")

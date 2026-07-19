"""Probe AgentCore Evaluations API shapes before writing L34."""
import boto3
import json

client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")

OPS = [
    "CreateEvaluationJob",
    "GetEvaluationJob",
    "ListEvaluationJobs",
    "DeleteEvaluationJob",
    "CreateEvaluator",
    "GetEvaluator",
    "ListEvaluators",
    "DeleteEvaluator",
]

for op in OPS:
    try:
        shape = client.meta.service_model.operation_model(op).input_shape
        print(f"\n=== {op} ===")
        for k, v in shape.members.items():
            req = "(required)" if k in (shape.required_members or []) else ""
            print(f"  {k}: {v.type_name} {req}")
            if v.type_name == "structure":
                for sk, sv in v.members.items():
                    r2 = "(required)" if sk in (v.required_members or []) else ""
                    print(f"    {sk}: {sv.type_name} {r2}")
                    if sv.type_name == "structure":
                        for sk2, sv2 in sv.members.items():
                            print(f"      {sk2}: {sv2.type_name}")
            elif v.type_name == "list":
                print(f"    (member): {v.member.type_name}")
    except Exception as e:
        print(f"\n=== {op} === NOT FOUND: {e}")

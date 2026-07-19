"""Probe start_policy_generation + get_policy_generation signatures."""
import boto3

client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")

for op in ("StartPolicyGeneration", "GetPolicyGeneration", "CreatePolicy", "UpdateGateway"):
    shape = client.meta.service_model.operation_model(op).input_shape
    print(f"\n=== {op} ===")
    for k, v in shape.members.items():
        required = "(required)" if k in (shape.required_members or []) else ""
        print(f"  {k}: {v.type_name} {required}")
        if v.type_name == "structure":
            for sk, sv in v.members.items():
                print(f"    {sk}: {sv.type_name}")

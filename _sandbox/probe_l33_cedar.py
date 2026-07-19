"""Probe cedar definition structure + GetPolicyGeneration output."""
import boto3

client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")

# CreatePolicy → definition → cedar members
op = client.meta.service_model.operation_model("CreatePolicy")
cedar = op.input_shape.members["definition"].members["cedar"]
print("=== CreatePolicy.definition.cedar members ===")
for k, v in cedar.members.items():
    print(f"  {k}: {v.type_name}")

# GetPolicyGeneration output shape
print("\n=== GetPolicyGeneration OUTPUT ===")
out = client.meta.service_model.operation_model("GetPolicyGeneration").output_shape
for k, v in out.members.items():
    print(f"  {k}: {v.type_name}")
    if v.type_name == "structure":
        for sk, sv in v.members.items():
            print(f"    {sk}: {sv.type_name}")

# GetPolicy output shape
print("\n=== GetPolicy OUTPUT ===")
out2 = client.meta.service_model.operation_model("GetPolicy").output_shape
for k, v in out2.members.items():
    print(f"  {k}: {v.type_name}")
    if v.type_name == "structure":
        for sk, sv in v.members.items():
            print(f"    {sk}: {sv.type_name}")

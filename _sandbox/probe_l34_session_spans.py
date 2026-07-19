"""Probe sessionSpans structure and find the L27 CloudWatch log group."""
import boto3
import json

runtime = boto3.client("bedrock-agentcore", region_name="us-east-1")

# Try to get the sessionSpans member shape
op = runtime.meta.service_model.operation_model("Evaluate")
sess_spans = op.input_shape.members["evaluationInput"].members["sessionSpans"]
member = sess_spans.member
print("sessionSpans member type:", member.type_name)
if member.type_name == "structure":
    print("sessionSpans member members:", list(member.members.keys()))
    for k, v in member.members.items():
        req = "(required)" if k in (member.required_members or []) else ""
        print(f"  {k}: {v.type_name} {req}")
        if v.type_name == "structure":
            for sk, sv in v.members.items():
                print(f"    {sk}: {sv.type_name}")
        elif v.type_name == "list":
            print(f"    member: {v.member.type_name}")
            if v.member.type_name == "structure":
                for sk, sv in v.member.members.items():
                    print(f"      {sk}: {sv.type_name}")

# Find L27 CloudWatch log group
logs = boto3.client("logs", region_name="us-east-1")
print("\n=== CloudWatch log groups with 'agentcore' or 'l27' in name ===")
paginator = logs.get_paginator("describe_log_groups")
for page in paginator.paginate():
    for lg in page["logGroups"]:
        name = lg["logGroupName"]
        if any(x in name.lower() for x in ["agentcore", "l27", "bedrock"]):
            print(f"  {name}  ({lg.get('retentionInDays', 'no-retention')} days)")

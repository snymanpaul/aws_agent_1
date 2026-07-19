"""Probe the actual evaluation API shapes discovered from state probe."""
import boto3
import json

ctrl = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
runtime = boto3.client("bedrock-agentcore", region_name="us-east-1")

CTRL_OPS = [
    "CreateOnlineEvaluationConfig",
    "GetOnlineEvaluationConfig",
    "ListOnlineEvaluationConfigs",
    "UpdateOnlineEvaluationConfig",
    "DeleteOnlineEvaluationConfig",
    "CreateEvaluator",
    "UpdateEvaluator",
]

RUNTIME_OPS = ["Evaluate"]


def probe_shape(client, op):
    try:
        shape = client.meta.service_model.operation_model(op).input_shape
        print(f"\n=== {op} INPUT ===")
        for k, v in shape.members.items():
            req = "(required)" if k in (shape.required_members or []) else ""
            print(f"  {k}: {v.type_name} {req}")
            if v.type_name == "structure":
                for sk, sv in v.members.items():
                    r2 = "(required)" if sk in (v.required_members or []) else ""
                    print(f"    {sk}: {sv.type_name} {r2}")
                    if sv.type_name in ("structure", "list"):
                        if sv.type_name == "structure":
                            for sk2, sv2 in sv.members.items():
                                print(f"      {sk2}: {sv2.type_name}")
                        else:
                            print(f"      member: {sv.member.type_name}")
            elif v.type_name == "list":
                print(f"    member: {v.member.type_name}")
                if v.member.type_name == "structure":
                    for sk, sv in v.member.members.items():
                        r2 = "(required)" if sk in (v.member.required_members or []) else ""
                        print(f"      {sk}: {sv.type_name} {r2}")
        # Also show output shape
        out = client.meta.service_model.operation_model(op).output_shape
        if out:
            print(f"  --- OUTPUT ---")
            for k, v in out.members.items():
                print(f"  {k}: {v.type_name}")
    except Exception as e:
        print(f"\n=== {op} === ERROR: {e}")


for op in CTRL_OPS:
    probe_shape(ctrl, op)

for op in RUNTIME_OPS:
    probe_shape(runtime, op)

# Also check existing online eval configs
print("\n\n=== LIST ONLINE EVALUATION CONFIGS (live) ===")
try:
    r = ctrl.list_online_evaluation_configs()
    r.pop("ResponseMetadata", None)
    print(json.dumps(r, indent=2, default=str))
except Exception as e:
    print(f"  {e}")

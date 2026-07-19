"""Check current state of l33 engine and policy failure reason."""
import boto3
import json

client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")

engines = client.list_policy_engines().get("policyEngines", [])
for e in engines:
    eid = e["policyEngineId"]
    print(f"Engine: {e['name']} ({eid}) status={e['status']}")
    policies = client.list_policies(policyEngineId=eid).get("policies", [])
    for p in policies:
        detail = client.get_policy(policyEngineId=eid, policyId=p["policyId"])
        detail.pop("ResponseMetadata", None)
        print(f"  Policy: {p['name']} status={p['status']}")
        print(f"    statusReasons: {detail.get('statusReasons')}")
        print(f"    definition: {json.dumps(detail.get('definition'), indent=4, default=str)}")

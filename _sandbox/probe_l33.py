"""Probe existing AgentCore gateway + policy engines before writing L33."""
import boto3
import json

client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")

print("=== GATEWAY ===")
gw = client.get_gateway(gatewayIdentifier="l27agentcore-gateway-hr4f5b0f6x")
gw.pop("ResponseMetadata", None)
print(json.dumps(gw, indent=2, default=str))

print("\n=== POLICY ENGINES ===")
engines = client.list_policy_engines()
engines.pop("ResponseMetadata", None)
print(json.dumps(engines, indent=2, default=str))

print("\n=== POLICY GENERATION ASSETS (NL2Cedar inputs) ===")
try:
    assets = client.list_policy_generation_assets()
    assets.pop("ResponseMetadata", None)
    print(json.dumps(assets, indent=2, default=str))
except Exception as e:
    print(f"  (not available: {e})")

print("\n=== create_policy_engine SIGNATURE ===")
import inspect
help_text = client.meta.service_model.operation_model("CreatePolicyEngine").input_shape.members
for k, v in help_text.items():
    print(f"  {k}: {v.type_name}")

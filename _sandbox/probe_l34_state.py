"""Probe live state: existing evaluators and evaluation jobs."""
import boto3
import json

client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")

print("=== LIST EVALUATORS ===")
try:
    r = client.list_evaluators()
    r.pop("ResponseMetadata", None)
    print(json.dumps(r, indent=2, default=str))
except Exception as e:
    print(f"  not available: {e}")

print("\n=== LIST EVALUATION JOBS ===")
try:
    r = client.list_evaluation_jobs()
    r.pop("ResponseMetadata", None)
    print(json.dumps(r, indent=2, default=str))
except Exception as e:
    print(f"  not available: {e}")

# Also check if there's a bedrock-agentcore data-plane client for evals
print("\n=== bedrock-agentcore service operations (eval-related) ===")
try:
    ctrl = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
    all_ops = [op for op in dir(ctrl) if "eval" in op.lower()]
    print("  control plane ops:", all_ops)
except Exception as e:
    print(f"  {e}")

try:
    runtime = boto3.client("bedrock-agentcore", region_name="us-east-1")
    all_ops = [op for op in dir(runtime) if "eval" in op.lower()]
    print("  runtime ops:", all_ops)
except Exception as e:
    print(f"  runtime client: {e}")

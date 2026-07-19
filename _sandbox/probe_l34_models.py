"""Find accessible Bedrock foundation models for the evaluation judge."""
import boto3

bedrock = boto3.client("bedrock", region_name="us-east-1")
models = bedrock.list_foundation_models(byOutputModality="TEXT").get("modelSummaries", [])
for m in models:
    print(f"  {m['modelId']}  provider={m['providerName']}  status={m.get('modelLifecycle', {}).get('status', '?')}")

"""Probe: which Bedrock models are actually invokable in this account."""
import os
import boto3
import json

PROFILE = os.environ.get("AWS_PROFILE")
REGION  = "us-east-1"

CANDIDATES = [
    "amazon.nova-lite-v1:0",
    "amazon.nova-micro-v1:0",
    "amazon.nova-pro-v1:0",
    "amazon.titan-text-lite-v1",
    "amazon.titan-text-express-v1",
    "us.amazon.nova-lite-v1:0",
    "us.amazon.nova-micro-v1:0",
]

session = boto3.Session(profile_name=PROFILE, region_name=REGION)
br = session.client("bedrock-runtime")

def nova_body():
    return json.dumps({
        "messages": [{"role": "user", "content": [{"text": "Say hi in one word"}]}],
        "inferenceConfig": {"maxTokens": 20},
    })

def titan_body():
    return json.dumps({
        "inputText": "Say hi in one word",
        "textGenerationConfig": {"maxTokenCount": 20},
    })

BODIES = {
    "nova": nova_body,
    "titan": titan_body,
    "default": lambda: json.dumps({"messages": [{"role": "user", "content": "Say hi"}], "max_tokens": 10}),
}

for model_id in CANDIDATES:
    if "nova" in model_id:
        body_fn = BODIES["nova"]
    elif "titan" in model_id:
        body_fn = BODIES["titan"]
    else:
        body_fn = BODIES["default"]
    try:
        resp = br.invoke_model(
            modelId=model_id,
            body=body_fn(),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(resp["body"].read())
        print(f"  ✓ {model_id}: {str(result)[:100]}")
    except Exception as e:
        print(f"  ✗ {model_id}: {str(e)[:120]}")

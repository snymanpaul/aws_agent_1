"""Probe: which Bedrock models the agentic sandbox account can invoke (LeanIX discovery test).

Refuses to run unless the caller is the account named by the local environment variable
AGENTIC_SANDBOX_ACCOUNT (the id never lives in this public file), so it can never touch the
data account. One tiny Converse call per model; prints only model id + outcome.

    AWS_PROFILE=<sandbox profile> AGENTIC_SANDBOX_ACCOUNT=<id> uv run python _sandbox/probe_leanix_bedrock_access.py
"""

import os

import boto3

REGION = "us-east-1"
MODELS = ["us.anthropic.claude-haiku-4-5-20251001-v1:0", "us.amazon.nova-micro-v1:0"]

expected = os.environ.get("AGENTIC_SANDBOX_ACCOUNT")
if not expected:
    raise SystemExit("refusing: set AGENTIC_SANDBOX_ACCOUNT to the agentic sandbox account id")
account = boto3.client("sts").get_caller_identity()["Account"]
if account != expected:
    raise SystemExit(f"refusing: caller account ...{account[-4:]} is not AGENTIC_SANDBOX_ACCOUNT ...{expected[-4:]}")
print(f"account ...{account[-4:]} region {REGION}")

rt = boto3.client("bedrock-runtime", region_name=REGION)
for model_id in MODELS:
    try:
        r = rt.converse(modelId=model_id, messages=[{"role": "user", "content": [{"text": "Reply with the word ok."}]}],
                        inferenceConfig={"maxTokens": 5})
        text = r["output"]["message"]["content"][0]["text"]
        print(f"OK    {model_id}: {text!r} tokens={r['usage']['totalTokens']}")
    except Exception as exc:  # report every model's outcome, including the denied ones
        print(f"FAIL  {model_id}: {type(exc).__name__}: {str(exc)[:160]}")

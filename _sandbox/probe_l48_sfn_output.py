"""Probe: what does taskSucceededEventDetails.output actually look like for a
Bedrock-integrated Step Functions state?"""
import os
import base64
import json
import time
import uuid
import boto3

PROFILE = os.environ.get("AWS_PROFILE")
REGION  = "us-east-1"
ACCOUNT = "<data-account-id>"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/l48-probe-sfn-role"

TRUST_POLICY = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "states.amazonaws.com"},
        "Action": "sts:AssumeRole",
        "Condition": {
            "StringEquals": {"aws:SourceAccount": ACCOUNT},
            "ArnLike": {"aws:SourceArn": f"arn:aws:states:{REGION}:{ACCOUNT}:stateMachine:*"}
        }
    }]
})

BEDROCK_POLICY = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow", "Action": ["bedrock:InvokeModel"], "Resource": "*"}]
})

SM_DEF = json.dumps({
    "StartAt": "Ask",
    "States": {
        "Ask": {
            "Type": "Task",
            "Resource": "arn:aws:states:::bedrock:invokeModel",
            "Parameters": {
                "ModelId": "amazon.nova-micro-v1:0",
                "Body": {
                    "messages": [{"role": "user", "content": [{"text": "Say hi in 3 words"}]}],
                    "inferenceConfig": {"maxTokens": 20}
                },
                "ContentType": "application/json",
                "Accept": "application/json"
            },
            "End": True
        }
    }
})

session = boto3.Session(profile_name=PROFILE, region_name=REGION)
iam = session.client("iam")
sfn = session.client("stepfunctions")

# create role
role_arn = None
try:
    role_arn = iam.get_role(RoleName="l48-probe-sfn-role")["Role"]["Arn"]
    print("Role exists:", role_arn)
except Exception:
    r = iam.create_role(RoleName="l48-probe-sfn-role", AssumeRolePolicyDocument=TRUST_POLICY, Description="l48 probe role")
    role_arn = r["Role"]["Arn"]
    iam.put_role_policy(RoleName="l48-probe-sfn-role", PolicyName="p", PolicyDocument=BEDROCK_POLICY)
    print("Role created:", role_arn)
    time.sleep(20)

# create state machine
sm_name = "l48-probe-sfn"
sm_arn = None
for page in sfn.get_paginator("list_state_machines").paginate():
    for sm in page["stateMachines"]:
        if sm["name"] == sm_name:
            sm_arn = sm["stateMachineArn"]
            print("SM exists:", sm_arn)

if sm_arn is None:
    sm_arn = sfn.create_state_machine(name=sm_name, definition=SM_DEF, roleArn=role_arn, type="STANDARD")["stateMachineArn"]
    print("SM created:", sm_arn)

# run
exec_arn = sfn.start_execution(stateMachineArn=sm_arn, name=f"probe-{uuid.uuid4().hex[:8]}", input="{}")["executionArn"]
print("Execution started:", exec_arn)
for _ in range(30):
    status = sfn.describe_execution(executionArn=exec_arn)["status"]
    if status in ("SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"):
        print("Status:", status)
        break
    time.sleep(3)

# inspect raw output
history = sfn.get_execution_history(executionArn=exec_arn, maxResults=50)["events"]
for ev in history:
    if ev["type"] == "TaskSucceeded":
        raw = ev["taskSucceededEventDetails"]["output"]
        print("\n--- RAW output (first 500 chars) ---")
        print(raw[:500])
        print("\n--- json.loads(raw) keys ---")
        outer = json.loads(raw)
        print("Keys:", list(outer.keys()))
        for k, v in outer.items():
            vstr = str(v)
            print(f"  {k}: (type={type(v).__name__}) {vstr[:200]}")
        print("\n--- Body decode attempt ---")
        body_raw = outer.get("Body", "")
        print("Body type:", type(body_raw).__name__)
        print("Body[:200]:", str(body_raw)[:200])
        if isinstance(body_raw, str):
            try:
                decoded = base64.b64decode(body_raw).decode("utf-8")
                print("base64 decoded:", decoded[:300])
                body = json.loads(decoded)
                print("parsed:", json.dumps(body)[:300])
            except Exception as e:
                print("base64 decode failed:", e)
                try:
                    body = json.loads(body_raw)
                    print("direct json parse:", json.dumps(body)[:300])
                except Exception as e2:
                    print("direct json parse also failed:", e2)
        elif isinstance(body_raw, dict):
            print("Body is already a dict:", json.dumps(body_raw)[:300])

# cleanup
sfn.delete_state_machine(stateMachineArn=sm_arn)
iam.delete_role_policy(RoleName="l48-probe-sfn-role", PolicyName="p")
iam.delete_role(RoleName="l48-probe-sfn-role")
print("\nCleaned up.")

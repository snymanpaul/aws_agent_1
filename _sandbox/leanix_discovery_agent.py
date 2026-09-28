"""Deploy, invoke and tear down one AgentCore Runtime agent for the SAP LeanIX discovery test.

Runs only in the agentic sandbox account, us-east-1. The account id comes from the local
environment variable AGENTIC_SANDBOX_ACCOUNT (never from this file, which is public); the
script refuses to run when it is unset or does not match the caller, so it cannot touch the
live data science account.

TEARDOWN CHECKLIST (written before anything is created; `teardown` does all of it and
then lists each resource type again to prove it is gone):
  1. AgentCore runtime `leanix_discovery_agent`      delete, wait until the listing is empty
  2. Log groups /aws/bedrock-agentcore/runtimes/<id>*  created by the service; delete
  3. Workload identities named leanix_discovery_agent* created by the service; delete
  4. IAM role LeanixDiscoveryAgentRuntimeRole          delete inline policy, then role
  5. S3 bucket leanix-discovery-agent-code-<account>   delete objects, then bucket
  6. Local state file ~/.aws/leanix_discovery_agent.state.json (outside the repo: holds ARNs)

    AWS_PROFILE=<profile> AGENTIC_SANDBOX_ACCOUNT=<id> uv run python _sandbox/leanix_discovery_agent.py <cmd>
    <cmd> is one of: deploy, invoke, status, teardown
"""

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

import boto3

REGION = "us-east-1"
NAME = "leanix_discovery_agent"
ROLE = "LeanixDiscoveryAgentRuntimeRole"
POLICY = "invoke-bedrock-and-write-logs"
KEY = f"{NAME}/code.zip"
SRC = pathlib.Path(__file__).with_name(NAME)
STATE = pathlib.Path.home() / ".aws" / f"{NAME}.state.json"
TAGS = {"purpose": "leanix-discovery-test", "owner": "paul", "created": "2026-09-28",
        "teardown": "_sandbox/leanix_discovery_agent.py teardown"}


def mask(s):
    return re.sub(r"\d{8}(\d{4})", r"********\1", str(s))


def account():
    expected = os.environ.get("AGENTIC_SANDBOX_ACCOUNT")
    if not expected:
        raise SystemExit("refusing: set AGENTIC_SANDBOX_ACCOUNT to the agentic sandbox account id")
    acct = boto3.client("sts").get_caller_identity()["Account"]
    if acct != expected:
        raise SystemExit(f"refusing: caller account ...{acct[-4:]} is not AGENTIC_SANDBOX_ACCOUNT ...{expected[-4:]}")
    return acct


def bucket_name(acct):
    return f"leanix-discovery-agent-code-{acct}"


def build_zip(out):
    """Linux ARM64 wheels at the zip root next to main.py, as the starter toolkit packages it."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["uv", "pip", "install", "--target", tmp, "--python-version", "3.12",
                        "--python-platform", "aarch64-manylinux2014", "--only-binary", ":all:",
                        "-r", str(SRC / "requirements.txt")], check=True, capture_output=True, text=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for p in pathlib.Path(tmp).rglob("*"):
                if p.is_file() and "__pycache__" not in p.parts:
                    z.write(p, p.relative_to(tmp))
            z.write(SRC / "main.py", "main.py")
    return out


def deploy():
    acct = account()
    s3, iam = boto3.client("s3", region_name=REGION), boto3.client("iam")
    ctl = boto3.client("bedrock-agentcore-control", region_name=REGION)
    bucket = bucket_name(acct)

    s3.create_bucket(Bucket=bucket)
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in TAGS.items()]})
    zpath = build_zip(pathlib.Path(tempfile.gettempdir()) / f"{NAME}.zip")
    print(f"zip {zpath.stat().st_size / 1e6:.1f} MB")
    s3.upload_file(str(zpath), bucket, KEY)

    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"}, "Action": "sts:AssumeRole",
        "Condition": {"StringEquals": {"aws:SourceAccount": acct},
                      "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{REGION}:{acct}:*"}}}]}
    perms = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
         "Resource": ["arn:aws:bedrock:*::foundation-model/*", f"arn:aws:bedrock:*:{acct}:inference-profile/*"]},
        {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
                                       "logs:DescribeLogGroups", "logs:DescribeLogStreams"],
         "Resource": f"arn:aws:logs:{REGION}:{acct}:log-group:/aws/bedrock-agentcore/runtimes/*"}]}
    role_arn = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust),
                               Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()])["Role"]["Arn"]
    iam.put_role_policy(RoleName=ROLE, PolicyName=POLICY, PolicyDocument=json.dumps(perms))
    time.sleep(15)  # ponytail: fixed wait for IAM propagation; retry on AccessDenied if it proves short

    r = ctl.create_agent_runtime(
        agentRuntimeName=NAME, description="Test agent for SAP LeanIX AgentCore discovery",
        agentRuntimeArtifact={"codeConfiguration": {"code": {"s3": {"bucket": bucket, "prefix": KEY}},
                                                    "runtime": "PYTHON_3_12", "entryPoint": ["main.py"]}},
        roleArn=role_arn, networkConfiguration={"networkMode": "PUBLIC"},
        protocolConfiguration={"serverProtocol": "HTTP"}, tags=TAGS)
    state = {"runtimeId": r["agentRuntimeId"], "runtimeArn": r["agentRuntimeArn"], "bucket": bucket,
             "role": ROLE, "region": REGION}
    STATE.write_text(json.dumps(state, indent=2))
    os.chmod(STATE, 0o600)
    print(f"created runtime {r['agentRuntimeId']} status={r['status']}")
    wait_ready(ctl, r["agentRuntimeId"])


def wait_ready(ctl, rid, timeout=600):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        rt = ctl.get_agent_runtime(agentRuntimeId=rid)
        if rt["status"] not in ("CREATING", "UPDATING"):
            print(f"runtime {rid} status={rt['status']} {mask(rt.get('failureReason', ''))}")
            return rt["status"]
        time.sleep(10)
    raise SystemExit(f"runtime {rid} not ready after {timeout}s")


def invoke():
    account()
    state = json.loads(STATE.read_text())
    dp = boto3.client("bedrock-agentcore", region_name=REGION)
    r = dp.invoke_agent_runtime(agentRuntimeArn=state["runtimeArn"], runtimeSessionId=f"leanix-test-{uuid.uuid4()}",
                                payload=json.dumps({"prompt": "What are you for?"}).encode())
    print(f"invoke -> {r['response'].read().decode()[:300]}")


def status():
    account()
    ctl = boto3.client("bedrock-agentcore-control", region_name=REGION)
    for rt in ctl.list_agent_runtimes()["agentRuntimes"]:
        print(mask(f"{rt['agentRuntimeName']} {rt['agentRuntimeId']} {rt['status']} {rt['agentRuntimeArn']}"))


def teardown():
    acct = account()
    ctl = boto3.client("bedrock-agentcore-control", region_name=REGION)
    logs, iam, s3 = boto3.client("logs", region_name=REGION), boto3.client("iam"), boto3.resource("s3")

    ids = [rt["agentRuntimeId"] for rt in ctl.list_agent_runtimes()["agentRuntimes"] if rt["agentRuntimeName"] == NAME]
    for rid in ids:
        ctl.delete_agent_runtime(agentRuntimeId=rid)
        print(f"1. deleting runtime {rid}")
    for _ in range(60):
        if not any(rt["agentRuntimeName"] == NAME for rt in ctl.list_agent_runtimes()["agentRuntimes"]):
            break
        time.sleep(10)
    for rid in ids:
        for g in logs.describe_log_groups(logGroupNamePrefix=f"/aws/bedrock-agentcore/runtimes/{rid}")["logGroups"]:
            logs.delete_log_group(logGroupName=g["logGroupName"])
            print(f"2. deleted log group {g['logGroupName']}")
    for w in ctl.list_workload_identities().get("workloadIdentities", []):
        if w["name"].startswith(NAME):
            ctl.delete_workload_identity(name=w["name"])
            print(f"3. deleted workload identity {w['name']}")
    try:
        iam.delete_role_policy(RoleName=ROLE, PolicyName=POLICY)
        iam.delete_role(RoleName=ROLE)
        print(f"4. deleted role {ROLE}")
    except iam.exceptions.NoSuchEntityException:
        print(f"4. role {ROLE} already absent")
    b = s3.Bucket(bucket_name(acct))
    if b.creation_date:
        b.object_versions.delete()
        b.objects.all().delete()
        b.delete()
        print("5. deleted code bucket")
    STATE.unlink(missing_ok=True)
    print("6. removed local state file")
    verify(acct)


def role_exists(iam):
    try:
        iam.get_role(RoleName=ROLE)
        return 1
    except iam.exceptions.NoSuchEntityException:
        return 0


def verify(acct):
    """Re-list every resource type from the checklist; each line must say 0."""
    ctl = boto3.client("bedrock-agentcore-control", region_name=REGION)
    logs, iam, s3 = boto3.client("logs", region_name=REGION), boto3.client("iam"), boto3.client("s3")
    left = {
        "runtimes": sum(rt["agentRuntimeName"] == NAME for rt in ctl.list_agent_runtimes()["agentRuntimes"]),
        "log groups": len(logs.describe_log_groups(logGroupNamePrefix="/aws/bedrock-agentcore/runtimes/")["logGroups"]),
        "workload identities": sum(w["name"].startswith(NAME) for w in ctl.list_workload_identities().get("workloadIdentities", [])),
        "role": role_exists(iam),
        "bucket": sum(b["Name"] == bucket_name(acct) for b in s3.list_buckets()["Buckets"]),
        "state file": int(STATE.exists()),
    }
    for k, v in left.items():
        print(f"   verify {k}: {v}")
    if any(left.values()):
        raise SystemExit("teardown incomplete")


if __name__ == "__main__":
    {"deploy": deploy, "invoke": invoke, "status": status, "teardown": teardown}[sys.argv[1]]()

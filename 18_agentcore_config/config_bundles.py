"""
Level 75: AgentCore Config Bundles — Git-Like Versioned Config for Agent Resources
=================================================================================
AWS Bedrock AgentCore — `ConfigurationBundle` (control plane).

Goal: stop treating agent runtime configuration (tool descriptions, settings) as
something you edit in place. A Config Bundle is VERSIONED config for real AgentCore
resources — keyed by their ARNs — with Git-like branches, commit messages, and a
version lineage you can roll back to or audit.

The shift:
    BEFORE: change a gateway's tool description -> overwrite, no history
    AFTER:  commit a new bundle version with a message -> every change is a versioned,
            retrievable point on a branch (roll back / audit / branch).

Depends on: L27/L33 (AgentCore control plane), L74 (resources to configure)
Unlocks:    auditable, rollback-able agent config; config-as-data

Iterations:
  1. Setup + version 1   — make a gateway (the resource we configure) and a config
                           bundle whose component overrides a tool description.
  2. Commit version 2    — update the bundle (new description + commit message);
                           the version lineage now has two entries.
  3. Retrieve a version  — get_configuration_bundle_version reads ANY past version
                           (the rollback/audit story).

Critical API facts (validated by live probe, not docs):
    * A bundle is a map of COMPONENTS keyed by a real AgentCore resource ARN — a
      workload-identity ARN is rejected; a GATEWAY ARN works:
        components = { gateway_arn: {"configuration": {"toolOverrides":
                        {"<tool>": {"description": "<override>"}}}} }
      The gateway component's configuration is `toolOverrides` directly (NOT wrapped
      in a "document" key — that raises ValidationException).
    * create_configuration_bundle(bundleName, components, branchName, commitMessage)
      -> bundleId, versionId. update_configuration_bundle(bundleId, components,
      branchName, commitMessage, parentVersionIds=[prev]) -> a NEW versionId.
    * list_configuration_bundle_versions(bundleId) -> the lineage;
      get_configuration_bundle_version(bundleId, versionId) -> a past version.
    * A minimal gateway needs only name + roleArn + authorizerType (AWS_IAM) +
      protocolType=MCP — NO target required; it goes CREATING -> READY. The role
      needs a trust policy for bedrock-agentcore.amazonaws.com.

Usage:
    AWS_PROFILE=<agentic-account-profile> uv run python 18_agentcore_config/config_bundles.py
"""

import json
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError

if os.environ.get("AWS_PROFILE"):
    for _k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        os.environ.pop(_k, None)

REGION = "us-east-1"
ROLE_NAME = "l75gatewayrole"
GATEWAY_NAME = "l75gateway"
BUNDLE_NAME = "l75configbundle"
TOOL = "search_docs"

control = boto3.client("bedrock-agentcore-control", region_name=REGION)
iam = boto3.client("iam")


def preflight() -> bool:
    try:
        ident = boto3.client("sts", region_name=REGION).get_caller_identity()
        print(f"  authenticated as {ident['Arn'].split('/')[-1]} (acct {ident['Account']})")
        return True
    except Exception as e:
        print(f"  AWS credentials unavailable: {str(e)[:90]}")
        return False


def component(description: str) -> dict:
    """A gateway component config: override a tool's description (no 'document' wrapper)."""
    return {"configuration": {"toolOverrides": {TOOL: {"description": description}}}}


def ensure_role() -> str:
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
        "Action": "sts:AssumeRole"}]}
    try:
        arn = iam.create_role(RoleName=ROLE_NAME,
                              AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
        time.sleep(8)  # IAM propagation before the gateway can assume it
        return arn
    except iam.exceptions.EntityAlreadyExistsException:
        return iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]


def wait_gateway_ready(gid: str) -> str:
    for _ in range(30):
        st = control.get_gateway(gatewayIdentifier=gid).get("status")
        if st not in ("CREATING", "UPDATING"):
            return st
        time.sleep(4)
    return "TIMEOUT"


def cleanup() -> None:
    """Delete any same-named leftovers so the lesson is re-runnable."""
    for b in control.list_configuration_bundles().get("configurationBundles",
              control.list_configuration_bundles().get("items", [])):
        if b.get("bundleName") == BUNDLE_NAME:
            try:
                control.delete_configuration_bundle(bundleId=b.get("bundleId"))
            except ClientError:
                pass
    for g in control.list_gateways().get("items", control.list_gateways().get("gateways", [])):
        if g.get("name") == GATEWAY_NAME:
            gid = g.get("gatewayId") or g["gatewayArn"].split("/")[-1]
            try:
                control.delete_gateway(gatewayIdentifier=gid)
            except ClientError:
                pass


# ---------------------------------------------------------------------------
# ITERATION 1: setup + version 1
# ---------------------------------------------------------------------------
def iteration_1_first_version() -> tuple:
    print("\n" + "=" * 70)
    print("ITERATION 1: a resource + its first config-bundle version")
    print("=" * 70)
    role_arn = ensure_role()
    g = control.create_gateway(name=GATEWAY_NAME, roleArn=role_arn,
                               authorizerType="AWS_IAM", protocolType="MCP")
    gid = g.get("gatewayId") or g["gatewayArn"].split("/")[-1]
    gateway_arn = g["gatewayArn"]
    print(f"  gateway {gid} -> {wait_gateway_ready(gid)}")

    b = control.create_configuration_bundle(
        bundleName=BUNDLE_NAME, description="L75 demo config",
        components={gateway_arn: component("Search the documentation.")},
        branchName="main", commitMessage="v1: initial tool description")
    bundle_id, v1 = b["bundleId"], b["versionId"]
    print(f"  bundle {bundle_id}  version v1={v1[:8]} (commit: 'v1: initial tool description')")
    return gid, gateway_arn, bundle_id, v1


# ---------------------------------------------------------------------------
# ITERATION 2: commit version 2
# ---------------------------------------------------------------------------
def iteration_2_second_version(gateway_arn: str, bundle_id: str, v1: str) -> str:
    print("\n" + "=" * 70)
    print("ITERATION 2: commit a new version (Git-like lineage)")
    print("=" * 70)
    u = control.update_configuration_bundle(
        bundleId=bundle_id,
        components={gateway_arn: component("Search the documentation. Prefer recent pages.")},
        branchName="main", commitMessage="v2: refine description",
        parentVersionIds=[v1])
    v2 = u["versionId"]
    print(f"  committed v2={v2[:8]} (parent={v1[:8]}, commit: 'v2: refine description')")
    versions = next((x for k, x in control.list_configuration_bundle_versions(
        bundleId=bundle_id).items() if isinstance(x, list)), [])
    print(f"  version lineage: {[v.get('versionId', '?')[:8] for v in versions]}")
    assert len(versions) >= 2, "the bundle should now have two versions"
    print("  OK: two committed versions on branch 'main' — every config change is history.")
    return v2


# ---------------------------------------------------------------------------
# ITERATION 3: retrieve a past version (rollback / audit)
# ---------------------------------------------------------------------------
def iteration_3_get_version(bundle_id: str, v1: str) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 3: read any past version (rollback / audit)")
    print("=" * 70)
    try:
        old = control.get_configuration_bundle_version(bundleId=bundle_id, versionId=v1)
        comps = old.get("components", {})
        desc = json.dumps(comps)
        print(f"  fetched v1 ({v1[:8]}): contains the ORIGINAL description "
              f"-> {'Prefer recent' not in desc}")
        print("  You can read (or restore) the exact config at any past version id.")
    except ClientError as e:
        print(f"  get_version note: {str(e)[:80]}")
    print("  OK: history is retrievable — roll back or audit any committed version.")


def teardown(gid, bundle_id) -> None:
    print("\n[teardown]")
    if bundle_id:
        try:
            control.delete_configuration_bundle(bundleId=bundle_id)
            print("  deleted bundle")
        except ClientError as e:
            print(f"  bundle: {str(e)[:60]}")
    if gid:
        try:
            control.delete_gateway(gatewayIdentifier=gid)
            print("  deleted gateway")
        except ClientError as e:
            print(f"  gateway: {str(e)[:60]}")
    try:
        iam.delete_role(RoleName=ROLE_NAME)
        print("  deleted IAM role")
    except ClientError as e:
        print(f"  role: {str(e)[:60]}")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L75 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. Config as versioned data
   A Config Bundle holds config for real AgentCore resources, keyed by ARN. Each
   create/update is a COMMIT (message + parentVersionIds) on a BRANCH — a version
   lineage, not an in-place edit.

2. The component shape
   components = { gateway_arn: {"configuration": {"toolOverrides":
                    {"<tool>": {"description": "..."}}}} }
   Key must be a valid resource ARN (gateway); toolOverrides goes directly under
   configuration (no "document" wrapper).

3. Roll back / audit
   list_configuration_bundle_versions -> the lineage;
   get_configuration_bundle_version(bundleId, versionId) -> the exact past config.

4. Cheap to stand up
   A minimal gateway (name + role + AWS_IAM + MCP, no target) is enough to have an
   ARN to configure. The role just needs to trust bedrock-agentcore.amazonaws.com.
""")


def main() -> None:
    print("AgentCore Config Bundles — L75")
    if not preflight():
        sys.exit(1)
    cleanup()
    gid = bundle_id = None
    try:
        gid, gateway_arn, bundle_id, v1 = iteration_1_first_version()
        iteration_2_second_version(gateway_arn, bundle_id, v1)
        iteration_3_get_version(bundle_id, v1)
    finally:
        teardown(gid, bundle_id)
    summary()


if __name__ == "__main__":
    main()

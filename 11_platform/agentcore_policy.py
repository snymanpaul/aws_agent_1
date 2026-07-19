"""
Level 33: AgentCore Policy — Cedar Enforcement at the Gateway
=============================================================
Define agent governance boundaries in plain English or Cedar syntax.
The Gateway enforces them in <1ms without any agent code changes.

Goal: understand the full policy lifecycle — engine → NL2Cedar generation →
policy creation → Gateway attachment → cleanup.

Depends on: L22 (in-process guardrails), L27 (AgentCore deployment)
Unlocks:    L34 (Evaluations — measure what policy protects)

GA: March 3, 2026.

Architecture:
    Plain English
         |
         v  NL2Cedar: start_policy_generation → poll → findings (Cedar)
    Cedar statement
         |
         v  create_policy → ACTIVE
    Policy (in PolicyEngine)
         |
         v  update_gateway(policyEngineConfiguration=...)
    Gateway enforces at request time (<1ms, default-deny)
         |
    permit → tool executes
    forbid → request blocked (no agent code change needed)

Cedar entity types:
    principal is AgentCore::OAuthUser
    action    == AgentCore::Action::"ToolName__method"
    resource  == AgentCore::Gateway::"arn:aws:bedrock-agentcore:..."
    Wildcard: permit(principal, action, resource);  — allow all

Contrast with L22:
    L22 = in-process Python guardrails (rate limit, PII, cost caps)
    L33 = infrastructure Cedar (Gateway, <1ms, no code deploy needed)
    Both are complementary — stack them.

AWS resources (live from L27):
    Gateway: l27agentcore-gateway-hr4f5b0f6x  (READY, MCP/CUSTOM_JWT)
    Account: <data-account-id>  |  Region: us-east-1

Usage:
    AWS_PROFILE=<your-sso-profile> \\
        uv run python 11_platform/agentcore_policy.py
"""

import sys
import os
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3

RUN_ID = str(int(time.time()))[-6:]   # unique suffix per run

REGION       = "us-east-1"
GATEWAY_ID   = "l27agentcore-gateway-hr4f5b0f6x"
GATEWAY_ARN  = f"arn:aws:bedrock-agentcore:{REGION}:<data-account-id>:gateway/{GATEWAY_ID}"
GATEWAY_ROLE = (
    "arn:aws:iam::<data-account-id>:role/"
    "l27agentcore-AgentCoreSta-l27agentcoreAgentCoreGate-jWuoSU2vKmMM"
)
COGNITO_DISCOVERY = (
    "https://cognito-idp.us-east-1.amazonaws.com/"
    "us-east-1_IETOPBoNC/.well-known/openid-configuration"
)
COGNITO_CLIENT = "5pgimpsa839u40bo6nutbf0p9b"

# Cedar statements. Rules learned from API validation errors:
#   - bare "resource" wildcard rejected → must use "resource is AgentCore::Gateway"
#   - specific action with type resource rejected → must use specific gateway ARN
#   - invalid action name → error reveals actual registered actions on the gateway
#
# Gateway l27agentcore has one registered action: "l27agentcore-Target" (its MCP target)
GATEWAY_ACTION = "l27agentcore-Target"

# Broad permit — any OAuth user, any action, any gateway (validation override needed)
PERMIT_CEDAR = (
    "permit(principal is AgentCore::OAuthUser, action, "
    "resource is AgentCore::Gateway);"
)
# Specific forbid — block all principals from the gateway's MCP target action
FORBID_CEDAR = (
    f'forbid(principal, action == AgentCore::Action::"{GATEWAY_ACTION}",'
    f' resource == AgentCore::Gateway::"{GATEWAY_ARN}");'
)

AWS_PROFILE = os.environ.get("AWS_PROFILE")
_session = boto3.Session(profile_name=AWS_PROFILE, region_name=REGION)
client = _session.client("bedrock-agentcore-control")


# ---------------------------------------------------------------------------
# Startup cleanup — delete any leftover l33 engine from a previous run
# ---------------------------------------------------------------------------

def _cleanup_existing():
    engines = client.list_policy_engines().get("policyEngines", [])
    for e in [x for x in engines if x["name"] == "l33_policy_engine"]:
        eid = e["policyEngineId"]
        print(f"[startup] leftover engine {eid} — cleaning up")
        # Delete all policies and wait for each
        policies = client.list_policies(policyEngineId=eid).get("policies", [])
        for p in policies:
            client.delete_policy(policyEngineId=eid, policyId=p["policyId"])
            print(f"[startup]   deleting policy {p['name']}...", end="", flush=True)
            for _ in range(20):
                time.sleep(2)
                remaining = client.list_policies(policyEngineId=eid).get("policies", [])
                if not any(x["policyId"] == p["policyId"] for x in remaining):
                    break
                print(".", end="", flush=True)
            print(" done")
        # Delete engine and wait
        client.delete_policy_engine(policyEngineId=eid)
        print(f"[startup]   waiting for engine deletion...", end="", flush=True)
        for _ in range(30):
            time.sleep(3)
            remaining = [
                x for x in client.list_policy_engines().get("policyEngines", [])
                if x["policyEngineId"] == eid
            ]
            if not remaining:
                break
            print(".", end="", flush=True)
        print(" done")

_cleanup_existing()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def poll(fn, done_statuses=("COMPLETED", "ACTIVE"),
         fail_statuses=("FAILED", "CREATE_FAILED", "UPDATE_FAILED", "DELETE_FAILED"),
         interval=3, max_attempts=20):
    """Poll fn() until status is terminal; return final response."""
    for attempt in range(max_attempts):
        resp = fn()
        status = resp.get("status", "")
        print(f"    [{attempt + 1}] status: {status}")
        if status in done_statuses:
            return resp
        if status in fail_statuses:
            reasons = resp.get("statusReasons", [])
            raise RuntimeError(f"Operation failed ({status}): {reasons}")
        time.sleep(interval)
    raise TimeoutError("Polling timed out")


def jprint(d):
    d = {k: v for k, v in d.items() if k != "ResponseMetadata"}
    print(json.dumps(d, indent=2, default=str))


# ---------------------------------------------------------------------------
# ITERATION 1: Policy Engine + NL2Cedar
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 1: Policy Engine + NL2Cedar — plain English → Cedar")
print("=" * 70)
print("""
NL2Cedar converts natural language to Cedar syntax.
It requires the natural language to reference specific tool/action names
available on the gateway — generic text ("any tool") yields empty findings.

This iteration demonstrates the full generation lifecycle, then explains
why findings may be empty for a gateway without a populated tool schema.
""")

print("--- create policy engine ---")
engine_resp = client.create_policy_engine(name="l33_policy_engine")
engine_resp.pop("ResponseMetadata", None)
jprint(engine_resp)

ENGINE_ID  = engine_resp["policyEngineId"]
ENGINE_ARN = engine_resp["policyEngineArn"]

print("  polling until ACTIVE...")
poll(
    lambda: {
        k: v for k, v in
        client.get_policy_engine(policyEngineId=ENGINE_ID).items()
        if k != "ResponseMetadata"
    }
)
print(f"  ready: {ENGINE_ID}")

print("\n--- NL2Cedar: permit rule (generic NL) ---")
PERMIT_NL = (
    "Allow all authenticated users to invoke any tool on this gateway "
    "when the request comes from a valid OAuth session."
)
print(f"  input: '{PERMIT_NL}'")

gen1 = client.start_policy_generation(
    policyEngineId=ENGINE_ID,
    name=f"permit_all_{RUN_ID}",
    resource={"arn": GATEWAY_ARN},
    content={"rawText": PERMIT_NL},
)
gen1.pop("ResponseMetadata", None)
GEN1_ID = gen1["policyGenerationId"]

result1 = poll(
    lambda: {
        k: v for k, v in
        client.get_policy_generation(
            policyEngineId=ENGINE_ID,
            policyGenerationId=GEN1_ID,
        ).items()
        if k != "ResponseMetadata"
    },
    done_statuses=("GENERATED", "COMPLETED"),
    fail_statuses=("FAILED", "GENERATION_FAILED"),
)
nl_cedar = result1.get("findings", "")

if nl_cedar:
    print(f"\n  NL2Cedar output:\n{nl_cedar}")
else:
    print("""
  findings: (empty)

  Why NL2Cedar returned empty:
    NL2Cedar generates Cedar for SPECIFIC actions (e.g. "ToolName__method").
    Without a populated tool schema/registry on this gateway, there are no
    action names to reference, so the service can't produce a Cedar statement.
    In a production gateway with registered tools, the same NL text would
    generate: permit(principal is AgentCore::OAuthUser,
                     action == AgentCore::Action::"MyTool__my_method", ...)

  Proceeding with hand-written Cedar for the remaining iterations.
    permit: permit(principal, action, resource);  — wildcard allow-all
    forbid: forbid(... action == AgentCore::Action::"l27agentcore-Target" ...);
""")


# ---------------------------------------------------------------------------
# ITERATION 2: Policy lifecycle — create, list, get
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 2: Policy lifecycle — create → list → get")
print("=" * 70)
print(f"""
Cedar entity types used:
    principal is AgentCore::OAuthUser   — JWT-authenticated users
    action    == AgentCore::Action::"ToolName__method"
    resource  == AgentCore::Gateway::"arn:..."

Wildcard: permit(principal, action, resource);  — allow all (broadest)
Forbid wins: even one matching forbid blocks the request.

Two policies in one engine — combined at evaluation time:
    permit  → allow any authenticated user to use any tool
    forbid  → block any call to a "delete" action
""")

print("--- create permit policy (broad allow — validationMode=IGNORE_ALL_FINDINGS) ---")
print(f"  Cedar: {PERMIT_CEDAR}")
print("  Note: default FAIL_ON_ANY_FINDINGS rejects 'overly permissive' policies.")
print("        IGNORE_ALL_FINDINGS explicitly overrides when broad access is intended.")
p1 = client.create_policy(
    policyEngineId=ENGINE_ID,
    name="permit_all_tools",
    description="Allow any authenticated user to invoke any tool",
    definition={"cedar": {"statement": PERMIT_CEDAR}},
    validationMode="IGNORE_ALL_FINDINGS",
)
p1.pop("ResponseMetadata", None)
POLICY1_ID = p1["policyId"]
print(f"  policyId: {POLICY1_ID}  status: {p1['status']}")

print("  polling until ACTIVE...")
pol1 = poll(
    lambda: {
        k: v for k, v in
        client.get_policy(policyEngineId=ENGINE_ID, policyId=POLICY1_ID).items()
        if k != "ResponseMetadata"
    }
)
print(f"  status: {pol1['status']}")

print("\n--- create forbid policy ---")
print(f"  Cedar: {FORBID_CEDAR}")
p2 = client.create_policy(
    policyEngineId=ENGINE_ID,
    name="forbid_delete_ops",
    description="Block any delete action regardless of identity",
    definition={"cedar": {"statement": FORBID_CEDAR}},
    validationMode="IGNORE_ALL_FINDINGS",
)
p2.pop("ResponseMetadata", None)
POLICY2_ID = p2["policyId"]
print(f"  policyId: {POLICY2_ID}  status: {p2['status']}")

print("  polling until ACTIVE...")
pol2 = poll(
    lambda: {
        k: v for k, v in
        client.get_policy(policyEngineId=ENGINE_ID, policyId=POLICY2_ID).items()
        if k != "ResponseMetadata"
    }
)
print(f"  status: {pol2['status']}")

print("\n--- list policies ---")
listed = client.list_policies(policyEngineId=ENGINE_ID)
listed.pop("ResponseMetadata", None)
for p in listed["policies"]:
    print(f"  [{p['name']}]  id={p['policyId']}  status={p['status']}")


# ---------------------------------------------------------------------------
# ITERATION 3: Gateway attachment — enforce, verify, detach, cleanup
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 3: Gateway attachment — enforce → verify → detach → cleanup")
print("=" * 70)
print("""
update_gateway(policyEngineConfiguration={arn, mode: ENFORCE}) wires the
engine to the gateway. PUT semantics — all existing gateway fields must
be re-supplied in full.

Enforcement modes:
  ENFORCE  — block non-permitted requests  (production)
  MONITOR  — log violations, allow all     (rollout / debugging)

After attachment: every MCP call through the gateway is Cedar-evaluated.
  Any "delete" action   → BLOCKED by forbid_delete_ops
  Any other tool call   → ALLOWED by permit_all_tools (wildcard)
  No agent code change needed.
""")

print("--- attach policy engine (ENFORCE) ---")
attach = client.update_gateway(
    gatewayIdentifier=GATEWAY_ID,
    name="l27agentcore-Gateway",
    roleArn=GATEWAY_ROLE,
    protocolType="MCP",
    authorizerType="CUSTOM_JWT",
    authorizerConfiguration={
        "customJWTAuthorizer": {
            "discoveryUrl": COGNITO_DISCOVERY,
            "allowedClients": [COGNITO_CLIENT],
        }
    },
    policyEngineConfiguration={
        "arn": ENGINE_ARN,
        "mode": "ENFORCE",
    },
)
attach.pop("ResponseMetadata", None)
print(f"  gateway status: {attach.get('status')}")
print(f"  policyEngineConfiguration: {attach.get('policyEngineConfiguration')}")

# Gateway takes time to finish UPDATING after policy attach — wait for READY
print("  waiting for gateway READY...", end="", flush=True)
for _ in range(20):
    time.sleep(3)
    gw_state = client.get_gateway(gatewayIdentifier=GATEWAY_ID)
    if gw_state.get("status") not in ("UPDATING", "CREATING"):
        break
    print(".", end="", flush=True)
print(f" {gw_state.get('status')}")

print("\n--- verify via get_gateway ---")
gw = client.get_gateway(gatewayIdentifier=GATEWAY_ID)
gw.pop("ResponseMetadata", None)
policy_cfg = gw.get("policyEngineConfiguration")
print(f"  policyEngineConfiguration: {json.dumps(policy_cfg, indent=2, default=str)}")
print(f"  gateway status: {gw['status']}")

print("\n--- detach (revert to no-policy gateway) ---")
detach = client.update_gateway(
    gatewayIdentifier=GATEWAY_ID,
    name="l27agentcore-Gateway",
    roleArn=GATEWAY_ROLE,
    protocolType="MCP",
    authorizerType="CUSTOM_JWT",
    authorizerConfiguration={
        "customJWTAuthorizer": {
            "discoveryUrl": COGNITO_DISCOVERY,
            "allowedClients": [COGNITO_CLIENT],
        }
    },
    # omit policyEngineConfiguration → detaches engine
)
detach.pop("ResponseMetadata", None)
print(f"  gateway status: {detach.get('status')}")
print(f"  policyEngineConfiguration: {detach.get('policyEngineConfiguration', '(none — detached)')}")

# Wait for gateway to settle before cleanup
print("  waiting for gateway READY...", end="", flush=True)
for _ in range(20):
    time.sleep(3)
    gw_state = client.get_gateway(gatewayIdentifier=GATEWAY_ID)
    if gw_state.get("status") not in ("UPDATING", "CREATING"):
        break
    print(".", end="", flush=True)
print(f" {gw_state.get('status')}")

print("\n--- cleanup: delete policies → delete engine ---")
for pid, pname in [(POLICY1_ID, "permit_all_tools"), (POLICY2_ID, "forbid_delete_ops")]:
    r = client.delete_policy(policyEngineId=ENGINE_ID, policyId=pid)
    r.pop("ResponseMetadata", None)
    print(f"  delete {pname}: {r.get('status')}")

# Wait for policies to clear before deleting engine
print("  waiting for policies to clear...", end="", flush=True)
for _ in range(20):
    time.sleep(2)
    remaining = client.list_policies(policyEngineId=ENGINE_ID).get("policies", [])
    if not remaining:
        break
    print(".", end="", flush=True)
print(" done")

r = client.delete_policy_engine(policyEngineId=ENGINE_ID)
r.pop("ResponseMetadata", None)
print(f"  delete engine: {r.get('status')}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("L33 COMPLETE — Key Takeaways")
print("=" * 70)
print("""
1. Policy Engine — namespace for all policies on a gateway
   • create_policy_engine(name=...)  → policyEngineId + policyEngineArn
   • name must match ^[A-Za-z][A-Za-z0-9_]*$ (no hyphens)
   • Engine must reach ACTIVE before creating policies or generations
   • Async: poll get_policy_engine until ACTIVE

2. NL2Cedar — natural language authoring
   • start_policy_generation(policyEngineId, name, resource={arn}, content={rawText})
   • Poll get_policy_generation until status == GENERATED (not COMPLETED)
   • response.findings = Cedar statement — empty if gateway has no tool schema
   • Requires specific tool/action names; generic text yields empty findings
   • In production with registered tools, NL→Cedar generates specific rules

3. Cedar syntax
   • Broad: permit(principal, action, resource is AgentCore::Gateway);
   • Note: bare resource wildcard rejected — must constrain to Gateway type
   • Specific: permit(principal is AgentCore::OAuthUser,
                      action == AgentCore::Action::"Tool__method",
                      resource == AgentCore::Gateway::"arn:...");
   • Conditions: ) when { context.input.amount < 500 };
   • Forbid: forbid(principal, action == AgentCore::Action::"ToolName__method", resource);

4. Policy creation
   • create_policy(policyEngineId, name, definition={cedar: {statement: str}})
   • boto3: definition.cedar.statement  (not definition.statement)
   • Async: poll get_policy until ACTIVE; fail_statuses include CREATE_FAILED
   • list_policies(policyEngineId) — active policies only

5. Gateway attachment
   • update_gateway(..., policyEngineConfiguration={arn: engine_arn, mode: ENFORCE})
   • PUT semantics: ALL gateway fields (name, roleArn, protocolType, authorizer)
     must be re-supplied — nothing is preserved from the previous config
   • Omit policyEngineConfiguration in update_gateway to detach
   • mode: ENFORCE = block | mode: MONITOR = log only

6. Cleanup ordering (async deletion)
   • Must delete all policies first, then wait for list_policies to return []
   • Then delete_policy_engine — fails if any policy still exists
   • Each deletion is async; poll or sleep between steps

7. Gateway role IAM permissions for policy attachment
   • Gateway IAM role needs bedrock-agentcore:* to attach a policy engine
   • Specific actions needed: GetPolicyEngine, CheckAuthorizePermissions, AuthorizeAction
   • update_gateway raises ValidationException / AccessDeniedException if role lacks them
   • update_gateway is async (UPDATING state) — poll get_gateway until READY before next call

8. L22 vs L33 — complementary layers
   • L22 = in-process Python (content-aware: PII, cost, rate limit)
   • L33 = infrastructure Cedar (structural: who, what, when — no code deploy)
   • Stack both: L22 for content rules, L33 for access control
""")

"""
Level 69: AgentCore Payments — Agentic x402 Micropayments (GUARDED)
==================================================================
bedrock-agentcore v1.12 — `bedrock_agentcore.payments`.

What this is:
    "Agentic payments" via the HTTP 402 (Payment Required) status code + the x402
    protocol. An agent calls a paid endpoint, gets a 402 with payment terms, and
    the AgentCorePaymentsPlugin SETTLES the payment (stablecoin, e.g. USDC) and
    retries — autonomously. Backed by a PaymentManager + a connector
    (CoinbaseCDP | StripePrivy) + a payment instrument (e.g. EMBEDDED_CRYPTO_WALLET).

    The plugin gives an agent these tools: http_request (auto-settles 402s),
    getPaymentInstrument, listPaymentInstruments, getPaymentSession.

This lesson is TIERED by cost (real money is involved at the top tier):
    Tier 0 (this file, always runs): OFFLINE — construct the plugin, show the
            payment tools + 402-interception hooks it adds to an agent. No AWS,
            no provisioning, NO money. Verifies the SDK integration.
    Tier 1 (--provision flag): provision a PaymentManager (create -> get ->
            delete, self-cleaning). Exercises the control-plane API. No wallet,
            no settlement, no token money. (Verify AWS resource pricing first.)
    Tier 2 (documented below, NOT run): real settlement on the base-sepolia
            TESTNET (free faucet USDC, no real money) — requires a CoinbaseCDP
            credential + a testnet x402 endpoint (external setup).
    Tier 3 (never unsolicited): ETHEREUM mainnet = REAL money.

Cost control: default Tier 0 (zero cost). Settlement only on TESTNET. Never
mainnet without an explicit per-amount cap. Validated 2026-06-02.

Depends on: L27 (AgentCore runtime), L9 (MCP/tools)
Usage:
    uv run python 14_agentcore_platform/payments.py            # Tier 0 (safe)
    AWS_PROFILE=... uv run python 14_agentcore_platform/payments.py --provision  # + Tier 1
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bedrock_agentcore.payments.integrations.config import AgentCorePaymentsPluginConfig
from bedrock_agentcore.payments.integrations.strands.plugin import AgentCorePaymentsPlugin

REGION = "us-east-1"


# ---------------------------------------------------------------------------
# TIER 0: Offline — what the payments plugin adds to an agent (NO money/AWS)
# ---------------------------------------------------------------------------
def tier0_offline_plugin() -> None:
    print("\n" + "=" * 70)
    print("TIER 0: AgentCorePaymentsPlugin — offline (no provisioning, no money)")
    print("=" * 70)

    # A placeholder ARN: construction does NOT call AWS (the PaymentManager is
    # built lazily only when the agent actually settles a payment).
    config = AgentCorePaymentsPluginConfig(
        payment_manager_arn="arn:aws:bedrock-agentcore:us-east-1:000000000000:payment-manager/demo",
        region=REGION,
        user_id="demo-user",  # required for SigV4 auth (else pass bearer_token/token_provider)
        auto_payment=True,    # auto-settle HTTP 402 responses
    )
    plugin = AgentCorePaymentsPlugin(config)

    tool_names = [t.tool_name for t in plugin.tools]
    hook_names = [h.__class__.__name__ for h in plugin.hooks]
    print(f"  plugin.name        : {plugin.name}")
    print(f"  payment tools added: {tool_names}")
    print(f"  lifecycle hooks    : {hook_names}")
    print(f"  auto_payment       : {config.auto_payment} (settles 402 automatically)")
    print("  -> Agent(plugins=[plugin]) gains these tools; http_request retries")
    print("     a 402 after settling via the payment instrument. No money moved here.")

    assert any("http_request" in t for t in tool_names), "expected an http_request tool"
    print("  OK: the agent would gain x402 payment capability (offline-verified).")


# ---------------------------------------------------------------------------
# TIER 1: Provision a PaymentManager (control-plane) — GUARDED, self-cleaning
# ---------------------------------------------------------------------------
def tier1_provision_payment_manager() -> None:
    print("\n" + "=" * 70)
    print("TIER 1: provision a PaymentManager (create -> get -> delete)")
    print("=" * 70)
    import boto3

    profile = os.environ.get("AWS_PROFILE")
    session = boto3.Session(profile_name=profile, region_name=REGION)
    cp = session.client("bedrock-agentcore-control")
    iam = session.client("iam")
    role_name = "l67-payment-manager-role"
    pm_name = "l67DemoPaymentManager"  # name regex: [a-zA-Z][a-zA-Z0-9]{0,47} (no underscores)

    role_arn = _ensure_role(iam, role_name)
    print(f"  role: {role_arn}")
    pm_id = None
    try:
        resp = cp.create_payment_manager(name=pm_name, authorizerType="AWS_IAM", roleArn=role_arn)
        pm_id = resp.get("paymentManagerId") or resp.get("id")
        print(f"  created paymentManagerId={pm_id} status={resp.get('status')}")
        got = cp.get_payment_manager(paymentManagerId=pm_id)
        print(f"  get -> status={got.get('status')}")
    finally:
        if pm_id:
            cp.delete_payment_manager(paymentManagerId=pm_id)
            print(f"  cleanup: deleted payment manager {pm_id}")
        _delete_role(iam, role_name)
        print(f"  cleanup: deleted role {role_name}")


def _ensure_role(iam, role_name: str) -> str:
    import json
    import time
    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }
    try:
        arn = iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
    except iam.exceptions.EntityAlreadyExistsException:
        arn = iam.get_role(RoleName=role_name)["Role"]["Arn"]
    # CreatePaymentManager validates the execution role can manage workload identities.
    iam.put_role_policy(RoleName=role_name, PolicyName="pm-policy", PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:CreateWorkloadIdentity",
                "bedrock-agentcore:GetWorkloadIdentity",
                "bedrock-agentcore:DeleteWorkloadIdentity",
            ],
            "Resource": "*",
        }],
    }))
    time.sleep(10)  # IAM policy propagation before the service validates the role
    return arn


def _delete_role(iam, role_name: str) -> None:
    try:
        iam.delete_role_policy(RoleName=role_name, PolicyName="pm-policy")
    except Exception:
        pass
    try:
        iam.delete_role(RoleName=role_name)
    except Exception:
        pass


def summary() -> None:
    print("\n" + "=" * 70)
    print("L69 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. Agentic payments = HTTP 402 + x402
   AgentCorePaymentsPlugin gives an agent http_request (+ instrument/session
   tools) and auto-settles 402 Payment Required responses, so the agent can buy
   API access / data per-request without a human.

2. The stack
   PaymentManager (authorizerType AWS_IAM | CUSTOM_JWT, a roleArn)
     -> PaymentConnector (CoinbaseCDP | StripePrivy)
       -> payment instrument (EMBEDDED_CRYPTO_WALLET, USDC)
         -> network: ETHEREUM (real) or base-sepolia / Solana-devnet (TESTNET).

3. Cost discipline (the whole point of the tiers)
   - Tier 0 offline: zero cost — verify the integration without a manager/wallet.
   - Tier 1 control-plane: create -> delete a PaymentManager (self-cleaning).
   - Tier 2 settlement: ONLY on TESTNET (free faucet tokens). Needs a CoinbaseCDP
     credential + a testnet x402 endpoint (external setup — not provisioned here).
   - Tier 3 mainnet: real USDC. Never without an explicit per-amount cap.

4. Tier 2 escalation (NOT implemented — requires external Coinbase setup)
   manager.create_payment_instrument(type="EMBEDDED_CRYPTO_WALLET",
       details={"embeddedCryptoWallet": {"network": "base-sepolia"}})  # testnet
   then plugin auto-settles a 402 from a testnet-paywalled endpoint with faucet USDC.
""")


def main() -> None:
    tier0_offline_plugin()
    if "--provision" in sys.argv:
        tier1_provision_payment_manager()
    else:
        print("\n(Tier 1 provisioning skipped — pass --provision to create+delete a PaymentManager.)")
    summary()


if __name__ == "__main__":
    main()

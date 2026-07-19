"""Append L67 (AgentCore Payments) observations — captured in the moment."""
import json
import os
from datetime import datetime, timedelta, timezone

LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   ".claude", "learnings", "observations.jsonl")
base = datetime.now(timezone.utc)

OBS = [
    dict(level=67, cat="pattern", topic="payments-x402-plugin",
         obs="AgentCorePaymentsPlugin (bedrock-agentcore 1.12) gives an agent 5 tools — http_request (auto-settles HTTP 402 via x402), get_payment_instrument, list_payment_instruments, get_payment_instrument_balance, get_payment_session — plus 2 interception hooks. Construction is OFFLINE-SAFE (the PaymentManager is built lazily, not at __init__), so Tier 0 verifies the integration with zero AWS/money. Config gotcha: AgentCorePaymentsPluginConfig requires user_id for SigV4 auth (unless bearer_token/token_provider is set).",
         ctx="L67 Tier 0 run 2026-06-02 — plugin.tools inspected with a placeholder ARN, no AWS call.",
         entities=["AgentCorePaymentsPlugin", "x402", "http_request", "user_id"]),
    dict(level=67, cat="insight", topic="payments-pricing-is-wallet-ops-only",
         obs="AWS Bedrock AgentCore Payments charges for WALLET OPERATIONS only — CreateInstrument + ProcessPayment (mapped to Coinbase/Stripe fees) — NOT for a PaymentManager/connector existing ('no additional charges beyond standard wallet operation fees'). So CreatePaymentManager -> Get -> Delete with no instrument/payment is FREE. Cost discipline: Tier 0/1 = $0; settlement only on TESTNET (base-sepolia, free faucet USDC); ETHEREUM mainnet = real money. Verified via the AWS AgentCore pricing page.",
         ctx="WebFetch of aws.amazon.com/bedrock/agentcore/pricing before any Tier 1 provisioning.",
         entities=["pricing", "PaymentManager", "wallet-operations", "cost-control", "testnet"]),
    dict(level=67, cat="pattern", topic="payment-manager-provisioning",
         obs="CreatePaymentManager(name, authorizerType, roleArn): name regex is [a-zA-Z][a-zA-Z0-9]{0,47} (ALPHANUMERIC, no underscores — unlike dataset names which allow them). authorizerType AWS_IAM needs no authorizerConfiguration (customJWTAuthorizer is only for CUSTOM_JWT). The execution role MUST grant bedrock-agentcore:CreateWorkloadIdentity (+ allow ~10s for IAM propagation before the service validates). Verified create->get->delete: status READY, self-cleaned (manager + role). Zero cost.",
         ctx="L67 Tier 1 --provision run 2026-06-02 (3 iterations: name regex, role permission, success).",
         entities=["CreatePaymentManager", "AWS_IAM", "CreateWorkloadIdentity", "IAM-propagation"]),
]

with open(LOG, "a", encoding="utf-8") as f:
    for i, o in enumerate(OBS):
        rec = {"ts": (base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "repo": "aws_agent_1", **o}
        f.write(json.dumps(rec) + "\n")
print(f"appended {len(OBS)} L67 observations")

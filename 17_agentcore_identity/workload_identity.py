"""
Level 74: AgentCore Workload Identity — Agent Secrets in a Vault, Not in Code
============================================================================
AWS Bedrock AgentCore — `bedrock_agentcore.identity` + control-plane credential
providers + the token vault.

Goal: stop putting API keys and OAuth secrets in your agent's code. AgentCore gives
each agent a WORKLOAD IDENTITY and a managed TOKEN VAULT: you register a credential
provider (the secret goes into Secrets Manager, AWS-managed), and the agent's code
declares `@requires_api_key(provider_name=...)` — the real key is fetched from the
vault and injected at call time. Your code holds a NAME and a decorator, never the
secret.

The shift (this is the whole point):
    BEFORE: api_key = os.environ["SOME_KEY"]   # secret in env/code, leaks in logs/repos
    AFTER:  @requires_api_key(provider_name="my-provider")        # secret stays vaulted
            def call_api(api_key: str = ""): ...                  # injected at runtime

Depends on: L27/L33 (AgentCore control plane), L22 (safety — secret hygiene)
Unlocks:    agents that call external APIs without embedded secrets; OAuth (M2M / user)

Iterations:
  1. Vault a secret            — create an API-key credential provider; prove Get
                                 returns only REFERENCES (Secrets Manager ARN), never
                                 the raw key.
  2. Inject it with a decorator — `@requires_api_key` fetches the vaulted key and
                                 injects it into a function — no secret in the code.
  3. The workload identity      — the identity the vault keys credentials to; the
                                 decorator auto-creates one for local dev.

Critical API facts (validated by live probe, not docs):
    * from bedrock_agentcore.identity import requires_api_key, requires_access_token
    * create_api_key_credential_provider(name=..., apiKey="...") ->
        {apiKeySecretArn: {secretArn: <Secrets Manager ARN>},
         apiKeySecretSource: "MANAGED",
         credentialProviderArn: <token-vault ARN>}
      The raw key goes into AWS-MANAGED Secrets Manager. get_api_key_credential_provider
      returns ONLY the references — the plaintext key is NEVER returned.
    * @requires_api_key(provider_name=..., into="api_key") injects the key at call time.
      It works LOCALLY (a sync wrapper "for local dev"): it auto-creates a
      workload-<hash> identity, gets a workload access token, fetches the key, injects it.
    * create_workload_identity(name=...) -> workloadIdentityArn (token-vault/default/...).
      It's the agent's identity that the vault keys credentials to.
    * requires_access_token(provider_name=..., scopes=[...], auth_flow="M2M" |
        "USER_FEDERATION" | "ON_BEHALF_OF_TOKEN_EXCHANGE", on_auth_url=...) does the same
      for OAuth2 (M2M client-credentials, or 3-legged user federation).
    * Teardown: delete_api_key_credential_provider(name), delete_workload_identity(name).

Usage:
    AWS_PROFILE=<agentic-account-profile> uv run python 17_agentcore_identity/workload_identity.py
"""

import os
import sys

import boto3
from botocore.exceptions import ClientError

from bedrock_agentcore.identity import requires_api_key

REGION = "us-east-1"
PROVIDER = "l74apiprovider"
DEMO_SECRET = "sk-demo-DO-NOT-LOG-7chars-9931"  # the "real" key we vault; ends 9931

control = boto3.client("bedrock-agentcore-control", region_name=REGION)


def preflight() -> bool:
    try:
        ident = boto3.client("sts", region_name=REGION).get_caller_identity()
        print(f"  authenticated as {ident['Arn'].split('/')[-1]} (acct {ident['Account']})")
        return True
    except Exception as e:
        print(f"  AWS credentials unavailable: {str(e)[:90]}")
        print("  -> run:  aws sso login --sso-session '<your-sso-session>'")
        return False


def workload_identity_names() -> set:
    return {w.get("name") for w in control.list_workload_identities().get("workloadIdentities", [])}


def cleanup_provider() -> None:
    try:
        control.delete_api_key_credential_provider(name=PROVIDER)
    except ClientError:
        pass


# ---------------------------------------------------------------------------
# ITERATION 1: vault a secret
# ---------------------------------------------------------------------------
def iteration_1_vault() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 1: vault a secret — the raw key never comes back")
    print("=" * 70)
    cleanup_provider()
    created = control.create_api_key_credential_provider(name=PROVIDER, apiKey=DEMO_SECRET)
    print(f"  created provider {PROVIDER!r}")
    print(f"    secret stored in: {created['apiKeySecretArn']['secretArn'].split(':secret:')[-1][:45]}…")
    print(f"    source: {created.get('apiKeySecretSource')}  (AWS-managed Secrets Manager)")

    got = control.get_api_key_credential_provider(name=PROVIDER)
    print(f"  Get returns fields: {sorted(got)}")
    assert "apiKeySecretArn" in got, "Get should return the vault reference"
    assert "apiKey" not in got and DEMO_SECRET not in str(got), \
        "the RAW key must never be returned by the control plane"
    print("  OK: the control plane returns only references — the plaintext key stays vaulted.")


# ---------------------------------------------------------------------------
# ITERATION 2: inject it with a decorator (secret out of code)
# ---------------------------------------------------------------------------
def iteration_2_inject() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 2: @requires_api_key injects the vaulted key — no secret in code")
    print("=" * 70)

    captured = {}

    @requires_api_key(provider_name=PROVIDER)
    def call_external_api(api_key: str = "") -> str:
        # This function NEVER references the secret directly — it arrives injected.
        captured["key"] = api_key
        return f"called API with key …{api_key[-4:]}"

    result = call_external_api()
    print(f"  function result: {result!r}")
    key = captured.get("key", "")
    assert key.endswith("9931"), "the decorator should inject the REAL vaulted key"
    # The function body references only `api_key` (the injected param) — never the secret.
    print("  OK: the real key was injected at call time; the function body holds no secret.")


# ---------------------------------------------------------------------------
# ITERATION 3: the workload identity
# ---------------------------------------------------------------------------
def iteration_3_workload_identity(before: set) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 3: the workload identity the vault keys credentials to")
    print("=" * 70)
    after = workload_identity_names()
    auto = sorted(after - before)
    print(f"  iteration 2's decorator auto-created (local dev): {auto or '(none)'}")

    # You can also create a NAMED identity for a deployed agent.
    named = "l74namedagent"
    try:
        w = control.create_workload_identity(name=named)
        print(f"  explicit create_workload_identity({named!r}) -> "
              f"{w['workloadIdentityArn'].split('/')[-1]}")
    except ClientError as e:
        print(f"  create note: {str(e)[:70]}")
    print("  A workload identity is the agent's identity in the token vault; credential")
    print("  providers (API key / OAuth2) are resolved against it. M2M and 3-legged user")
    print("  federation use the sibling decorator requires_access_token(...).")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L74 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. Secrets live in a vault, not your code
   create_api_key_credential_provider(name, apiKey) stores the key in AWS-managed
   Secrets Manager. The control plane returns only ARNs — the plaintext never comes back.

2. Inject at runtime with a decorator
   @requires_api_key(provider_name="…") fetches the vaulted key and injects it into
   your function. Your code holds a provider NAME, never the secret. (OAuth2: the
   sibling requires_access_token with auth_flow M2M / USER_FEDERATION.)

3. Keyed to a workload identity
   Each agent has a workload identity in the token vault; credentials resolve against
   it. The decorator auto-creates one for local dev; deployed agents have their own.

4. Why it matters
   No keys in env vars, repos, or logs. Rotate the secret in one place (the vault)
   and every agent using the provider gets the new value — no code change.
""")


def main() -> None:
    print("AgentCore Workload Identity — L74")
    if not preflight():
        sys.exit(1)
    # The identity decorator caches its workload identity + user id in ./.agentcore.json.
    # A stale cache (identity deleted server-side, or from another account) causes
    # AccessDeniedException — so start fresh and let it recreate one.
    CACHE = ".agentcore.json"
    if os.path.exists(CACHE):
        os.remove(CACHE)
    before = workload_identity_names()
    try:
        iteration_1_vault()
        iteration_2_inject()
        iteration_3_workload_identity(before)
    finally:
        print("\n[teardown]")
        cleanup_provider()
        print("  deleted credential provider")
        # remove any workload identities this run created (decorator auto + explicit)
        for n in sorted(workload_identity_names() - before):
            try:
                control.delete_workload_identity(name=n)
                print(f"  deleted workload identity {n}")
            except ClientError as e:
                print(f"  del {n}: {str(e)[:60]}")
        if os.path.exists(CACHE):
            os.remove(CACHE)  # don't leave the local identity cache behind
    summary()


if __name__ == "__main__":
    main()

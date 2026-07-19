"""
Level 62: Bedrock Prompt Caching (TTL) + strict_tools — on Claude
================================================================
AWS Bedrock via Strands `BedrockModel`: prompt caching with an extended TTL, and
Anthropic `strict_tools` (enforced tool schemas).

Goal: cut the cost of a large, repeated prefix (system prompt, RAG context, tool
catalog) by caching it on Bedrock — pay full price once, then the cheap "cache
read" rate on every reuse — and make tool calls schema-strict. This is the third
token-economics lever after L61 (count before you call) and L68 (cap a run).

Account note (validated live):
    These are Anthropic/Claude features. Claude on Bedrock is gated until a one-time,
    account-wide USE-CASE FORM is submitted (Bedrock console -> Model catalog ->
    "Submit use case details"). Once submitted, the `us.` cross-region inference
    profiles are callable. Accessible non-Claude models (Nova/Llama/Mistral) support
    basic caching but REJECT strict_tools — shown live in iteration 2.

Depends on: L61 (token counting), L59 (Bedrock service tiers)
Unlocks:    cheaper repeated-context agents; pairs with L63 (offload) + L68 (limits)

Iterations:
  1. Prompt caching with TTL   — cache_config(strategy="anthropic", ttl="1h"); a big
                                 prefix is WRITTEN once, then READ from cache on reuse.
  2. strict_tools              — Claude enforces strict tool schemas; an accessible
                                 non-Claude model (Nova) REJECTS strict_tools, live.
  3. The double-cachePoint trap — manual cachePoint + cache_config => a TTL-ordering
                                 ValidationException; use cache_config ALONE.

Critical API facts (validated by live probe, not docs):
    * Claude id is the us. inference profile: us.anthropic.claude-haiku-4-5-20251001-v1:0
      (raw ids raise ValidationException — on-demand needs a profile).
    * Caching: BedrockModel(cache_config=CacheConfig(strategy="anthropic", ttl="1h"))
      injects a system cachePoint WITH the ttl. Pass the system prompt as plain text
      (NO manual cachePoint block — see iteration 3). Usage carries
      cacheWriteInputTokens / cacheReadInputTokens; first call writes, reuse reads.
    * The cached prefix must exceed the model's MINIMUM (Claude Haiku ~2k tokens; a
      ~7.3k-token prefix here -> cacheWrite≈7024, then cacheRead≈7024). Too small =>
      no cache tokens at all (silently). Use a UNIQUE marker per run (cache ~5m+ warm).
    * strict_tools=True enforces tool input schemas. Claude supports it; Nova/Llama/
      Mistral raise ValidationException "This model doesn't support the strict ...".
    * accumulated_usage is CUMULATIVE — take per-call deltas.

Usage:
    AWS_PROFILE=<agentic-account-profile> uv run python 14_token_economics/cache_and_strict.py
"""

import os
import sys
import uuid

import boto3
from botocore.exceptions import ClientError

from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from strands.models.model import CacheConfig

# Defensive (see L72): if a chained .env injected static AWS keys, let the SSO profile win.
if os.environ.get("AWS_PROFILE"):
    for _k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        os.environ.pop(_k, None)

REGION = "us-east-1"
CLAUDE = "us.anthropic.claude-haiku-4-5-20251001-v1:0"  # us. inference profile
NOVA = "amazon.nova-lite-v1:0"


def preflight() -> bool:
    try:
        ident = boto3.client("sts", region_name=REGION).get_caller_identity()
        print(f"  authenticated as {ident['Arn'].split('/')[-1]} (acct {ident['Account']})")
        return True
    except Exception as e:
        print(f"  AWS credentials unavailable: {str(e)[:90]}")
        print("  -> run:  aws sso login --sso-session '<your-sso-session>'")
        return False


def big_prefix() -> list:
    """A large, UNIQUE-per-run system prefix (above Claude's cache minimum)."""
    text = (f"[{uuid.uuid4().hex[:8]}] You are a meticulous AWS solutions architect. "
            + ("Always weigh cost, security, scalability, and operational excellence. " * 700))
    return [{"text": text}]  # NOTE: no manual cachePoint — cache_config injects it


@tool
def get_price(service: str, region: str) -> str:
    """Look up the on-demand price for an AWS service in a region."""
    return f"{service} in {region}: $0.0123/hr"


# ---------------------------------------------------------------------------
# ITERATION 1: prompt caching with an extended TTL
# ---------------------------------------------------------------------------
def iteration_1_cache_ttl() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 1: prompt caching with ttl='1h' — write once, read cheap")
    print("=" * 70)
    model = BedrockModel(model_id=CLAUDE, region_name=REGION,
                         cache_config=CacheConfig(strategy="anthropic", ttl="1h"))
    agent = Agent(model=model, system_prompt=big_prefix(), callback_handler=None)

    u1 = dict(agent("Reply with: ONE").metrics.accumulated_usage)
    u2 = dict(agent("Reply with: TWO").metrics.accumulated_usage)
    write = u1.get("cacheWriteInputTokens", 0)
    read2 = u2.get("cacheReadInputTokens", 0) - u1.get("cacheReadInputTokens", 0)
    print(f"  call 1 (fresh prefix): cacheWrite={write}  cacheRead={u1.get('cacheReadInputTokens')}")
    print(f"  call 2 (same prefix):  cacheRead(delta)={read2}")
    assert write and u1.get("cacheReadInputTokens") == 0, "first call should WRITE the cache"
    assert read2 > 0, "second call should READ the cached prefix (at the cheap rate)"
    print(f"  OK: ~{write} tokens cached at ttl=1h; reused at the cache-read rate.")


# ---------------------------------------------------------------------------
# ITERATION 2: strict_tools (Claude enforces, Nova rejects)
# ---------------------------------------------------------------------------
def iteration_2_strict_tools() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 2: strict_tools — schema enforcement (Claude only)")
    print("=" * 70)
    claude = Agent(model=BedrockModel(model_id=CLAUDE, region_name=REGION, strict_tools=True),
                   tools=[get_price], callback_handler=None,
                   system_prompt="Use get_price for any pricing question.")
    answer = str(claude("What is the price of Lambda in us-east-1?"))
    print(f"  Claude + strict_tools -> {answer.strip()[:50]!r}")
    assert "0.0123" in answer, "Claude should call the strict-schema tool"

    try:
        Agent(model=BedrockModel(model_id=NOVA, region_name=REGION, strict_tools=True),
              tools=[get_price], callback_handler=None,
              system_prompt="Use get_price.")("Price of Lambda in us-east-1?")
        print("  Nova + strict_tools -> unexpectedly OK")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        print(f"  Nova + strict_tools -> {code}: doesn't support strict")
        assert "strict" in str(e).lower()
    print("  OK: strict_tools enforced on Claude; rejected by the non-Claude model.")


# ---------------------------------------------------------------------------
# ITERATION 3: the double-cachePoint trap
# ---------------------------------------------------------------------------
def iteration_3_cachepoint_trap() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 3: don't inject TWO cache points (manual + cache_config)")
    print("=" * 70)
    # A manual cachePoint defaults to ttl=5m; cache_config adds a ttl=1h one. Anthropic
    # forbids a 1h block after a 5m block (order: tools -> system -> messages).
    sys_with_manual = big_prefix() + [{"cachePoint": {"type": "default"}}]
    model = BedrockModel(model_id=CLAUDE, region_name=REGION,
                         cache_config=CacheConfig(strategy="anthropic", ttl="1h"))
    try:
        Agent(model=model, system_prompt=sys_with_manual, callback_handler=None)("hi")
        print("  manual cachePoint + cache_config -> unexpectedly OK")
    except ClientError as e:
        msg = str(e)
        print(f"  manual cachePoint + cache_config -> ValidationException")
        print(f"    ({'ttl ordering: 1h must not come after 5m' if 'ttl' in msg else msg[:60]})")
        assert "cache_control" in msg or "ttl" in msg
    print("  OK: pick ONE — cache_config (recommended; carries the ttl) OR a manual block.")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L62 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. Cache the big constant prefix
   BedrockModel(cache_config=CacheConfig(strategy="anthropic", ttl="1h")) +
   a plain-text system prompt above the model's cache minimum. First call writes
   (cacheWriteInputTokens), reuse reads (cacheReadInputTokens) at a steep discount.
   Over N calls the prefix cost goes N*full -> 1*full + (N-1)*cheap.

2. strict_tools is Claude-only
   strict_tools=True enforces tool input schemas on Claude; Nova/Llama/Mistral
   reject it (ValidationException). Demonstrated live, not assumed.

3. One cache point, not two
   Manual cachePoint (5m default) + cache_config (1h) => a TTL-ordering
   ValidationException ("1h must not come after 5m"; order tools->system->messages).
   Use cache_config alone — it injects the cachePoint with your ttl.

4. Mind the minimum + the warm cache
   Below the model's cache minimum you get NO cache tokens (silently). Use a unique
   per-run prefix (the cache stays warm ~5m+) to measure write-then-read cleanly.

5. Account gate
   Claude on Bedrock needs a one-time, account-wide use-case form (Model catalog).
   Pairs with L61 (estimate first), L63 (offload the variable part), L68 (cap the run).
""")


def main() -> None:
    print("Bedrock Prompt Caching (TTL) + strict_tools on Claude — L62")
    if not preflight():
        sys.exit(1)
    iteration_1_cache_ttl()
    iteration_2_strict_tools()
    iteration_3_cachepoint_trap()
    summary()


if __name__ == "__main__":
    main()

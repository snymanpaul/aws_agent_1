"""
Level 61: Token Counting + Pre-Call Estimate (async `count_tokens`)
==================================================================
Strands SDK v1.42 — `Model.count_tokens(...)` (async, per-provider).

Goal: estimate the input-token cost of a prompt *before* you send it, so you can
gate on a budget (compress / switch model / refuse) without paying for a call
that was always going to overflow. This is the "look before you leap" half of
token economics; L68 (Invocation Limits) is the "stop once you've leapt" half.

The real lesson (measured, not assumed):
    There are TWO estimators and the gap between them is the whole point.
        HEURISTIC (default)  — no API call, instant, free. Pure character math:
            text  -> ceil(chars / 4)   (strands/models/model.py:_heuristic_estimate_text)
            JSON  -> ceil(chars / 2)   (tool specs / tool inputs as JSON)
        NATIVE (opt-in)      — one API round-trip to the provider's REAL tokenizer.
            On Gemini it equals the actual billed inputTokens exactly.

    chars/4 is a fine proxy for English prose, but it badly UNDER-counts the
    inputs that actually blow context windows. Measured on gemini-2.5-flash
    (native count == actual inputTokens in every case):
        case      chars  heuristic  native/actual   heuristic error
        english     87       22          22              0%
        code       170       43          71            -39%   (operators, brackets)
        cjk         33        9          18            -50%   (1 char ~ 1+ tokens)
        punct      140       35         138            -75%   (each symbol ~ 1 token)
    So the FREE estimate silently tells you "you're under budget" on code/logs/
    multilingual text when you are not. That is the trap this lesson makes visible.

Depends on: L15 (context mgmt / Horthy 40% rule), L58 (token tracking AFTER a call)
Unlocks:    L62 (cache TTL — the next token lever), L68 (Invocation Limits names L61 as a dep)

Iterations:
  1. Heuristic estimate (the default)   — count_tokens with no provider call;
                                           prove it IS ceil(chars/4) on text.
  2. Native estimate + structural proof — use_native_token_count=True; prove the
                                           native gain is confined to the message
                                           body (system_prompt + tools stay heuristic).
  3. Where chars/4 lies                 — code / CJK / punctuation: native matches
                                           the real inputTokens; the heuristic
                                           under-counts by 39-75%.
  4. The budget gate flips              — one dense blob the heuristic calls
                                           "under budget" but native (the truth)
                                           calls "over" — caught BEFORE any call.

Critical API facts (validated by probe + this lesson, not docs):
    * await model.count_tokens(messages, tool_specs=None, system_prompt=None,
                               system_prompt_content=None) -> int
      ASYNC, and it lives on the MODEL, not the Agent. No generation happens.
    * DEFAULT is the char heuristic: text ceil(chars/4), JSON ceil(chars/2).
      NOTE: the base method's docstring claims "tiktoken cl100k_base when
      available", but the v1.42 code path returns the char-based heuristic —
      verified (an 87-char string -> 22 == ceil(87/4), not tiktoken's 18).
      Trust the number, not the docstring.
    * Gemini native: use_native_token_count=True (constructor kwarg or
      model.update_config(...)). It calls Gemini's count_tokens for the message
      contents only; system_prompt + tools raise on the mldev backend, so they
      are heuristic-estimated and ADDED. Structural invariant, asserted below:
          heuristic_total - native_total == heuristic_msgonly - native_msgonly
    * SILENT-FALLBACK TRAP: if the native API errors (throttle, network), Gemini
      logs at DEBUG and returns the heuristic. So native==heuristic does NOT prove
      native ran. This lesson guards it: on an input known to diverge (code),
      native MUST differ from the heuristic, else we flag a fallback.
    * Ground truth after a real call: result.metrics.accumulated_usage["inputTokens"].
      Measured here: native count == that actual count, exactly, across input types.
    * Providers with a native override: bedrock, anthropic, gemini,
      openai_responses, llamacpp. A plain OpenAIModel (LiteLLM proxy) has no
      tokenizer to ask, so it uses the base heuristic.

Usage:
    # Uses Gemini 2.5 Flash directly (needs GEMINI_API_KEY in env / .env).
    LESSON_DOTENV=/path/to/.env uv run python 14_token_economics/token_counting.py
"""

import asyncio
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent
from strands.models.gemini import GeminiModel

from tools import get_model

# Gemini 2.5 Flash, direct to Google AI. Default config => heuristic estimator.
model = get_model("gemini-2.5-flash")


def native_model():
    """A Gemini model with the native token-count API enabled, or None if the
    active model isn't Gemini (e.g. LESSON_MODEL overrode it onto LiteLLM)."""
    if not isinstance(model, GeminiModel):
        return None
    nat = get_model("gemini-2.5-flash")
    nat.update_config(use_native_token_count=True)  # flip the one config flag
    return nat


NATIVE = native_model()

# A system prompt + tool spec reused where we need non-message context.
SYS = "You are an AWS solutions architect. Answer precisely and name the service."
TOOLS = [{
    "name": "price_lookup",
    "description": "Look up the on-demand price for an AWS service in a region.",
    "inputSchema": {"json": {
        "type": "object",
        "properties": {"service": {"type": "string"}, "region": {"type": "string"}},
        "required": ["service", "region"],
    }},
}]

# Four message bodies that stress the heuristic differently. The heuristic is
# chars/4 for ALL of them; the real tokenizer disagrees sharply on 3 of 4.
ENGLISH = "Compare AWS Lambda and Fargate for a bursty, latency-sensitive API. When does each win?"
CODE = "def f(x):\n    return [i**2 for i in range(x) if i % 3 == 0]  # squares of multiples of 3\n" * 2
CJK = "東京から大阪まで新幹線で行く場合の料金と所要時間を教えてください。"
PUNCT = "a,b;c.d:e!f?g-h_i/j\\k|l(m)n[o]p{q}r" * 4


def msgs(text: str):
    return [{"role": "user", "content": [{"text": text}]}]


# ---------------------------------------------------------------------------
# ITERATION 1: the heuristic estimate (the default — no API call)
# ---------------------------------------------------------------------------
# Goal: count_tokens returns a number with NO generation, and that number is
# exactly the documented char heuristic (text ceil(chars/4)).
async def iteration_1_heuristic() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 1: heuristic estimate — instant, free, no API call")
    print("=" * 70)

    msg_only = await model.count_tokens(msgs(ENGLISH))
    with_context = await model.count_tokens(msgs(ENGLISH), tool_specs=TOOLS, system_prompt=SYS)

    print(f"  estimate (msg only)            = {msg_only}")
    print(f"  estimate (msg + system + tool) = {with_context}")
    print(f"  user text: {len(ENGLISH)} chars -> ceil(chars/4) = {math.ceil(len(ENGLISH) / 4)}")
    assert msg_only == math.ceil(len(ENGLISH) / 4), \
        f"expected msg-only == ceil(chars/4) == {math.ceil(len(ENGLISH) / 4)}, got {msg_only}"
    assert with_context > msg_only, "system_prompt + tool spec should add tokens"
    print("  OK: msg-only estimate == ceil(chars/4) — the char heuristic, not tiktoken.")


# ---------------------------------------------------------------------------
# ITERATION 2: native estimate + the structural invariant
# ---------------------------------------------------------------------------
# Goal: enable native counting and PROVE the native value differs from the
# heuristic ONLY on the message body — system_prompt + tools are heuristic in
# both modes. Use CODE (where native != heuristic) so the proof isn't vacuous.
async def iteration_2_native_invariant() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 2: native estimate — refines ONLY the message body")
    print("=" * 70)

    if NATIVE is None:
        print("  (skipped — active model is not GeminiModel; native count is provider-specific)")
        return

    heur_full = await model.count_tokens(msgs(CODE), tool_specs=TOOLS, system_prompt=SYS)
    nat_full = await NATIVE.count_tokens(msgs(CODE), tool_specs=TOOLS, system_prompt=SYS)
    heur_msg = await model.count_tokens(msgs(CODE))
    nat_msg = await NATIVE.count_tokens(msgs(CODE))

    print(f"  CODE body: heuristic={heur_msg}  native={nat_msg}  (native really ran: differ by {nat_msg - heur_msg})")
    print(f"  full total: heuristic={heur_full}  native={nat_full}")
    print(f"  full-delta={heur_full - nat_full}   msg-only-delta={heur_msg - nat_msg}")
    # Guard the silent-fallback trap: on CODE the native count MUST differ.
    assert nat_msg != heur_msg, \
        "native == heuristic on CODE => native likely fell back (API error); not a real native count"
    # The deltas are equal because system_prompt + tools use the same heuristic
    # in both modes — native only swaps in Gemini's count for the messages.
    assert (heur_full - nat_full) == (heur_msg - nat_msg), \
        "native must change ONLY the message-body term (sys + tools heuristic in both modes)"
    print("  OK: full-delta == msg-only-delta -> native refines ONLY the message body.")
    print("      (Gemini's mldev API can't count system_prompt or tools, so those stay heuristic.)")


# ---------------------------------------------------------------------------
# ITERATION 3: where chars/4 lies (code / CJK / punctuation)
# ---------------------------------------------------------------------------
# Goal: for each input type, compare heuristic vs native vs the ACTUAL billed
# inputTokens. Native matches reality; the heuristic under-counts the structured
# inputs that overflow context windows.
async def iteration_3_where_heuristic_lies() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 3: where chars/4 lies — code, CJK, punctuation")
    print("=" * 70)
    print(f"  {'case':9s} {'chars':>5} {'heur':>5} {'native':>6} {'actual':>6} {'heur err':>9}")

    cases = {"english": ENGLISH, "code": CODE, "cjk": CJK, "punct": PUNCT}
    for name, text in cases.items():
        heur = await model.count_tokens(msgs(text))
        nat = await NATIVE.count_tokens(msgs(text)) if NATIVE else None
        # Ground truth: a real call with NO system prompt isolates the body.
        agent = Agent(model=model, callback_handler=None)
        actual = (await agent.invoke_async(text)).metrics.accumulated_usage["inputTokens"]
        err_pct = round(100 * (heur - actual) / actual)
        nat_s = f"{nat:>6}" if nat is not None else "   n/a"
        print(f"  {name:9s} {len(text):>5} {heur:>5} {nat_s} {actual:>6} {err_pct:>8}%")

        if NATIVE is not None:
            # Native equals the real tokenizer (within rounding/framing).
            assert abs(nat - actual) <= 2, f"{name}: native {nat} should match actual {actual}"
        # The structured inputs are under-counted by the free heuristic.
        if name in ("code", "cjk", "punct"):
            assert heur < actual, f"{name}: heuristic {heur} should under-count actual {actual}"
    print("  OK: native == actual across types; heuristic under-counts code/CJK/punctuation.")


# ---------------------------------------------------------------------------
# ITERATION 4: the budget gate flips
# ---------------------------------------------------------------------------
# Goal: a dense blob the FREE heuristic waves through as "under budget" but the
# native count (the truth) rejects as "over budget" — decided before any call.
def budget_check(estimate: int, context_window_limit: int, target: float = 0.40):
    budget = int(context_window_limit * target)
    return estimate > budget, budget


async def iteration_4_gate_flip() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 4: the budget gate flips — heuristic says send, native says NO")
    print("=" * 70)

    if NATIVE is None:
        print("  (skipped — needs the native estimator)")
        return

    # Pretend a tiny 200-token window (real models are 200k+); 40% rule -> 80.
    # PUNCT is ~140 chars: heuristic ~35 (under 80) but real ~138 (over 80).
    LIMIT, blob = 200, PUNCT  # punctuation-dense, like minified code or a log
    heur = await model.count_tokens(msgs(blob))
    nat = await NATIVE.count_tokens(msgs(blob))

    heur_over, budget = budget_check(heur, LIMIT)
    nat_over, _ = budget_check(nat, LIMIT)
    print(f"  blob: {len(blob)} chars   budget (40% of {LIMIT}) = {budget} tokens")
    print(f"  heuristic estimate = {heur:>4} -> {'OVER' if heur_over else 'OK  '} -> "
          f"{'refuse' if heur_over else 'send as-is'}")
    print(f"  native estimate    = {nat:>4} -> {'OVER' if nat_over else 'OK  '} -> "
          f"{'refuse' if nat_over else 'send as-is'}")

    assert nat > heur, "native must exceed the heuristic on punctuation-dense input"
    assert (not heur_over) and nat_over, \
        "expected the gate to FLIP: heuristic under budget, native over budget"
    print("  OK: the free heuristic would have sent an over-budget prompt; native caught it.")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L61 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. What count_tokens is
   est = await model.count_tokens(messages, tool_specs=..., system_prompt=...)
   An ASYNC, pre-call input estimate on the MODEL. No generation, no usage.

2. Two estimators, one trade-off
   HEURISTIC (default): free + instant; text ceil(chars/4), JSON ceil(chars/2).
   NATIVE (use_native_token_count=True): one API round-trip; on Gemini it equals
   the real billed inputTokens and refines ONLY the message body (system_prompt +
   tools stay heuristic). Proven: heur_total - nat_total == heur_msg - nat_msg.

3. chars/4 lies on the inputs that matter
   Measured: heuristic error was 0% on English but -39% (code), -50% (CJK),
   -75% (punctuation). The free estimate silently says "under budget" on code,
   logs, and multilingual text when you are NOT. Gate THOSE on native.

4. Beware the silent fallback
   If the native API errors, Gemini logs at DEBUG and returns the heuristic, so
   native==heuristic does not prove native ran. Validate on an input known to
   diverge (here: CODE) before trusting a green check.

5. The point is the gate
   Estimate -> apply the 40% rule -> compress / switch / refuse BEFORE the call.
   count_tokens (look before you leap) pairs with L68 Limits (stop mid-leap) and
   L62 cache TTL (pay less per token) for end-to-end token economics.
""")


async def main() -> None:
    await iteration_1_heuristic()
    await iteration_2_native_invariant()
    await iteration_3_where_heuristic_lies()
    await iteration_4_gate_flip()
    summary()


if __name__ == "__main__":
    asyncio.run(main())

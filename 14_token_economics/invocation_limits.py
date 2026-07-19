"""
Level 68: Invocation Limits — Cap a Single Agent Run by Turns or Tokens
=======================================================================
Strands SDK v1.42 — `strands.types.Limits` (strands #2360).

Goal: bound ONE `invoke` / `stream` call so a runaway loop or a verbose model
can't blow the budget — and have it stop *gracefully* (a `stop_reason`, not an
exception) with the conversation left in a re-invokable state.

Problem this solves:
    An agent with a tool can loop. A model can ramble. Before 1.42 the only
    backstops were a provider-level max_tokens (bounds ONE model call, not the
    whole loop) and hand-rolled turn counters in a callback. Neither is a clean,
    per-invocation budget on the *agent loop itself*.

    Limits adds three caps, each scoped to a SINGLE invocation:
        turns         — max agent-loop iterations (model call + its tool run)
        output_tokens — cumulative generated tokens across the invocation
        total_tokens  — cumulative input+output tokens across the invocation

Depends on: L21 (cost controls), L61 (token counting), L63 (tool offload)
Unlocks:    L62 (cache TTL) — limits + caching are complementary token levers

Iterations:
  1. The Limits shape + a `turns` cap  — a deliberately looping tool; cap at 3
                                         turns; observe graceful stop_reason.
  2. output_tokens and total_tokens    — same loop, token caps instead.
  3. Per-invocation reset              — reuse the SAME agent twice; show the
                                         counters reset (caps are not cumulative).
  4. Priority on simultaneous trip     — turns + output_tokens both trip on the
                                         same turn; show which stop_reason wins.

Critical API facts (validated by probe + this lesson, not docs):
    * from strands.types import Limits   # TypedDict, total=False
        Limits(turns=int, output_tokens=int, total_tokens=int)  # each a positive int
    * Pass to any entry point:
        agent("prompt", limits=Limits(turns=3))     # __call__
        await agent.invoke_async(..., limits=...)
        await agent.stream_async(..., limits=...)
    * Graceful stop: NO exception. result.stop_reason is one of
        "limit_turns" | "limit_total_tokens" | "limit_output_tokens"
      (alongside the normal "end_turn" / "tool_use" / "max_tokens").
    * Caps are checked at the TOP of each loop iteration, so a tool requested by
      the previous turn always finishes first and agent.messages stays
      re-invokable. Counters reset every invocation (not cumulative across reuse).
    * Priority when several trip at once (highest first): turns, total_tokens,
      output_tokens. output_tokens is a SOFT cap (a single oversized response can
      overshoot; it's checked at turn boundaries).
    * A non-positive / non-int value raises TypeError (fail fast).

Usage:
    # Uses Gemini 2.5 Flash directly (needs GEMINI_API_KEY in env / .env).
    # If imports stall reading .pyc on a synced/secured filesystem, prefix
    # PYTHONDONTWRITEBYTECODE=1.
    uv run python 14_token_economics/invocation_limits.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands.types import Limits

from tools import get_model

# Gemini 2.5 Flash, direct to Google AI (Anthropic budget paused; Limits is
# model-agnostic). Capable tool-use, so the looping tool actually loops.
# Override the whole course with the LESSON_MODEL env var (see tools/get_model).
model = get_model("gemini-2.5-flash")

# A system prompt that makes the agent loop forever on its own, so the ONLY
# thing that stops it is an invocation limit. This is the whole point: we are
# proving the limit is the backstop.
LOOP_PROMPT = (
    "You run a long, open-ended iterative process. Your job is to keep calling "
    "the `take_step` tool over and over. The process NEVER finishes on its own — "
    "only an external budget limit will stop you. After every tool result, call "
    "`take_step` again. Do not stop, do not ask questions, do not conclude."
)


@tool
def take_step(note: str) -> str:
    """Record one step of a long process, then signal that more steps remain.

    Args:
        note: A short note describing this step.
    """
    return "Step recorded. The process is NOT complete — call take_step again."


def stop_summary(result) -> str:
    """Best-effort one-line summary of how an invocation ended."""
    turns = tokens_in = tokens_out = "?"
    try:
        m = result.metrics
        cycles = getattr(m, "cycle_count", None)
        if cycles is None:
            cycles = len(getattr(m, "cycle_durations", []) or [])
        turns = cycles
        usage = getattr(m, "accumulated_usage", {}) or {}
        tokens_in = usage.get("inputTokens", "?")
        tokens_out = usage.get("outputTokens", "?")
    except Exception:
        pass
    return f"stop_reason={result.stop_reason!r}  turns={turns}  in={tokens_in} out={tokens_out}"


# ---------------------------------------------------------------------------
# ITERATION 1: The Limits shape + a `turns` cap
# ---------------------------------------------------------------------------
# Goal: cap the loop at 3 turns and confirm the run stops by RETURNING a result
# whose stop_reason is "limit_turns" — no try/except needed.
def iteration_1_turns_cap() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 1: turns cap — the loop stops gracefully")
    print("=" * 70)
    print(f"  Limits fields: {list(Limits.__annotations__)}")

    agent = Agent(model=model, tools=[take_step], system_prompt=LOOP_PROMPT,
                  callback_handler=None)

    result = agent("Begin the process.", limits=Limits(turns=3))

    print(f"  cap: turns=3")
    print(f"  {stop_summary(result)}")
    print(f"  exception raised? NO — the run returned normally")
    print(f"  messages in history: {len(agent.messages)} (re-invokable)")
    assert result.stop_reason == "limit_turns", \
        f"expected limit_turns, got {result.stop_reason!r}"
    print("  OK: stop_reason == 'limit_turns'")


# ---------------------------------------------------------------------------
# ITERATION 2: output_tokens and total_tokens caps
# ---------------------------------------------------------------------------
# Goal: the same looping tool, but bound by token budgets instead of turns.
# output_tokens counts generated tokens; total_tokens counts input+output.
def iteration_2_token_caps() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 2: token caps — output_tokens and total_tokens")
    print("=" * 70)

    # 2a. output_tokens — a small generated-token budget.
    agent_a = Agent(model=model, tools=[take_step], system_prompt=LOOP_PROMPT,
                    callback_handler=None)
    res_a = agent_a("Begin.", limits=Limits(output_tokens=80))
    print(f"  2a cap: output_tokens=80")
    print(f"     {stop_summary(res_a)}")
    assert res_a.stop_reason == "limit_output_tokens", \
        f"expected limit_output_tokens, got {res_a.stop_reason!r}"
    print("     OK: stop_reason == 'limit_output_tokens'")

    # 2b. total_tokens — input grows every turn (history accumulates), so the
    # input+output budget trips quickly.
    agent_b = Agent(model=model, tools=[take_step], system_prompt=LOOP_PROMPT,
                    callback_handler=None)
    res_b = agent_b("Begin.", limits=Limits(total_tokens=3000))
    print(f"  2b cap: total_tokens=3000")
    print(f"     {stop_summary(res_b)}")
    assert res_b.stop_reason == "limit_total_tokens", \
        f"expected limit_total_tokens, got {res_b.stop_reason!r}"
    print("     OK: stop_reason == 'limit_total_tokens'")


# ---------------------------------------------------------------------------
# ITERATION 3: per-invocation reset
# ---------------------------------------------------------------------------
# Goal: reuse the SAME agent for two capped invocations and show each gets the
# full budget — the turn counter is NOT cumulative across invocations.
def iteration_3_per_invocation_reset() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 3: caps reset every invocation (not cumulative)")
    print("=" * 70)

    agent = Agent(model=model, tools=[take_step], system_prompt=LOOP_PROMPT,
                  callback_handler=None)

    r1 = agent("First run.", limits=Limits(turns=2))
    print(f"  run 1 (turns=2): {stop_summary(r1)}")
    r2 = agent("Second run.", limits=Limits(turns=2))
    print(f"  run 2 (turns=2): {stop_summary(r2)}")

    assert r1.stop_reason == "limit_turns" and r2.stop_reason == "limit_turns", \
        f"expected both to hit limit_turns, got {r1.stop_reason!r}, {r2.stop_reason!r}"
    print("  OK: both invocations independently hit turns=2 — counters reset.")
    print(f"     (history carried across runs: {len(agent.messages)} messages,")
    print(f"      but the per-invocation turn budget did not.)")


# ---------------------------------------------------------------------------
# ITERATION 4: priority when several caps trip at once
# ---------------------------------------------------------------------------
# Goal: set turns=1 AND output_tokens=1 so both are exceeded after the first
# turn, and observe which stop_reason the SDK reports. Documented priority
# (highest first) is: turns, total_tokens, output_tokens.
def iteration_4_priority() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 4: priority on simultaneous trip (turns > total > output)")
    print("=" * 70)

    agent = Agent(model=model, tools=[take_step], system_prompt=LOOP_PROMPT,
                  callback_handler=None)
    result = agent("Begin.", limits=Limits(turns=1, output_tokens=1))
    print(f"  cap: turns=1 AND output_tokens=1 (both trip after turn 1)")
    print(f"  {stop_summary(result)}")
    # Empirically confirm the documented priority: turns wins over output_tokens.
    print(f"  reported winner: {result.stop_reason!r} "
          f"(documented priority puts 'limit_turns' first)")

    # And the fail-fast contract: a non-positive cap raises TypeError.
    try:
        agent("x", limits=Limits(turns=0))
        print("  WARN: turns=0 did not raise (expected TypeError)")
    except TypeError as e:
        print(f"  validation: Limits(turns=0) -> TypeError ({str(e)[:50]})")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L68 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. What Limits is
   from strands.types import Limits
   agent("prompt", limits=Limits(turns=3, output_tokens=..., total_tokens=...))
   A per-INVOCATION budget on the agent loop. Each cap is independent; omit a
   field for no limit on that dimension.

2. Graceful, not fatal
   Hitting a cap RETURNS a result with result.stop_reason in
   {limit_turns, limit_total_tokens, limit_output_tokens}. No exception. The
   in-flight tool finishes, agent.messages stays consistent, and you can simply
   invoke again to continue — useful for "budget per step" loops.

3. Per-invocation, not cumulative
   Reusing an agent does not carry the counters over. Every invoke/stream gets
   the full budget again. (History DOES carry; the budget does not.)

4. Priority & soft caps
   When several trip together: turns > total_tokens > output_tokens.
   output_tokens is a soft cap (checked at turn boundaries; one big response can
   overshoot). A non-positive/non-int cap raises TypeError up front.

5. How it differs from neighbours
   - provider max_tokens : bounds ONE model call; Limits bounds the whole loop.
   - L21 cost controls   : your own $ accounting; Limits is an SDK-native stop.
   - L63 tool offload    : shrinks what each turn COSTS; Limits caps how MANY.
   Use them together for real token economics.
""")


def main() -> None:
    iteration_1_turns_cap()
    iteration_2_token_caps()
    iteration_3_per_invocation_reset()
    iteration_4_priority()
    summary()


if __name__ == "__main__":
    main()

"""
Level 70: Native Interrupts — Human-in-the-Loop Approval Gates
=============================================================
Strands SDK v1.42 — `event.interrupt(...)` + `AgentResult.interrupts` + resume.

Goal: pause the agent loop in the middle of a tool call, hand a structured
approval request back to your code (or a human), and resume EXACTLY where it
left off once the decision arrives — using the SDK-native interrupt primitive,
not a hand-rolled checkpoint-and-branch.

Native interrupts vs the L47 hand-rolled pattern (the framing):
    L47 HITL pattern  — you detect a risky step, stop, persist your own state,
                        and reconstruct the conversation to continue. You own the
                        plumbing and the bugs.
    L70 native        — a hook calls event.interrupt(name, reason=...). The SDK
                        unwinds the loop, returns AgentResult(stop_reason="interrupt",
                        interrupts=[...]), and on resume RE-ENTERS the same hook so
                        event.interrupt() RETURNS the human's response. The loop
                        state is preserved for you; the hook reads linearly.

The elegant part: the hook is written as straight-line code —
    decision = event.interrupt("approve_delete", reason={...})
    if decision != "APPROVE": event.cancel_tool = "denied"
— yet the first time through it RAISES (pausing the agent) and the second time
through (on resume) it RETURNS the human's answer. Same code, two behaviours.

Depends on: L21 / L28 (hooks), L47 (the HITL pattern this replaces), L22 (safety gates)
Unlocks:    approval queues, async human review; pairs with L57 for durable resume.

Iterations:
  1. The interrupt round-trip   — gate a delete tool; pause; inspect interrupts;
                                   resume with APPROVE; the tool runs.
  2. Deny blocks the tool       — resume with DENY; event.cancel_tool skips it.
  3. Interrupts are portable    — the approval request is JSON keyed by id; route
                                   it to a human/queue and resume by that id.

Critical API facts (validated by probe + this lesson, not docs):
    * Raise from a hook: response = event.interrupt(name, reason=<any JSON>).
      First pass RAISES InterruptException (loop pauses). One interrupt per hook
      callback; `name` must be unique across callbacks.
    * The paused run RETURNS normally: result.stop_reason == "interrupt" and
      result.interrupts is a list of Interrupt objects, each with .id, .name, .reason.
    * Resume by re-invoking with InterruptResponseContent blocks:
        agent([{"interruptResponse": {"interruptId": i.id, "response": <value>}}])
      On resume the hook runs again and event.interrupt(...) RETURNS <value>.
    * Block a tool from a BeforeToolCallEvent hook by setting event.cancel_tool =
      "<reason>"; the tool is skipped and the model is told why.
    * Interrupt state lives on the agent in-memory ("session managed in-between
      return and user response"). Same-process resume reuses the agent; durable
      cross-process resume layers a session manager (L57) to persist that state.

Usage:
    LESSON_DOTENV=/path/to/.env uv run python 12_orchestration/interrupts_hitl.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

from tools import get_model

model = get_model("gemini-2.5-flash")

# Module-level audit log so iterations can prove whether the tool actually ran.
DELETED: list[str] = []


@tool
def delete_object(key: str) -> str:
    """Permanently delete the storage object with the given key."""
    DELETED.append(key)
    return f"deleted {key}"


class ApprovalHook(HookProvider):
    """Gate every delete_object call behind a human approval interrupt."""

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.approve)

    def approve(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use["name"] != "delete_object":
            return
        # Straight-line code that PAUSES here on the first pass and RESUMES with
        # the human's answer on the second pass. reason is shown to the approver.
        decision = event.interrupt("approve_delete", reason={"key": event.tool_use["input"].get("key")})
        if decision != "APPROVE":
            event.cancel_tool = "human denied the deletion"


def gated_agent() -> Agent:
    return Agent(
        model=model,
        tools=[delete_object],
        hooks=[ApprovalHook()],
        system_prompt="You delete storage objects by key using the delete_object tool.",
        callback_handler=None,
    )


# ---------------------------------------------------------------------------
# ITERATION 1: the interrupt round-trip (approve)
# ---------------------------------------------------------------------------
# Goal: the agent tries to delete, the loop PAUSES with an interrupt, we inspect
# the request, approve it, and the tool runs on resume.
def iteration_1_round_trip() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 1: pause -> inspect -> APPROVE -> resume (the tool runs)")
    print("=" * 70)
    DELETED.clear()

    agent = gated_agent()
    paused = agent("Delete the object with key 'prod-db'.")
    print(f"  first call: stop_reason={paused.stop_reason!r}")
    for i in paused.interrupts:
        print(f"    interrupt id={i.id[:8]}... name={i.name!r} reason={i.reason}")
    assert paused.stop_reason == "interrupt", "the gated tool should pause the loop"
    assert DELETED == [], "nothing should be deleted before approval"

    responses = [{"interruptResponse": {"interruptId": i.id, "response": "APPROVE"}}
                 for i in paused.interrupts]
    resumed = agent(responses)
    print(f"  after APPROVE: stop_reason={resumed.stop_reason!r}  DELETED={DELETED}")
    assert "prod-db" in DELETED, "the tool should run once approved"
    print("  OK: the loop resumed inside the same hook and the deletion executed.")


# ---------------------------------------------------------------------------
# ITERATION 2: deny blocks the tool
# ---------------------------------------------------------------------------
# Goal: same pause, but the human denies. The hook sets event.cancel_tool, so the
# tool never runs and the model is told the action was blocked.
def iteration_2_deny() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 2: DENY -> event.cancel_tool -> the tool is skipped")
    print("=" * 70)
    DELETED.clear()

    agent = gated_agent()
    paused = agent("Delete the object with key 'prod-db'.")
    assert paused.stop_reason == "interrupt"

    responses = [{"interruptResponse": {"interruptId": i.id, "response": "DENY"}}
                 for i in paused.interrupts]
    resumed = agent(responses)
    print(f"  after DENY: stop_reason={resumed.stop_reason!r}  DELETED={DELETED}")
    print(f"  agent said: {str(resumed).strip()[:60]!r}")
    assert DELETED == [], "a denied deletion must NOT run"
    print("  OK: the human's DENY cancelled the tool — execution is gated, not advisory.")


# ---------------------------------------------------------------------------
# ITERATION 3: the interrupt is portable data (route to a human/queue)
# ---------------------------------------------------------------------------
# Goal: the approval request is plain JSON keyed by interrupt id. Serialize it
# (as if posting to a review queue), get a decision out-of-band, then resume by
# matching that id — you never needed the live result object, just the id.
def iteration_3_portable() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 3: interrupts are JSON you can route to a human, keyed by id")
    print("=" * 70)
    DELETED.clear()

    agent = gated_agent()
    paused = agent("Delete the object with key 'prod-db'.")
    assert paused.stop_reason == "interrupt"

    # What a review queue would store / show a human — pure JSON, no SDK objects.
    queue_items = [{"interruptId": i.id, "name": i.name, "reason": i.reason} for i in paused.interrupts]
    payload = json.dumps(queue_items)
    print(f"  enqueued for human review ({len(payload)} bytes JSON): {queue_items[0]['reason']}")

    # ... time passes; a human approves in some other UI ...
    human_decision = "APPROVE"
    responses = [{"interruptResponse": {"interruptId": item["interruptId"], "response": human_decision}}
                 for item in json.loads(payload)]
    resumed = agent(responses)
    print(f"  resumed from the queued id: DELETED={DELETED}  stop_reason={resumed.stop_reason!r}")
    assert "prod-db" in DELETED, "resuming by the serialized id should run the approved tool"
    print("  OK: the id is the only join key — the pause can span a queue/boundary.")
    print("      (Durable cross-PROCESS resume adds a session manager (L57) to persist interrupt state.)")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L70 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. The primitive
   In a hook:  decision = event.interrupt(name, reason=<json>)
   It RAISES on the first pass (loop pauses) and RETURNS the human's response on
   resume. Block a tool with event.cancel_tool = "<why>".

2. The round-trip
   result.stop_reason == "interrupt"; result.interrupts = [Interrupt(id, name, reason)].
   Resume: agent([{"interruptResponse": {"interruptId": i.id, "response": v}}]).

3. Gated, not advisory
   APPROVE lets the tool run; DENY (via cancel_tool) skips it and tells the model.
   The human's decision controls execution, not just logging.

4. Portable by id
   The interrupt is JSON keyed by id — enqueue it, show a human, resume later by
   that id. You don't need the live result object. Durable cross-process resume
   layers L57 session management to persist the interrupt state.

5. vs neighbours
   - L47 HITL pattern : hand-rolled stop/persist/reconstruct. L70 is the SDK doing it.
   - L29 steering     : auto-guides/blocks via policy. L70 pauses for a HUMAN.
   - L68 limits       : stops on budget. L70 stops for an approval, then continues.
""")


def main() -> None:
    iteration_1_round_trip()
    iteration_2_deny()
    iteration_3_portable()
    summary()


if __name__ == "__main__":
    main()

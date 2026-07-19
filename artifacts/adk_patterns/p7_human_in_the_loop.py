"""ADK pattern 7 — Human-in-the-Loop (the human safety net).

ADK: an ApprovalTool PAUSES execution for human authorization before a high-stakes, irreversible action.
Strands: the SDK-native interrupt round-trip (validated in 12_orchestration/interrupts_hitl.py):
  - a BeforeToolCallEvent hook calls `decision = event.interrupt(name, reason=...)`.
  - first pass RAISES -> the run returns AgentResult(stop_reason="interrupt", interrupts=[...]).
  - resume with [{"interruptResponse": {"interruptId": i.id, "response": <decision>}}]; the hook
    re-enters and event.interrupt() RETURNS the decision. DENY sets event.cancel_tool to skip the tool.

Improvement over v1: v1 used a pre-set boolean gate (no pause). This is the genuine PAUSE -> inspect
the pending interrupt -> RESUME round-trip, the faithful "pause for human authorization".
"""

from _model import gemini
from _harness import tokens_of, audit
from _trace import instrument
from strands import Agent, tool
from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent

LEDGER: list[float] = []   # real money moved — proves whether the action executed


@tool
def issue_refund(amount: float) -> str:
    """Issue an irreversible refund of `amount` dollars to the customer."""
    LEDGER.append(amount)
    return f"Refund of ${amount:.2f} issued."


class ApprovalHook(HookProvider):
    def register_hooks(self, registry: HookRegistry, **_):
        registry.add_callback(BeforeToolCallEvent, self._gate)

    def _gate(self, event: BeforeToolCallEvent):
        if event.tool_use["name"] != "issue_refund":
            return
        # Straight-line code: RAISES (pauses) on first pass, RETURNS the human's decision on resume.
        decision = event.interrupt("approve_refund", reason={"amount": event.tool_use["input"].get("amount")})
        if decision != "APPROVE":
            event.cancel_tool = "human denied the refund"


def _agent():
    return Agent(model=gemini(), tools=[issue_refund], hooks=[ApprovalHook()], callback_handler=None,
                 system_prompt="The customer is owed a refund. Call issue_refund with amount 49.99.")


def _round_trip(decision: str, rec=None):
    LEDGER.clear()
    agent = instrument(_agent(), rec)
    paused = agent("Please process my $49.99 refund.")
    if paused.stop_reason != "interrupt" or not paused.interrupts:
        return {"paused": False, "ledger": list(LEDGER), "tokens": tokens_of(paused)}
    before = list(LEDGER)   # must be empty: nothing ran before the human answered
    responses = [{"interruptResponse": {"interruptId": i.id, "response": decision}} for i in paused.interrupts]
    resumed = agent(responses)
    return {"paused": True, "before": before, "ledger": list(LEDGER),
            "tokens": tokens_of(paused) + tokens_of(resumed)}


def trial(rec=None):
    appr = _round_trip("APPROVE", rec)
    deny = _round_trip("DENY", rec)
    ok = (appr["paused"] and appr["before"] == [] and appr["ledger"] == [49.99]   # paused, then ran on APPROVE
          and deny["paused"] and deny["ledger"] == [])                            # paused, blocked on DENY
    return {"ok": ok, "signal": f"approve_ledger={appr['ledger']} deny_ledger={deny['ledger']}",
            "tokens": appr["tokens"] + deny["tokens"],
            "note": "paused->APPROVE ran; paused->DENY blocked" if ok else "round-trip broke"}


def verify():
    audit("P7 Human-in-the-Loop", trial)


if __name__ == "__main__":
    verify()

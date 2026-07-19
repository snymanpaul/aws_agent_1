"""
Level 84: Multi-Turn Goal-Success Evaluation (local, real runs)
=============================================================
Closes the audit gap: GoalSuccessRate/Faithfulness were referenced but NEVER executed
(ADOT-gated). This evaluates whether a multi-step agent actually ACHIEVES its goal, using
a local goal judge over the real trajectory + real end-state -- no OTel/ADOT required.

Anti-simulation design (no fakes/stubs):
  - The goal is a REAL end-state mutated by real tool calls (refund + ticket-close), not a
    string the model claims. Deterministic goal check reads that state.
  - Discrimination uses a SECOND real run that is constrained so the goal is genuinely not
    reached (close_ticket withheld) -- not a hand-authored failure.
  - Both a deterministic state check AND an LLM goal-judge over the real trajectory.

Run:
  podman start litellm-proxy
  uv run python 13_quality/goal_success_eval.py
"""

from strands import Agent, tool
from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent
from strands.models.openai import OpenAIModel


def _model():
    return OpenAIModel(model_id="gemini-2.5-flash",
                       client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
                       params={"temperature": 0.0})


class Ticket:
    """Real task end-state mutated by tools (the goal is defined over THIS, not model text)."""
    def __init__(self):
        self.refunded = None
        self.closed = False

    def goal_met(self):
        return self.refunded is not None and self.closed


class TrajRec(HookProvider):
    def __init__(self):
        self.calls = []

    def register_hooks(self, registry: HookRegistry, **_):
        registry.add_callback(BeforeToolCallEvent,
                              lambda e: self.calls.append({"tool": e.tool_use.get("name"),
                                                           "args": e.tool_use.get("input")}))


def build(ticket, allow_close=True):
    @tool
    def lookup_account(account_id: str) -> str:
        """Look up a customer account; returns the disputed charge."""
        return f"account {account_id}: one disputed charge of $49.99"

    @tool
    def issue_refund(amount: float) -> str:
        """Issue a refund of `amount` to the customer."""
        ticket.refunded = amount
        return f"refunded ${amount:.2f}"

    tools = [lookup_account, issue_refund]
    if allow_close:
        @tool
        def close_ticket() -> str:
            """Close the support ticket once the issue is resolved."""
            ticket.closed = True
            return "ticket closed"
        tools.append(close_ticket)

    rec = TrajRec()
    agent = Agent(model=_model(), tools=tools, hooks=[rec], callback_handler=None,
                  system_prompt="You are support. Resolve the complaint end to end using the tools available.")
    return agent, rec


GOAL = "Look up the account, issue the $49.99 refund, AND close the ticket."


def judge_goal(calls, ticket):
    traj = "; ".join(f"{c['tool']}({c['args']})" for c in calls) or "(no tools)"
    j = Agent(model=_model(), callback_handler=None,
              system_prompt="Decide if the agent ACHIEVED the goal. Reply with exactly SUCCESS or FAIL.")
    r = str(j(f"Goal: {GOAL}\nTrajectory: {traj}\nEnd state: refunded={ticket.refunded} closed={ticket.closed}\nVerdict:")).strip().upper()
    return "SUCCESS" if "SUCCESS" in r else "FAIL"


def run(allow_close=True):
    ticket = Ticket()
    agent, rec = build(ticket, allow_close=allow_close)
    agent("A customer disputes a $49.99 charge on account ACC-123. Resolve it fully.")
    return ticket, rec.calls


def verify():
    print("[L84] good runs x3 (goal = refund AND close, over real state):")
    good_state, good_judge = [], []
    for i in range(3):
        t, calls = run(allow_close=True)
        gj = judge_goal(calls, t)
        good_state.append(t.goal_met()); good_judge.append(gj)
        print(f"  run{i+1}: goal_met={t.goal_met()} judge={gj} tools={[c['tool'] for c in calls]}")

    print("[L84] sabotaged run (close_ticket withheld -> goal genuinely unreachable):")
    bt, bcalls = run(allow_close=False)
    bj = judge_goal(bcalls, bt)
    print(f"  goal_met={bt.goal_met()} judge={bj} tools={[c['tool'] for c in bcalls]}")

    checks = {
        "good: deterministic goal met 3/3": all(good_state),
        "good: goal-judge SUCCESS 3/3": all(j == "SUCCESS" for j in good_judge),
        "sabotaged: deterministic goal NOT met": not bt.goal_met(),
        "sabotaged: goal-judge FAIL": bj == "FAIL",
        "judge discriminates good vs sabotaged": all(j == "SUCCESS" for j in good_judge) and bj == "FAIL",
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    assert all(checks.values()), "L84 FAILED"
    print("[L84] PASS — multi-turn goal-success measured on real end-state + trajectory, with real discrimination")


if __name__ == "__main__":
    verify()

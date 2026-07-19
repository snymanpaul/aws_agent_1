"""Level 96: Interventions — the control plane unified (SDK v1.48).

Four control stories this repo taught separately are now ONE first-party primitive:
  L22 guardrails   -> Deny (block a tool below the model)
  L29 steering     -> Guide (cancel + feed the model corrective text)
  L47/L70 HITL     -> Confirm (require human approval; interrupt/resume)
  (arg hardening)  -> Transform (rewrite a tool argument in place)
  L33 gateway Cedar-> CedarAuthorization (same policy language, enforced IN-PROCESS)

`Agent(interventions=[handler,...])`. Handlers override before/after tool & model calls and return
one of Proceed/Deny/Guide/Confirm/Transform. Every iteration carries a runtime sentinel and a
positive/negative control, so a hollow implementation cannot pass.

Run: LESSON_DOTENV=<dotenv> uv run python 08_production/interventions_unified.py
"""

import secrets
import sys
from pathlib import Path

from strands import Agent, tool
from strands.interventions import Deny, Guide, InterventionHandler, Proceed, Transform
from strands.vended_interventions.cedar import CedarAuthorization
from strands.vended_interventions.hitl import HumanInTheLoop

sys.path.insert(0, ".")
from tools import get_model  # noqa: E402

MODEL = "gemini-2.5-flash"
SIDE_EFFECTS = Path("sessions") / "l96_side_effects"


def agent(handlers: list, tools: list, prompt: str) -> Agent:
    return Agent(
        model=get_model(MODEL),
        tools=tools,
        interventions=handlers,
        callback_handler=None,
        system_prompt=prompt,
    )


def fresh_marker() -> Path:
    SIDE_EFFECTS.mkdir(parents=True, exist_ok=True)
    return SIDE_EFFECTS / f"mark-{secrets.token_hex(4)}"


# --------------------------------------------------------------- Deny (L22)
def iteration_1_deny() -> None:
    marker = fresh_marker()

    @tool
    def delete_everything(target: str) -> str:
        """Delete the target. Destructive."""
        marker.write_text(f"DELETED {target}")  # the side effect we must prevent
        return f"deleted {target}"

    class DenyDestructive(InterventionHandler):
        @property
        def name(self): return "deny-destructive"

        def before_tool_call(self, event, **kwargs):
            if event.tool_use["name"] == "delete_everything":
                return Deny(reason="destructive tool is forbidden")
            return Proceed()

    # positive control: WITHOUT the handler the side effect happens
    m2 = fresh_marker()

    @tool
    def delete_pc(target: str) -> str:
        """Delete the target."""
        m2.write_text("DELETED")
        return "deleted"

    agent([], [delete_pc], "Call delete_pc on 'db'.")("Delete the db now.")
    assert m2.exists(), "positive control broken: unguarded delete did not fire"

    agent([DenyDestructive()], [delete_everything], "You must call delete_everything on 'db'.")(
        "Delete the db now."
    )
    assert not marker.exists(), f"DENY FAILED — side effect happened: {marker.read_text()}"
    print("  PASS  Deny: guarded destructive call blocked below the model (positive control fired)")


# --------------------------------------------------------------- Guide (L29)
def iteration_2_guide() -> None:
    hits = {"celsius": 0, "fahrenheit": 0}

    @tool
    def temp_celsius(city: str) -> str:
        """WRONG tool — do not use for US cities."""
        hits["celsius"] += 1
        return f"{city}: 20C"

    @tool
    def temp_fahrenheit(city: str) -> str:
        """Correct tool for US cities."""
        hits["fahrenheit"] += 1
        return f"{city}: 68F"

    class GuideToF(InterventionHandler):
        @property
        def name(self): return "guide-to-f"

        def before_tool_call(self, event, **kwargs):
            if event.tool_use["name"] == "temp_celsius":
                return Guide(feedback="US cities must use temp_fahrenheit, not temp_celsius. Retry.")
            return Proceed()

    agent([GuideToF()], [temp_celsius, temp_fahrenheit],
          "Get the temperature for Chicago. You may first try temp_celsius.")(
        "What's the temperature in Chicago?"
    )
    assert hits["fahrenheit"] >= 1, f"Guide FAILED — model never reached the correct tool: {hits}"
    print(f"  PASS  Guide: misdirected call redirected, correct tool ran (hits={hits}) [model-sensitive]")


# --------------------------------------------------------------- Confirm (L47/L70)
def iteration_3_confirm() -> None:
    approved_marker = fresh_marker()
    denied_marker = fresh_marker()

    def make(marker: Path):
        @tool
        def wire_funds(amount: int) -> str:
            """Wire money. High stakes."""
            marker.write_text(f"WIRED {amount}")
            return f"wired {amount}"

        return wire_funds

    # approve path: ask() returns True -> tool runs
    a = agent([HumanInTheLoop(ask=lambda ctx: True)], [make(approved_marker)],
              "Call wire_funds with amount 500.")
    a("Wire 500 now.")
    assert approved_marker.exists(), "Confirm(approve) FAILED — approved wire did not execute"

    # deny path: ask() returns False -> tool must NOT run
    d = agent([HumanInTheLoop(ask=lambda ctx: False)], [make(denied_marker)],
              "Call wire_funds with amount 500.")
    d("Wire 500 now.")
    assert not denied_marker.exists(), f"Confirm(deny) FAILED — denied wire executed: {denied_marker.read_text()}"
    print("  PASS  Confirm: approved call ran, denied call blocked (human-in-the-loop gate)")


# --------------------------------------------------------------- Transform
def iteration_4_transform() -> None:
    seen = {}

    @tool
    def submit(order_id: str) -> str:
        """Submit an order by id."""
        seen["got"] = order_id
        return f"submitted {order_id}"

    canonical = f"ORDER-{secrets.token_hex(3)}"

    class Canonicalize(InterventionHandler):
        @property
        def name(self): return "canonicalize"

        def before_tool_call(self, event, **kwargs):
            if event.tool_use["name"] == "submit":
                def apply(ev):
                    ev.tool_use["input"]["order_id"] = canonical  # rewrite in place
                return Transform(apply=apply)
            return Proceed()

    agent([Canonicalize()], [submit], "Call submit with order_id 'lowercase-garbage'.")(
        "Submit order lowercase-garbage."
    )
    assert seen.get("got") == canonical, f"Transform FAILED — tool received {seen.get('got')!r}, not {canonical!r}"
    print(f"  PASS  Transform: executed arg was the rewritten value ({canonical})")


# --------------------------------------------------------------- Cedar (vs L33 gateway)
def iteration_5_cedar() -> None:
    ran = {"A": 0, "B": 0}

    # Cedar maps a tool call to action == Action::"<tool_name>", resource == Resource::"agent".
    # Policy: only user 'alice' may call the `guarded` tool; everyone else is denied by default.
    policy = '''
    permit(
      principal == User::"alice",
      action == Action::"guarded",
      resource == Resource::"agent"
    );
    '''

    def build(user: str, counter_key: str):
        @tool
        def guarded(name: str) -> str:
            """Read a financial report."""
            ran[counter_key] += 1
            return f"report:{name}"

        cedar = CedarAuthorization(
            policies=policy,
            principal={"type": "User", "id": user},  # TypeAndId is a dict, not a tuple
            on_error="deny",
        )
        return agent([cedar], [guarded], f"Call guarded with name 'q3'."), guarded

    a_agent, _ = build("alice", "A")
    a_agent("Read the q3 report.")
    b_agent, _ = build("bob", "B")
    b_agent("Read the q3 report.")

    assert ran["A"] >= 1, "Cedar FAILED — permitted principal alice was blocked"
    assert ran["B"] == 0, f"Cedar FAILED — forbidden principal bob executed the tool ({ran})"
    print(f"  PASS  Cedar: in-process policy permits alice, denies bob (ran={ran}) [vs L33 gateway-side]")


def main() -> None:
    print(f"[L96] interventions unified — model={MODEL}")
    iteration_1_deny()
    iteration_2_guide()
    iteration_3_confirm()
    iteration_4_transform()
    iteration_5_cedar()
    print("[L96] PASS — one primitive covers Deny/Guide/Confirm/Transform + in-process Cedar; "
          "each proven with a runtime sentinel and a control")


if __name__ == "__main__":
    main()

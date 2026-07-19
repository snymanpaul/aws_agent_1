"""ADK pattern 6 — Iterative Refinement (sculptor).

ADK: LoopAgent + max_iterations + escalate=True (early exit once quality is met).
Strands: a Graph cycle — reviser <-> critic, with set_max_node_executions as the hard cap and a
conditional edge that goes FALSE on GOOD (the escalate / early-exit analog).

Improvements over v1:
  * FORCED STRUCTURED OUTPUT — critic returns a typed Ballot {verdict: Literal['GOOD','REFINE']};
    the loop reads ballot.verdict, not a substring.
  * The early-exit + cap + min-rounds policy is count-driven (deterministic), confirmed by the audit
    harness across N runs.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from _model import gemini
from _harness import tokens_of, audit
from _trace import instrument
from strands import Agent
from strands.multiagent import GraphBuilder
from strands.multiagent.base import Status

CAP = 10
MIN_ROUNDS = 2   # policy: always do >= 2 critique rounds before accepting


class Ballot(BaseModel):
    verdict: Literal["GOOD", "REFINE"] = Field(
        description="GOOD if the tagline is <= 8 words AND names a concrete benefit, else REFINE")
    reason: str = Field(description="one short sentence")


def _verdict(state, node_id: str) -> Optional[str]:
    nr = state.results.get(node_id)
    if nr is None:
        return None
    return getattr(getattr(nr.result, "structured_output", None), "verdict", None)


def _critic_rounds(state) -> int:
    return sum(1 for n in state.execution_order if n.node_id == "critic")


def keep_refining(state) -> bool:
    """Run >= MIN_ROUNDS, then stop (escalate) once the typed verdict is GOOD; cap is the backstop."""
    if _critic_rounds(state) < MIN_ROUNDS:
        return True
    return _verdict(state, "critic") != "GOOD"


def build():
    reviser = Agent(name="reviser", model=gemini(), callback_handler=None,
                    system_prompt=("Write a concise product tagline (<= 8 words, naming a concrete benefit). "
                                   "If given prior feedback or a previous tagline, produce an improved variant. "
                                   "Output only the tagline."))
    critic = Agent(name="critic", model=gemini(), callback_handler=None, structured_output_model=Ballot,
                   system_prompt="Judge the tagline: <= 8 words AND names a concrete benefit.")
    b = GraphBuilder()
    b.add_node(reviser, "reviser")
    b.add_node(critic, "critic")
    b.add_edge("reviser", "critic")
    b.add_edge("critic", "reviser", condition=keep_refining)
    b.set_entry_point("reviser")
    b.reset_on_revisit(True)
    b.set_max_node_executions(CAP)
    return b.build()


def trial(rec=None):
    r = instrument(build(), rec)("A note-taking app that organizes your thoughts automatically with AI.")
    order = [n.node_id for n in r.execution_order]
    final = r.results["critic"].result.structured_output
    ok = (r.status == Status.COMPLETED
          and order.count("reviser") >= 2        # draft overwritten across passes
          and order.count("critic") >= 2
          and len(order) < CAP                    # early-exit before the cap
          and final.verdict == "GOOD")
    return {"ok": ok, "signal": f"order={order} verdict={final.verdict}",
            "tokens": tokens_of(r), "note": f"verdict={final.verdict}"}


def verify():
    audit("P6 Iterative Refinement", trial)


if __name__ == "__main__":
    verify()

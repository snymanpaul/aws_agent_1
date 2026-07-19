"""ADK pattern 5 — Generator & Critic (editor's desk).

ADK: LoopAgent(generator, critic); loop exits when the critic says PASS.
Strands: a real CYCLE in Graph — gen --> critic, and critic --> gen as a CONDITIONAL back-edge taken
only while the verdict != PASS. When PASS, the back-edge is skipped and the graph terminates.

Improvements over v1:
  * FORCED STRUCTURED OUTPUT — the critic is a structured_output_model agent returning a typed
    Ballot {verdict: Literal['PASS','REVISE']}. The loop condition reads ballot.verdict, NOT a
    substring of free text (the brittle parse the gate is trying to eliminate).
  * DETERMINISTIC LOOP — the generator writes a QUALITATIVE headline first (no numbers), so the
    "must contain a number" criterion reliably forces exactly one REVISE->PASS cycle. Reproducibility
    is then confirmed by the audit harness running this N times.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from _model import gemini
from _harness import tokens_of, audit
from _trace import instrument
from strands import Agent
from strands.multiagent import GraphBuilder
from strands.multiagent.base import Status


class Ballot(BaseModel):
    verdict: Literal["PASS", "REVISE"] = Field(
        description="PASS if the headline contains a concrete number or percentage, else REVISE")
    reason: str = Field(description="one short sentence")


def _verdict(state, node_id: str) -> Optional[str]:
    nr = state.results.get(node_id)
    if nr is None:
        return None
    so = getattr(nr.result, "structured_output", None)
    return getattr(so, "verdict", None)


def needs_revision(state) -> bool:
    """Typed back-edge condition: loop only while the critic's ballot verdict is not PASS."""
    return _verdict(state, "critic") != "PASS"


def build():
    gen = Agent(name="gen", model=gemini(), callback_handler=None,
                system_prompt=("Write a punchy one-line product headline. On your FIRST attempt write it "
                               "QUALITATIVELY with NO numbers. If you receive revision feedback, rewrite it to "
                               "INCLUDE a concrete number or percentage. Output only the headline."))
    critic = Agent(name="critic", model=gemini(), callback_handler=None, structured_output_model=Ballot,
                   system_prompt="Judge whether the headline contains a concrete number or percentage.")
    b = GraphBuilder()
    b.add_node(gen, "gen")
    b.add_node(critic, "critic")
    b.add_edge("gen", "critic")
    b.add_edge("critic", "gen", condition=needs_revision)   # cycle + typed conditional exit
    b.set_entry_point("gen")
    b.reset_on_revisit(True)
    b.set_max_node_executions(8)
    return b.build()


def trial(rec=None):
    r = instrument(build(), rec)("Our app now loads much faster after the rewrite.")
    order = [n.node_id for n in r.execution_order]
    final = r.results["critic"].result.structured_output
    ok = (r.status == Status.COMPLETED
          and order.count("gen") >= 2          # looped at least once
          and order.count("critic") >= 2
          and final.verdict == "PASS")         # exited via typed ballot, not substring
    return {"ok": ok, "signal": f"order={order} verdict={final.verdict}",
            "tokens": tokens_of(r), "note": f"verdict={final.verdict} ({final.reason[:40]!r})"}


def verify():
    audit("P5 Generator & Critic", trial)


if __name__ == "__main__":
    verify()

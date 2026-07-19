"""ADK pattern 8 — Composite (mix-and-match).

ADK's own example: coordinator routing -> parallel search -> generator-critic loop, sharing state.
Strands: a Graph node's executor can be any MultiAgentBase (graph.py:168), so primitives nest directly.

Improvement over v1: v1 nested only 2 stages. This builds the article's full 3-stage pipeline:
    triage   = Swarm            (pattern 2)
       -> research = parallel Graph (pattern 3)
            -> compose = cyclic Graph (pattern 5, generator-critic)
proving a Swarm AND two different Graphs compose as nodes, and the chain runs end-to-end.
"""

from _model import gemini
from _harness import tokens_of, audit
from _trace import instrument
from strands.multiagent import GraphBuilder, GraphResult, SwarmResult
from strands.multiagent.base import Status

from p2_coordinator import build as build_swarm          # Swarm
from p3_parallel import build_parallel                   # parallel Graph
from p5_generator_critic import build as build_gencritic  # cyclic Graph


def build():
    b = GraphBuilder()
    b.add_node(build_swarm(), "triage")        # Swarm as node
    b.add_node(build_parallel(), "research")   # parallel Graph as node
    b.add_node(build_gencritic(), "compose")   # cyclic Graph as node
    b.add_edge("triage", "research")
    b.add_edge("research", "compose")
    b.set_entry_point("triage")
    return b.build()


def trial(rec=None):
    r = instrument(build(), rec)("A customer was double-charged and is furious. Triage it, research the impact, "
                                 "then draft a reassuring one-line public headline about our refund fix.")
    triage = r.results.get("triage")
    research = r.results.get("research")
    compose = r.results.get("compose")
    types_ok = (isinstance(getattr(triage, "result", None), SwarmResult)
                and isinstance(getattr(research, "result", None), GraphResult)
                and isinstance(getattr(compose, "result", None), GraphResult))
    final = str(compose.result.results["gen"].result).strip() if compose else ""
    ok = (r.status == Status.COMPLETED
          and set(r.results) == {"triage", "research", "compose"}
          and types_ok
          and len(final) > 0)
    return {"ok": ok, "signal": f"nodes={sorted(r.results)} types_ok={types_ok}",
            "tokens": tokens_of(r), "note": f"headline={final[:70]!r}"}


def verify():
    audit("P8 Composite", trial, n=2)   # heaviest pattern (~11 calls/run); 2 runs to bound cost


if __name__ == "__main__":
    verify()

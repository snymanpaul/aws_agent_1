"""ADK pattern 2 — Coordinator/Dispatcher (concierge).

ADK: LlmAgent coordinator + sub_agents; AutoFlow transfers by reading child `description`.
Strands: Swarm — each agent gets an injected `handoff_to_agent` tool; the coordinator routes by
agent description.

Improvement over v1: tests BOTH directions (a billing query -> billing, a tech query -> tech).
v1 only checked billing, so it would have passed even if routing were biased to always-billing.
"""

from _model import gemini
from _harness import tokens_of, audit
from _trace import instrument
from strands import Agent
from strands.multiagent import Swarm
from strands.multiagent.base import Status


def build():
    coordinator = Agent(name="coordinator", model=gemini(), callback_handler=None,
                        description="Front desk router.",
                        system_prompt=("You are a router. Do NOT answer yourself. Immediately hand off to exactly "
                                       "one agent: 'billing' for charges/refunds/payments, 'tech' for errors/bugs/login."))
    billing = Agent(name="billing", model=gemini(), callback_handler=None,
                    description="Handles billing, charges, refunds, payments.",
                    system_prompt=("You are billing support. Resolve the issue in 1-2 sentences and STOP. "
                                   "Do NOT hand off to any other agent."))
    tech = Agent(name="tech", model=gemini(), callback_handler=None,
                 description="Handles technical errors, bugs, login failures.",
                 system_prompt=("You are tech support. Resolve the issue in 1-2 sentences and STOP. "
                                "Do NOT hand off to any other agent."))
    # repetitive_handoff_* is the documented guard against coordinator<->specialist ping-pong
    # (CLAUDE.md "Streaming Swarm"): abort if the last 3 handoffs cover < 2 unique agents.
    return Swarm([coordinator, billing, tech], entry_point=coordinator, max_handoffs=4, max_iterations=6,
                 repetitive_handoff_detection_window=3, repetitive_handoff_min_unique_agents=2)


def _route(query: str, rec=None):
    r = instrument(build(), rec)(query)
    return set(r.results.keys()), tokens_of(r), r.status


def trial(rec=None):
    bill_nodes, t1, s1 = _route("I was charged twice for my subscription and want a refund.", rec)
    tech_nodes, t2, s2 = _route("My app crashes on login with error 500.", rec)
    ok = (s1 == Status.COMPLETED and s2 == Status.COMPLETED
          and "billing" in bill_nodes and "tech" not in bill_nodes      # billing query -> billing only
          and "tech" in tech_nodes and "billing" not in tech_nodes)     # tech query -> tech only
    return {"ok": ok, "signal": f"bill->{sorted(bill_nodes)} tech->{sorted(tech_nodes)}",
            "tokens": t1 + t2, "note": "both directions routed correctly" if ok else "MISROUTE"}


def verify():
    audit("P2 Coordinator/Dispatcher", trial)


if __name__ == "__main__":
    verify()

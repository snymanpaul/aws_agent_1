"""ADK pattern 1 — Sequential Pipeline (assembly line).

ADK: SequentialAgent + LlmAgent(output_key=...); data flows via session.state, refs as {key}.
Strands: Graph with linear edges; each node's output is auto-injected into the next as
"Inputs from previous nodes" (graph.py:1150). The node_id IS the state key.

Improvement over v1: also proves CONTENT LINEAGE — a unique product codename injected at the input
must survive extract -> analyze -> write, i.e. data really flowed (not just that 3 nodes ran).
"""

from _model import gemini
from _harness import tokens_of, audit
from _trace import instrument
from strands import Agent
from strands.multiagent import GraphBuilder
from strands.multiagent.base import Status

CODENAME = "Zephyr"   # unique sentinel that must propagate end-to-end
TASK = (f"Product '{CODENAME}' Q1 revenue rose 40% to $14M, but churn climbed from 3% to 7% "
        f"and support tickets doubled after its new pricing launched.")


def build():
    extract = Agent(name="extract", model=gemini(), callback_handler=None,
                    system_prompt="Extract the 3 key facts. Keep the product name. Terse bullet list only.")
    analyze = Agent(name="analyze", model=gemini(), callback_handler=None,
                    system_prompt="From the facts, state the single most important implication in one sentence. Keep the product name.")
    write = Agent(name="write", model=gemini(), callback_handler=None,
                  system_prompt="Write a 1-line headline that NAMES the product. Output only the headline.")
    b = GraphBuilder()
    for a, i in [(extract, "extract"), (analyze, "analyze"), (write, "write")]:
        b.add_node(a, i)
    b.add_edge("extract", "analyze")
    b.add_edge("analyze", "write")
    b.set_entry_point("extract")
    return b.build()


def trial(rec=None):
    r = instrument(build(), rec)(TASK)
    order = [n.node_id for n in r.execution_order]
    final = str(r.results["write"].result).strip()
    ok = (r.status == Status.COMPLETED
          and order == ["extract", "analyze", "write"]
          and len(r.results) == 3
          and CODENAME.lower() in final.lower())     # lineage: codename survived the whole pipeline
    return {"ok": ok, "signal": f"order={order}", "tokens": tokens_of(r),
            "note": f"headline={final[:70]!r}"}


def verify():
    audit("P1 Sequential Pipeline", trial)


if __name__ == "__main__":
    verify()

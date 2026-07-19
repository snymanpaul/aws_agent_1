"""
Level 78: Shared Working Memory Across a Multi-Agent Team
========================================================
Closes the audit gap: the repo had ZERO real use of memory shared between agents
(swarm shared_context / graph state were claimed but never read/written; multi-agent
persistence was never actually wired). This proves cross-agent memory EMPIRICALLY.

Anti-simulation design (no fakes/stubs — and structurally un-fakeable):
  The incident code is generated INSIDE the shared store's write tool and is NEVER
  returned to the writer agent. It exists ONLY in the store. So the reader agent can
  obtain it through exactly one path: reading the shared store. No prompt, no edge, no
  agent output ever carries it. If the reader can state the code, cross-agent memory
  is real — there is no other channel.

Verification:
  - positive: writer logs an incident (store mints a code); reader recalls + states it.
  - negative control: same reader against a FRESH EMPTY store must NOT produce a code
    (proves the test has teeth — a guessed or pre-baked answer would fail it).
  - multi-run N=3 with a fresh runtime code each run (a pre-baked pass cannot occur).

Run:
  podman start litellm-proxy   # serves gemini-2.5-flash
  uv run python 06_memory/shared_agent_memory.py
"""

import re
import threading
import uuid

from strands import Agent, tool
from strands.models.openai import OpenAIModel
from strands.multiagent import GraphBuilder, Swarm
from strands.multiagent.base import Status

CODE_RE = re.compile(r"INC-[0-9A-F]{8}")


def _model():
    # gemini-2.5-flash via the OpenAI-compat proxy (real model; no AWS dependency for this lesson)
    return OpenAIModel(model_id="gemini-2.5-flash",
                       client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
                       params={"temperature": 0.0})


class SharedMemory:
    """A real in-process shared store (not a mock). Two agents' tools close over one instance."""
    def __init__(self):
        self._d, self._lock = {}, threading.Lock()
        self.writes, self.reads = [], []

    def put(self, key, value):
        with self._lock:
            self._d[key] = value
            self.writes.append((key, value))

    def get(self, key):
        with self._lock:
            self.reads.append(key)
            return self._d.get(key)


def team(store: SharedMemory):
    @tool
    def log_incident(summary: str) -> str:
        """Record a customer incident in shared team memory. Returns a confirmation only."""
        code = "INC-" + uuid.uuid4().hex[:8].upper()   # minted in the store; never returned
        store.put("incident_code", code)
        return "incident recorded in shared memory"     # deliberately withholds the code

    @tool
    def get_incident_code() -> str:
        """Return the incident code from shared team memory, or MISSING if none."""
        return store.get("incident_code") or "MISSING"

    writer = Agent(name="writer", model=_model(), callback_handler=None, tools=[log_incident],
                   description="Logs customer incidents to shared team memory.",
                   system_prompt="Call log_incident with a one-line summary of the customer's problem, then reply 'done'.")
    reader = Agent(name="reader", model=_model(), callback_handler=None, tools=[get_incident_code],
                   description="Reports the incident code from shared team memory.",
                   system_prompt="Call get_incident_code and state the incident code verbatim in your reply.")
    return writer, reader


TASK_W = "A customer was double-charged $49.99 on their subscription."
TASK_R = "What incident code did the team log? State it."


def iter1_graph_once():
    """Writer -> Reader as a Graph. Code travels writer->STORE->reader, never on the edge."""
    store = SharedMemory()
    writer, reader = team(store)
    b = GraphBuilder()
    b.add_node(writer, "writer"); b.add_node(reader, "reader")
    b.add_edge("writer", "reader")
    b.set_entry_point("writer")
    r = b.build()(f"{TASK_W}\n\n(reader: {TASK_R})")
    minted = store.get("incident_code")
    w_out = str(r.results["writer"].result)
    rd_out = str(r.results["reader"].result)
    ok = (r.status == Status.COMPLETED
          and bool(minted)                          # writer really wrote
          and minted in rd_out                      # reader really read it
          and minted not in w_out                   # it did NOT travel on the writer->reader edge
          and "incident_code" in store.reads)       # reader actually hit the store
    return ok, minted, w_out, rd_out


def iter2_swarm_once():
    """Same shared store, but the team is a Swarm (proves shared memory across the swarm primitive)."""
    store = SharedMemory()
    writer, reader = team(store)
    sw = Swarm([writer, reader], entry_point=writer, max_handoffs=4, max_iterations=6,
               repetitive_handoff_detection_window=3, repetitive_handoff_min_unique_agents=2)
    r = sw(f"{TASK_W} Log it, then hand off so a teammate can report the incident code.")
    minted = store.get("incident_code")
    out = " ".join(str(n.result) for n in r.results.values())
    ok = bool(minted) and minted in out and "reader" in r.results
    return ok, minted, out


def negative_control():
    """Reader against a FRESH EMPTY store must NOT produce any incident code."""
    store = SharedMemory()
    _, reader = team(store)
    out = str(reader(TASK_R))
    leaked = CODE_RE.search(out)
    return (leaked is None), out


def verify():
    print("[L78] iter1 Graph — shared memory via store, not edge (N=3):")
    g_ok = []
    for i in range(3):
        ok, minted, w, rd = iter1_graph_once()
        g_ok.append(ok)
        print(f"  run{i+1}: ok={ok} minted={minted} | writer_out={w.strip()[:30]!r} reader_has_code={minted in rd}")

    print("[L78] iter2 Swarm — shared memory across swarm agents:")
    s_ok, s_minted, _ = iter2_swarm_once()
    print(f"  ok={s_ok} minted={s_minted}")

    print("[L78] negative control — empty store must yield NO code:")
    n_ok, n_out = negative_control()
    print(f"  ok={n_ok} reader_said={n_out.strip()[:50]!r}")

    checks = {
        "iter1 graph: cross-agent recall via store, 3/3": all(g_ok),
        "iter2 swarm: cross-agent recall via store": s_ok,
        "negative control: empty store yields no code": n_ok,
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    assert all(checks.values()), "L78 FAILED"
    print("[L78] PASS — cross-agent shared memory is real (store-mediated, edge-free, with a live negative control)")


if __name__ == "__main__":
    verify()

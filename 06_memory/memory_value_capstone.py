"""
Level 87 (Capstone): Memory-backed agent beats a memoryless baseline on goal-success
===================================================================================
Ties both tracks together: an agentic task whose goal REQUIRES recalling a fact from an
earlier turn. The memory-backed agent recalls it (L78/L79 shared memory) and meets the
goal (L84 goal-success); the memoryless baseline cannot. Graded over N runs and compared
with a permutation test from the unified harness (L85/L86). The capstone claim: memory
yields a SIGNIFICANT goal-success improvement (p<0.05).

Anti-simulation design (no fakes/stubs):
  - Two REAL conditions differing ONLY in memory access. The needed fact lives solely in
    memory (written by a real turn-1 agent); it is never in the turn-2 prompt, so the
    memoryless baseline genuinely cannot know it -- the difference is causal, not authored.
  - Goal is a REAL end-state (refund method) set by a tool; significance from real runs.

Run:
  podman start litellm-proxy
  uv run python 06_memory/memory_value_capstone.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands.models.openai import OpenAIModel

from tools.eval_harness import perm_test   # reuse the unified harness (L86)

N = 12
PREF = "store_credit"


def _model():
    return OpenAIModel(model_id="gemini-2.5-flash",
                       client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
                       params={"temperature": 0.4})


def _norm(s):
    return s.strip().lower().replace(" ", "_").replace("-", "_")


def run_once(memory: bool):
    store, state = {}, {"method": None}

    @tool
    def save_preference(method: str) -> str:
        """Record the customer's preferred refund method in durable memory."""
        store["pref"] = _norm(method)
        return "preference recorded"

    @tool
    def recall_preference() -> str:
        """Return the customer's preferred refund method from durable memory, or UNKNOWN."""
        return store.get("pref", "UNKNOWN")

    @tool
    def issue_refund(method: str) -> str:
        """Issue the refund using the given method."""
        state["method"] = _norm(method)
        return f"refund issued via {method}"

    if memory:
        # turn 1 (earlier interaction): a real agent records the preference into memory
        Agent(model=_model(), tools=[save_preference], callback_handler=None,
              system_prompt="Record the customer's stated refund preference.")(
            "The customer says: please always refund me as store credit.")

    # turn 2: process the refund using the customer's PREFERRED method (never stated in this prompt)
    tools = [issue_refund] + ([recall_preference] if memory else [])
    Agent(model=_model(), tools=tools, callback_handler=None,
          system_prompt="Process the customer's refund using their PREFERRED refund method.")(
        "Please process my $20 refund using my preferred method.")

    return 1 if state["method"] == PREF else 0


def verify():
    print(f"[L87] running memory-backed vs memoryless, N={N} each (goal = refund via remembered preference)...")
    mem = [run_once(True) for _ in range(N)]
    nomem = [run_once(False) for _ in range(N)]
    mem_rate, nomem_rate = sum(mem) / N, sum(nomem) / N
    p = perm_test(mem, nomem)
    print(f"[L87] memory-backed goal-success={mem_rate:.2f}  memoryless={nomem_rate:.2f}  p={p:.4f}")

    checks = {
        "memory-backed achieves the goal most of the time (>=0.8)": mem_rate >= 0.8,
        "memoryless mostly fails (<0.5)": nomem_rate < 0.5,
        "memory beats memoryless": mem_rate > nomem_rate,
        "improvement is significant (p<0.05)": p < 0.05,
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    assert all(checks.values()), "L87 FAILED"
    print("[L87] PASS — memory yields a statistically significant goal-success gain (capstone)")


if __name__ == "__main__":
    verify()

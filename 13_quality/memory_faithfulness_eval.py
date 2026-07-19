"""
Level 88: Memory-Faithfulness Eval (does the agent USE memory, or ignore/contradict it?)
======================================================================================
Bridges memory + evals: having memory is not enough -- the agent must GROUND its answer in
retrieved memory rather than its parametric prior or a user's wrong claim. This measures
faithfulness-to-memory empirically.

Anti-simulation design (no fakes/stubs):
  - The authoritative value is a RUNTIME-RANDOM number (e.g. 43 days) the model cannot have as
    a prior; it lives only in the memory tool. Faithful => the answer contains that exact number.
  - Negative control: with NO memory the agent cannot produce the number (proves grounding, not luck).
  - Pressure probe: the user asserts a WRONG number; a faithful agent still answers from memory.

Run:
  podman start litellm-proxy
  uv run python 13_quality/memory_faithfulness_eval.py
"""

import random

from strands import Agent, tool
from strands.models.openai import OpenAIModel

N = 4


def _model():
    return OpenAIModel(model_id="gemini-2.5-flash",
                       client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
                       params={"temperature": 0.3})


def ask(window, with_memory, user_claim=None):
    @tool
    def recall_refund_policy() -> str:
        """Return the company's authoritative refund-window policy from memory."""
        return f"Company policy: the refund window is {window} days."

    tools = [recall_refund_policy] if with_memory else []
    q = "How many days does a customer have to request a refund?"
    if user_claim:
        q = f"I'm pretty sure the refund window is {user_claim} days, right? " + q
    a = Agent(model=_model(), tools=tools, callback_handler=None,
              system_prompt="Answer using the company's authoritative policy. Be specific about the number of days.")
    return str(a(q))


def verify():
    windows = [random.choice([33, 37, 41, 43, 47, 53]) for _ in range(N)]
    print(f"[L88] runtime memory values: {windows}")

    faithful_mem = sum(1 for w in windows if str(w) in ask(w, with_memory=True)) / N
    leak_nomem = sum(1 for w in windows if str(w) in ask(w, with_memory=False)) / N
    faithful_pressure = sum(1 for w in windows if str(w) in ask(w, with_memory=True, user_claim=14)) / N

    print(f"[L88] with-memory faithfulness   = {faithful_mem:.2f}")
    print(f"[L88] no-memory leakage (control) = {leak_nomem:.2f}  (should be ~0)")
    print(f"[L88] faithful under wrong-user-claim = {faithful_pressure:.2f}")

    checks = {
        "with memory: answer grounded in memory (>=0.75)": faithful_mem >= 0.75,
        "no memory: cannot produce the value (<=0.25)": leak_nomem <= 0.25,
        "grounding is real (memory >> no-memory)": faithful_mem - leak_nomem >= 0.5,
        "stays faithful under a wrong user claim (>=0.75)": faithful_pressure >= 0.75,
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    assert all(checks.values()), "L88 FAILED"
    print("[L88] PASS — agent grounds answers in memory over prior and over a wrong user claim")


if __name__ == "__main__":
    verify()

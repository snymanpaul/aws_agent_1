"""ADK pattern 4 — Hierarchical Decomposition (russian doll).

ADK: an LlmAgent wraps a sub-agent with AgentTool; the sub-agent's whole workflow is one tool call,
nested across levels.
Strands: agents-as-tools — an Agent passed in tools=[...] is auto-wrapped and invoked as one call.
Here: orchestrator --(agent-as-tool)--> researcher --(agent-as-tool)--> analyst  (two agent levels).

Improvements over v1:
  * TWO real agent levels (the actual russian doll), not one.
  * RELIABLE detection by LINEAGE, not callbacks: the deepest agent (analyst) emits a unique sentinel
    code; it can only appear in the orchestrator's final answer if the FULL chain executed. (Probe
    finding: a sub-agent's callback_handler does NOT reliably fire when it runs as a tool, so callback
    counting under-reports nested calls — lineage is the trustworthy signal.)
  * BOUNDED RETRY: nested LLM tool-calls aren't pinned by temp 0 (see README), so we retry up to
    MAX_ATTEMPTS — the repo's rule "treat LLM calls like external APIs: they can fail, retry."
"""

from _model import gemini
from _harness import tokens_of, audit
from _trace import instrument
from strands import Agent

SENTINEL = "RA-7731"      # only the deepest agent emits this; its presence up top proves the chain ran
MAX_ATTEMPTS = 4


def _capture(sink):
    def cb(**kwargs):
        tu = kwargs.get("current_tool_use") or {}
        name = tu.get("name")
        if name and (not sink or sink[-1] != name):
            sink.append(name)
    return cb


def build():
    analyst = Agent(name="analyst", model=gemini(), callback_handler=None,
                    description="Scores partnership risk LOW/MED/HIGH from given facts.",
                    system_prompt=(f"Given facts, output one risk level (LOW/MED/HIGH) with a 5-word reason, "
                                   f"and end your reply with the exact code {SENTINEL}."))
    l1 = []
    researcher = Agent(name="researcher", model=gemini(), tools=[analyst], callback_handler=None,
                       description="Researches a company, then uses analyst to score risk.",
                       system_prompt=("State 3 terse facts about the company, then call the `analyst` tool to "
                                      "score risk, and include analyst's FULL reply (including its code) verbatim."))
    orchestrator = Agent(model=gemini(), tools=[researcher], callback_handler=_capture(l1),
                         system_prompt=("Call the `researcher` tool, then give a 1-line go/no-go verdict that "
                                        "INCLUDES the risk code researcher reports."))
    return orchestrator, l1


def trial(rec=None):
    attempts, total_tok, final = 0, 0, ""
    chain_ok = False
    for attempts in range(1, MAX_ATTEMPTS + 1):
        orchestrator, l1 = build()
        instrument(orchestrator, rec)
        result = orchestrator("Should we partner with Acme Corp? Research and assess risk first.")
        total_tok += tokens_of(result)
        final = str(result).strip()
        # full-chain proof: orchestrator called researcher AND the deepest agent's sentinel surfaced
        if "researcher" in l1 and SENTINEL in final:
            chain_ok = True
            break
    return {"ok": chain_ok, "signal": f"chain_ok={chain_ok}", "tokens": total_tok,
            "note": f"2-level chain ran; attempts={attempts}/{MAX_ATTEMPTS}; sentinel={'found' if chain_ok else 'MISSING'}"}


def verify():
    audit("P4 Hierarchical Decomposition", trial)


if __name__ == "__main__":
    verify()

"""
Level 46: Hybrid DAG-in-Graph — LLM Routing + Deterministic Pipelines

The question this answers: when do I use Graph vs Workflow?
  Answer: use both. At different layers.

  Graph (L8/L46):   LLM decides WHICH pipeline to run → flexible routing
  Workflow (L31):   fixed DAG executes the pipeline → reliable execution

Why they compose well:
  - LLM routing is unpredictable but necessary (you don't know at write-time
    what request is coming)
  - Workflow is deterministic but inflexible (steps are fixed)
  - Composition: LLM handles "what", Workflow handles "how"

The composition primitive: wrap each Workflow as a @tool.
  The router Agent sees a tool list.
  It picks a tool based on the request.
  That tool internally runs the full workflow lifecycle.
  The LLM never touches the pipeline internals.

Depends on: L6 (Agents-as-Tools), L8 (Graph routing), L31 (Workflow DAG)
"""
import re
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands_tools import workflow, calculator
from tools import get_model

model  = get_model("haiku")      # pipeline sub-agents (cheap, fast)
router_model = get_model("claude-sonnet-4")  # router (needs good intent detection)


# ── Workflow lifecycle helper ───────────────────────────────────────────────────

def _run_workflow(tasks: list[dict], wf_id: str) -> str:
    """
    Full workflow lifecycle in one call: create → start → status → delete.
    Returns the status report text (contains all task outputs).
    Each call gets its own Agent — agents are not thread-safe (L40 lesson).
    """
    agent = Agent(model=model, tools=[workflow, calculator], callback_handler=None)

    agent.tool.workflow(action="create", workflow_id=wf_id, tasks=tasks)
    agent.tool.workflow(action="start",  workflow_id=wf_id)
    status = agent.tool.workflow(action="status", workflow_id=wf_id)
    agent.tool.workflow(action="delete", workflow_id=wf_id)

    # Status response: {content: [{type: text, text: "..."}]}
    return "\n".join(
        item.get("text", "")
        for item in status.get("content", [])
        if item.get("text")
    )


# ── Pipeline 1: Ingest ─────────────────────────────────────────────────────────
# Three sequential steps: validate → extract_metadata → index_entry
# Strictly ordered — each step depends on the previous.

@tool
def run_ingest_pipeline(source: str) -> str:
    """
    Run the deterministic document ingestion pipeline for the given source.
    Steps (always in this order): validate → extract_metadata → index_entry.
    Use this for any document, file, or data source that needs to be catalogued.
    """
    wf_id = f"l46_ingest_{uuid.uuid4().hex[:8]}"
    print(f"\n  [Ingest Pipeline] {wf_id} — source: {source!r}")

    result = _run_workflow([
        {
            "task_id": "validate",
            "description": (
                f"You are a document validator. Source: {source!r}. "
                "Check three things: (1) content is non-empty, "
                "(2) format appears readable, (3) no obvious corruption indicators. "
                "Output exactly: VALID or INVALID: <reason>"
            ),
            "tools": ["calculator"],
            "priority": 5,
        },
        {
            "task_id": "extract_metadata",
            "description": (
                "The source document has been validated. Extract three metadata fields: "
                "estimated_word_count (rough order of magnitude), "
                "document_type (article/report/survey/note/other), "
                "primary_topic (3 words max). "
                "Output as key: value, one per line."
            ),
            "tools": ["calculator"],
            "dependencies": ["validate"],
            "priority": 4,
        },
        {
            "task_id": "index_entry",
            "description": (
                "Using the metadata extracted, write a single-line index entry "
                "suitable for a search catalogue. Include document type and topic. "
                "Format: INDEX: <one sentence>"
            ),
            "tools": ["calculator"],
            "dependencies": ["extract_metadata"],
            "priority": 3,
        },
    ], wf_id)

    print(f"  [Ingest Pipeline] complete")
    return result


# ── Pipeline 2: Analysis ───────────────────────────────────────────────────────
# Diamond DAG: research + assess_complexity run in parallel → synthesize merges
# Two independent branches dispatch simultaneously (no shared deps).

@tool
def run_analysis_pipeline(subject: str) -> str:
    """
    Run the deterministic analysis pipeline for the given subject.
    Steps: research and assess_complexity run in parallel, then synthesize merges both.
    Use this for any topic, concept, or technology that needs structured evaluation.
    """
    wf_id = f"l46_analysis_{uuid.uuid4().hex[:8]}"
    print(f"\n  [Analysis Pipeline] {wf_id} — subject: {subject!r}")

    result = _run_workflow([
        {
            "task_id": "research",
            "description": (
                f"You are a researcher. Subject: {subject!r}. "
                "State 3 key facts about this subject. One fact per line. "
                "Facts only — no commentary."
            ),
            "tools": ["calculator"],
            "priority": 5,
            # no dependencies → dispatched immediately
        },
        {
            "task_id": "assess_complexity",
            "description": (
                f"You are a complexity assessor. Subject: {subject!r}. "
                "Rate conceptual complexity 1-5 (1=trivial, 5=expert-only). "
                "Format: COMPLEXITY: N — <one sentence reason>"
            ),
            "tools": ["calculator"],
            "priority": 5,
            # no dependencies → dispatched simultaneously with research
        },
        {
            "task_id": "synthesize",
            "description": (
                "You have research facts and a complexity assessment. "
                "Write a 2-sentence synthesis: "
                "sentence 1 = the single most important fact, "
                "sentence 2 = practical implication for a practitioner. "
                "Format: SYNTHESIS: <two sentences>"
            ),
            "tools": ["calculator"],
            "dependencies": ["research", "assess_complexity"],  # waits for both
            "priority": 3,
        },
    ], wf_id)

    print(f"  [Analysis Pipeline] complete")
    return result


# ── Router Agent ───────────────────────────────────────────────────────────────
# This is the "Graph" layer — LLM decides which tool to call (or none).
# It never executes pipeline logic directly; it only routes.

ROUTER_SYSTEM = """You are a task router. Your only job is to classify each request
and call the appropriate pipeline tool — or answer directly if no pipeline applies.

Routing rules:
  "ingest [source]"     → run_ingest_pipeline   (cataloguing documents/data)
  "analyze [subject]"   → run_analysis_pipeline  (evaluating topics/concepts)
  general question      → answer directly (no tool call)

IMPORTANT: Never do pipeline work yourself. If the request matches a pipeline,
call the tool. The pipeline handles all the steps internally.
When calling a tool, extract just the core subject/source from the request.
"""

router = Agent(
    model=router_model,
    tools=[run_ingest_pipeline, run_analysis_pipeline],
    system_prompt=ROUTER_SYSTEM,
    callback_handler=None,
)


# ── Test requests ──────────────────────────────────────────────────────────────

REQUESTS = [
    # Ingest path
    "ingest: technical report on S3 Vectors launch, 12 pages",
    # Analysis path
    "analyze: retrieval-augmented generation",
    # Direct answer (no pipeline)
    "What is the difference between a Graph and a Workflow in Strands?",
    # Ingest path — different format
    "Please ingest this customer survey from Q1 2026 with 847 responses",
    # Analysis path — different phrasing
    "Can you analyze transformer attention mechanisms for me?",
]


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("L46: Hybrid DAG-in-Graph")
    print("LLM routing + Deterministic Workflow execution")
    print("=" * 60)
    print("""
Architecture:

  User Request
      |
      v
  +------------------+
  |   Router Agent   |  <-- LLM decides which tool to call
  |  (sonnet model)  |
  +--+------------+--+
     |            |
     v            v
  [ingest     [analysis      (or: answer directly)
   pipeline]   pipeline]
     |            |
     v            v
  Workflow     Workflow
  validate     research ─┐
     |         assess    ├─> synthesize
  extract      complexity┘
     |
  index_entry

  LLM layer:  routing only (flexible)
  DAG layer:  execution only (deterministic)
""")

    for i, request in enumerate(REQUESTS, 1):
        print(f"\n{'─' * 60}")
        print(f"[{i}] {request}")
        print(f"{'─' * 60}")
        result = router(request)
        print(f"\n[Response]: {result}")

    print("\n" + "=" * 60)
    print("""Key patterns demonstrated:

  1. Wrap Workflow as @tool — same composition as Agents-as-Tools (L6)
     but the "agent" is a deterministic DAG, not an LLM agent.

  2. Router sees tool descriptions, not pipeline internals.
     LLM can't deviate from the step order — it never touches the steps.

  3. Diamond DAG in Analysis: research + assess_complexity have no
     shared deps → dispatched in parallel automatically.

  4. Fresh Agent per workflow call (_run_workflow creates its own).
     Agents are not thread-safe — never share Agent instances.

  5. Decision rule:
     Use Graph/Agent for routing (which?)
     Use Workflow for execution (how? in what order?)
     The boundary is: the @tool function.
""")

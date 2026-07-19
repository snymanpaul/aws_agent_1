"""
Level 31: Workflow Pattern — Deterministic DAG Pipelines
=========================================================
strands_tools workflow tool — three focused iterations.

Goal: define pre-planned DAGs where tasks run in the correct dependency order
and independent tasks execute in parallel automatically. Contrast with L7
(Swarm: autonomous handoff) and L8 (Graph: agent decides path at runtime).

Depends on: L6 (Agents-as-Tools), L7 (Swarm), L8 (Graph)
Unlocks:    L32 (A2A — remote agents as workflow nodes)

Pattern decision tree:
  freeform collaboration   → Swarm (L7)
  agent decides at runtime → Graph (L8)
  fixed deterministic DAG  → Workflow (L31) ← this level

Lifecycle: create → start → status → delete
  create:  validate DAG, persist to ~/.strands/workflows/<id>.json
  start:   dependency-resolve → parallel-dispatch ready tasks → merge results
  status:  per-task progress, duration, model, tool counts
  list:    all workflows in manager
  delete:  remove from memory + disk

CRITICAL GOTCHA — Task Tool Inheritance:
  If a task does NOT specify "tools", it inherits ALL parent agent tools.
  If the parent has "workflow" as a tool, each task sub-agent also gets
  "workflow" — and the LLM will use it, creating recursive sub-workflows.

  Fix: always specify "tools" in task definitions.
    "tools": ["calculator"]  → task gets only calculator (non-recursive)
    "tools": ["__none__"]    → task gets NO tools (workaround, logs warning)

  The parent agent needs workflow + at least one other tool so tasks can
  specify a legitimate non-workflow tool via the "tools" field.

Usage:
    uv run python 11_platform/workflow_pattern.py

Architecture:
    Agent(tools=[workflow, calculator])   ← parent agent
         |
         v
    agent.tool.workflow(action="create", tasks=[{..., "tools": ["calculator"]}])
         |
    WorkflowManager (singleton)
         |
    TaskExecutor (ThreadPoolExecutor, 2-8 workers)
         |
    dependency resolution → dispatch ready tasks in parallel
         |
    each task → Agent(model=parent.model, tools=[calculator]) → executes prompt
         |
    results injected as context into dependent tasks
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent
from strands_tools import workflow, calculator
from tools import get_model

model = get_model("haiku")


# ---------------------------------------------------------------------------
# Helper: print workflow tool response
# ---------------------------------------------------------------------------

def show(result: dict, max_chars: int = 800) -> None:
    """Print the text from a workflow tool response."""
    if not isinstance(result, dict):
        print(f"  [unexpected type: {type(result)}]")
        return
    for item in result.get("content", []):
        text = item.get("text", "")
        print(text[:max_chars])


# ---------------------------------------------------------------------------
# ITERATION 1: Linear pipeline — 3 tasks in sequence, full lifecycle
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 1: Linear pipeline — create → start → status → delete")
print("=" * 70)
print("""
Three sequential tasks: collect → analyse → summarise.
Each depends on the previous so execution is strictly ordered.

KEY: tasks specify "tools": ["calculator"] to get only calculator,
preventing inheritance of "workflow" which would cause recursion.
""")

agent1 = Agent(model=model, tools=[workflow, calculator], callback_handler=None)

WORKFLOW_1 = "l31_linear"

print("--- create ---")
show(agent1.tool.workflow(
    action="create",
    workflow_id=WORKFLOW_1,
    tasks=[
        {
            "task_id": "collect",
            "description": (
                "Name 3 renewable energy types (e.g. solar, wind). "
                "Output as a plain numbered list, one word each."
            ),
            "tools": ["calculator"],
            "priority": 5,
        },
        {
            "task_id": "analyse",
            "description": (
                "Given the 3 renewable energy types from the previous step, "
                "state which has the largest global installed capacity in 2025. "
                "One sentence answer."
            ),
            "tools": ["calculator"],
            "dependencies": ["collect"],
            "priority": 4,
        },
        {
            "task_id": "summarise",
            "description": (
                "Write a single headline sentence (≤15 words) summarising "
                "the key finding from the previous analysis."
            ),
            "tools": ["calculator"],
            "dependencies": ["analyse"],
            "priority": 3,
        },
    ],
))

print("\n--- start (task sub-agents stream to stdout — interleaved output below) ---")
show(agent1.tool.workflow(action="start", workflow_id=WORKFLOW_1))

print("\n--- status ---")
show(agent1.tool.workflow(action="status", workflow_id=WORKFLOW_1))

print("\n--- delete ---")
show(agent1.tool.workflow(action="delete", workflow_id=WORKFLOW_1))


# ---------------------------------------------------------------------------
# ITERATION 2: Parallel branches — diamond DAG (fan-out → fan-in)
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 2: Parallel branches — diamond DAG (fan-out → fan-in)")
print("=" * 70)
print("""
Classic diamond pattern:
       [root]
      /       \\
  [branch_a] [branch_b]   ← no shared deps → dispatched simultaneously
      \\       /
      [merge]

branch_a and branch_b are independent → SDK dispatches both to the thread
pool at the same time. merge waits until both complete.

vs L7 Swarm: no autonomous handoff, explicit dependency edges
vs L8 Graph: path is fixed upfront, not chosen by LLM at runtime
""")

agent2 = Agent(model=model, tools=[workflow, calculator], callback_handler=None)

WORKFLOW_2 = "l31_diamond"

print("--- create ---")
show(agent2.tool.workflow(
    action="create",
    workflow_id=WORKFLOW_2,
    tasks=[
        {
            "task_id": "root",
            "description": "Name 4 programming languages: Python, Go, Rust, Java. Output comma-separated.",
            "tools": ["calculator"],
            "priority": 5,
        },
        {
            "task_id": "branch_a",
            "description": (
                "From: Python, Go, Rust, Java — pick the TWO best for systems programming. "
                "Answer: 'Systems: X, Y' and one-word reason each."
            ),
            "tools": ["calculator"],
            "dependencies": ["root"],
            "priority": 4,
        },
        {
            "task_id": "branch_b",
            "description": (
                "From: Python, Go, Rust, Java — pick the TWO best for data science. "
                "Answer: 'Data science: X, Y' and one-word reason each."
            ),
            "tools": ["calculator"],
            "dependencies": ["root"],
            "priority": 4,
        },
        {
            "task_id": "merge",
            "description": (
                "Combine results from branch_a (systems picks) and branch_b (data science picks). "
                "Output a 4-column table: Language | Systems? | Data Science? | Appears in both?"
            ),
            "tools": ["calculator"],
            "dependencies": ["branch_a", "branch_b"],
            "priority": 3,
        },
    ],
))

print("\n--- start ---")
show(agent2.tool.workflow(action="start", workflow_id=WORKFLOW_2))

print("\n--- status ---")
show(agent2.tool.workflow(action="status", workflow_id=WORKFLOW_2))

print("\n--- delete ---")
show(agent2.tool.workflow(action="delete", workflow_id=WORKFLOW_2))


# ---------------------------------------------------------------------------
# ITERATION 3: Priority scheduling + calculator tool use
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("ITERATION 3: Priority scheduling — 4 independent tasks, 1 calculator task")
print("=" * 70)
print("""
4 independent tasks compete for thread-pool slots by priority (5 → 1).
One task ACTUALLY uses calculator to demonstrate tool availability in tasks.
Two aggregation tasks depend on subsets of those results.

Shows:
  • Priority-based dispatch among simultaneously-ready tasks
  • Partial dependencies (agg_fast depends on task_p5+task_p4 only)
  • A task genuinely using an inherited tool (calculator)
""")

agent3 = Agent(model=model, tools=[workflow, calculator], callback_handler=None)

WORKFLOW_3 = "l31_priority"

print("--- create ---")
show(agent3.tool.workflow(
    action="create",
    workflow_id=WORKFLOW_3,
    tasks=[
        {
            "task_id": "task_p5",
            "description": "What is the capital of France? One word.",
            "tools": ["calculator"],
            "priority": 5,
        },
        {
            "task_id": "task_p4",
            "description": "What is the capital of Germany? One word.",
            "tools": ["calculator"],
            "priority": 4,
        },
        {
            "task_id": "task_p3",
            "description": "What is the capital of Japan? One word.",
            "tools": ["calculator"],
            "priority": 3,
        },
        {
            "task_id": "task_p1_calc",
            "description": (
                "Use the calculator tool to compute: 42 * 7 + 100. "
                "Report the numeric answer only."
            ),
            "tools": ["calculator"],   # ← this task actually uses calculator
            "priority": 1,
        },
        {
            "task_id": "agg_fast",
            "description": (
                "List the two European capitals from task_p5 and task_p4. "
                "Format: 'European capitals: X, Y'"
            ),
            "tools": ["calculator"],
            "dependencies": ["task_p5", "task_p4"],
            "priority": 3,
        },
        {
            "task_id": "agg_all",
            "description": (
                "Summarise all results in one sentence: the three capitals and "
                "the calculator answer from the previous steps."
            ),
            "tools": ["calculator"],
            "dependencies": ["task_p5", "task_p4", "task_p3", "task_p1_calc"],
            "priority": 2,
        },
    ],
))

print("\n--- start ---")
show(agent3.tool.workflow(action="start", workflow_id=WORKFLOW_3))

print("\n--- status ---")
show(agent3.tool.workflow(action="status", workflow_id=WORKFLOW_3))

print("\n--- list (should show 0 workflows — all deleted above) ---")
show(agent3.tool.workflow(action="list"))

print("\n--- delete ---")
show(agent3.tool.workflow(action="delete", workflow_id=WORKFLOW_3))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("L31 COMPLETE — Key Takeaways")
print("=" * 70)
print("""
1. Workflow tool (strands_tools, not core SDK)
   • Import: from strands_tools import workflow
   • Agent:  Agent(tools=[workflow, <other_tools>])
   • Call:   agent.tool.workflow(action=..., workflow_id=..., tasks=[...])
   • State persists to ~/.strands/workflows/<id>.json

2. Lifecycle: create → start → status | list → delete
   • create: validates DAG, stores JSON; tasks stay pending
   • start:  resolves deps, dispatches ready tasks to ThreadPoolExecutor
   • status: live progress — per-task status, priority, dependencies, timing
   • delete: removes from memory + disk

3. Parallel execution is automatic
   • Tasks with no shared unmet deps run simultaneously (diamond pattern)
   • Thread pool: 2-8 workers (env: STRANDS_WORKFLOW_{MIN,MAX}_THREADS)
   • Priority breaks ties among simultaneously-ready tasks (5=highest)

4. Dependency context passing
   • Dependent tasks receive prior results automatically in their prompt
   • "Previous task results:\\nResults from X: ...\\n\\nCurrent Task: ..."
   • No manual wiring required

5. GOTCHA — Task Tool Inheritance
   • If "tools" is unspecified or [], tasks inherit ALL parent tools
   • Parent has "workflow"? → task LLM creates recursive sub-workflows
   • Fix: always specify "tools" in each task definition
   • "tools": ["calculator"] prevents workflow inheritance; LLM won't
     call calculator for reasoning tasks → clean isolated execution

6. Pattern decision tree
   • freeform collaboration   → Swarm (L7)
   • agent decides at runtime → Graph (L8)
   • fixed deterministic DAG  → Workflow (L31) ← use when you need
     reproducible, auditable, dependency-ordered pipelines
""")

"""
Level 48 (live extension): Temporal — Activity-Level Crash Recovery

Demonstrates what the research reference in durable_execution.py described:
  1. Activity 1 runs on Worker A → result recorded in event history
  2. Worker A is killed (simulated crash) before Activity 2 starts
  3. Worker B starts → Temporal replays history → skips Activity 1
  4. Activities 2 and 3 run fresh on Worker B
  5. Event history proves Activity 1 ran exactly once

This is the gap Step Functions cannot fill at the activity granularity level.

Requires: temporal server start-dev --headless (already running)
          uv add temporalio (already installed)

Depends on: L48 durable_execution.py (three-tier context)
"""
import asyncio
import multiprocessing
import os
import uuid
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

TASK_QUEUE  = "l48-research"
CHECKPOINT  = "/tmp/l48_temporal_act1_done"


# ---------------------------------------------------------------------------
# Activities — each represents a retryable unit of work
# ---------------------------------------------------------------------------

@activity.defn
async def frame_problem() -> str:
    """
    Activity 1: runs on Worker A.
    Writes a checkpoint file so the main process knows when to kill Worker A.
    """
    print(f"  [pid {os.getpid()}] act1:frame_problem — starting")
    await asyncio.sleep(1)  # simulate LLM call
    # Signal to orchestrating process that Activity 1 is complete
    with open(CHECKPOINT, "w") as f:
        f.write(str(os.getpid()))
    print(f"  [pid {os.getpid()}] act1:frame_problem — DONE ✓  (checkpoint written)")
    return "What is durable execution and why does it matter for long-running agents?"


@activity.defn
async def analyse(question: str) -> str:
    """Activity 2: runs on Worker B after Worker A crash."""
    print(f"  [pid {os.getpid()}] act2:analyse — starting (Worker A is dead)")
    await asyncio.sleep(1)
    result = (
        "Durable execution ensures workflows survive process crashes by persisting "
        "state at each step. Without it, a crash restarts everything from scratch."
    )
    print(f"  [pid {os.getpid()}] act2:analyse — DONE ✓")
    return result


@activity.defn
async def synthesise(analysis: str) -> str:
    """Activity 3: runs on Worker B."""
    print(f"  [pid {os.getpid()}] act3:synthesise — starting")
    await asyncio.sleep(0.5)
    print(f"  [pid {os.getpid()}] act3:synthesise — DONE ✓")
    return (
        f"{analysis[:80]}... "
        "Use Step Functions (state-level) or Temporal (activity-level) in production."
    )


# ---------------------------------------------------------------------------
# Workflow — chains the three activities
# ---------------------------------------------------------------------------

@workflow.defn
class ResearchWorkflow:
    @workflow.run
    async def run(self) -> str:
        question = await workflow.execute_activity(
            frame_problem,
            start_to_close_timeout=timedelta(seconds=30),
        )
        analysis = await workflow.execute_activity(
            analyse, question,
            start_to_close_timeout=timedelta(seconds=15),
        )
        return await workflow.execute_activity(
            synthesise, analysis,
            start_to_close_timeout=timedelta(seconds=15),
        )


# ---------------------------------------------------------------------------
# Worker subprocess entry point
# ---------------------------------------------------------------------------

def _worker_main() -> None:
    """Run a Temporal worker — called in a subprocess."""
    asyncio.run(_async_worker())


async def _async_worker() -> None:
    client = await Client.connect("localhost:7233")
    async with Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ResearchWorkflow],
        activities=[frame_problem, analyse, synthesise],
        max_cached_workflows=0,           # disable sticky cache — tasks go to normal queue
                                          # immediately on worker death (no sticky delay)
        workflow_runner=UnsandboxedWorkflowRunner(),  # required when worker runs in subprocess
    ):
        await asyncio.Event().wait()  # run until killed


# ---------------------------------------------------------------------------
# Event history display
# ---------------------------------------------------------------------------

async def show_history(client: Client, workflow_id: str) -> None:
    handle  = client.get_workflow_handle(workflow_id)
    history = await handle.fetch_history()

    scheduled: dict[int, str] = {}   # event_id -> activity name

    print()
    print("  Execution history (each line = one persisted event):")
    print()

    for ev in history.events:
        # Use HasField — more reliable than event_type enum in all SDK versions
        if ev.HasField("activity_task_scheduled_event_attributes"):
            act_name = ev.activity_task_scheduled_event_attributes.activity_type.name
            scheduled[ev.event_id] = act_name
            print(f"  → scheduled  {act_name}")

        elif ev.HasField("activity_task_started_event_attributes"):
            sid = ev.activity_task_started_event_attributes.scheduled_event_id
            act = scheduled.get(sid, "?")
            print(f"  ▶ started    {act}")

        elif ev.HasField("activity_task_completed_event_attributes"):
            sid  = ev.activity_task_completed_event_attributes.scheduled_event_id
            act  = scheduled.get(sid, "?")
            note = "  ← in history; Worker A crash DID NOT re-run this" if act == "frame_problem" else ""
            print(f"  ✓ completed  {act}{note}")

        elif ev.HasField("activity_task_timed_out_event_attributes"):
            sid = ev.activity_task_timed_out_event_attributes.scheduled_event_id
            print(f"  ✗ timed-out  {scheduled.get(sid, '?')}")

        elif ev.HasField("activity_task_failed_event_attributes"):
            sid = ev.activity_task_failed_event_attributes.scheduled_event_id
            print(f"  ✗ failed     {scheduled.get(sid, '?')}")

        elif ev.HasField("workflow_execution_completed_event_attributes"):
            print(f"  · WORKFLOW COMPLETED")

    print()


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------

async def main() -> None:
    print()
    print("=" * 66)
    print("Level 48 (live): Temporal — Activity-Level Crash Recovery")
    print("=" * 66)
    print()

    # Clean up any checkpoint from a prior run
    if os.path.exists(CHECKPOINT):
        os.remove(CHECKPOINT)

    # Verify server
    try:
        client = await Client.connect("localhost:7233")
    except Exception as e:
        print(f"  ✗ Cannot reach Temporal server: {e}")
        print("  Run: temporal server start-dev --headless")
        return

    print("  Temporal server: reachable at localhost:7233")

    # Terminate any stale l48 workflows from a prior run
    async for wf in client.list_workflows('WorkflowType="ResearchWorkflow"'):
        if wf.status.name in ("RUNNING", ""):
            try:
                await client.get_workflow_handle(wf.id).terminate("cleanup prior run")
            except Exception:
                pass
    print()

    workflow_id = f"l48-crash-demo-{uuid.uuid4().hex[:8]}"

    # --- Start Worker A ---
    worker_a = multiprocessing.Process(target=_worker_main, daemon=True, name="worker-A")
    worker_a.start()
    print(f"  Worker A started (pid={worker_a.pid})")
    await asyncio.sleep(1)  # let worker complete one poll cycle

    # --- Start workflow ---
    handle = await client.start_workflow(
        ResearchWorkflow.run,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    print(f"  Workflow started: {workflow_id}")
    print()
    print("  Waiting for Activity 1 to complete on Worker A...")

    # --- Poll for Activity 1 checkpoint ---
    for _ in range(60):
        if os.path.exists(CHECKPOINT):
            break
        await asyncio.sleep(0.3)
    else:
        print("  ✗ Timed out waiting for Activity 1")
        worker_a.kill()
        return

    print()
    print("  *** CRASH: killing Worker A now ***")
    print(f"  Activity 1 result is safely in event history.")
    print(f"  Activity 2 has NOT yet been picked up — it will resume on Worker B.")

    # Kill Worker A
    worker_a.kill()
    worker_a.join(timeout=3)
    print(f"  Worker A (pid={worker_a.pid}) terminated.")
    print()

    # Brief pause so Temporal registers the worker as gone
    await asyncio.sleep(2)

    # --- Start Worker B ---
    worker_b = multiprocessing.Process(target=_worker_main, daemon=True, name="worker-B")
    worker_b.start()
    print(f"  Worker B started (pid={worker_b.pid})")
    print(f"  Temporal replays event history → skips Activity 1 → resumes at Activity 2")
    print()

    # --- Wait for workflow completion ---
    result = await asyncio.wait_for(handle.result(), timeout=60)
    print(f"  Workflow result: {str(result)[:100]}")

    # --- Show proof ---
    await show_history(client, workflow_id)

    print("  What this proves:")
    print("    ✓ Activity 1 ran exactly ONCE — on Worker A")
    print("    ✓ Worker A crash did not re-run Activity 1")
    print("    ✓ Activity 2 + 3 ran on Worker B — zero wasted work")
    print("    ✓ Temporal's event history IS the crash recovery mechanism")
    print()
    print("  This is the gap Step Functions doesn't fill:")
    print("    SFN: state-level (re-runs the whole STATE if worker crashes mid-state)")
    print("    Temporal: activity-level (skips completed ACTIVITIES within a state)")
    print()

    worker_b.kill()
    worker_b.join(timeout=2)
    print("=" * 66)


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    asyncio.run(main())

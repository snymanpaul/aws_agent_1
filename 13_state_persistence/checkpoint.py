"""
Level 65: Experimental Checkpoint — Durable-Execution Contract + Hook Realization
================================================================================
Strands SDK v1.42 — `strands.experimental.checkpoint` (Checkpoint, CheckpointPosition).

Goal: understand the SDK's durable-execution checkpoint CONTRACT (pause the agent
loop at a ReAct cycle boundary, persist its state, resume after a crash) — and,
because the auto-runtime for it is NOT yet wired in 1.42, REALIZE the very same
pattern today by snapshotting at the matching hook boundaries.

The honest situation (proven by probe in iteration 2, not assumed):
    SHIPPED in 1.42 — the DATA CONTRACT:
        Checkpoint(position, cycle_index, snapshot, app_data, schema_version)
        CheckpointPosition = "after_model" | "after_tools"
        to_dict() / from_dict() with schema-version gating.
    NOT SHIPPED in 1.42 — the AUTO RUNTIME:
        The module docstring describes "pause via stop_reason='checkpoint',
        state via AgentResult.checkpoint, resume via a checkpointResume block."
        But AgentResult has NO `checkpoint` field, nothing sets that stop_reason,
        and invoke()/stream() take no checkpoint/resume param. The auto pause/
        resume needs a durability provider (Temporal) + a custom ToolExecutor.

    So this lesson teaches the real contract, PROVES what's wired vs not, and then
    delivers a working durable loop using the L64 snapshot machinery at the two
    positions — which map exactly onto two lifecycle hooks:
        after_model  <-> AfterModelCallEvent
        after_tools  <-> AfterToolCallEvent

Depends on: L64 (snapshots — Checkpoint.snapshot IS a Snapshot.to_dict()),
            L21 / L28 (hooks), L57 (sessions baseline)
Unlocks:    durable execution; swap the manual hooks for Temporal when the
            auto-runtime ships.

Iterations:
  1. The Checkpoint contract      — build one from a real snapshot; JSON round-trip;
                                     schema-version gating; the two positions.
  2. What's wired vs not          — assert, in-lesson, that the auto-runtime is
                                     absent in 1.42 (the probe, as a lesson).
  3. Realize it with hooks        — snapshot at AfterModelCall / AfterToolCall;
                                     collect Checkpoints across cycles.
  4. Crash & resume               — rebuild the last checkpoint onto a FRESH agent
                                     and continue with pre-crash memory intact.

Critical API facts (validated by probe + this lesson, not docs):
    * Checkpoint(position="after_model"|"after_tools", cycle_index=0,
                 snapshot=<Snapshot.to_dict() dict>, app_data={}).
      schema_version is fixed "1.0" (init=False). to_dict()=asdict; from_dict()
      RAISES ValueError on a schema mismatch and warns+ignores unknown keys.
    * Checkpoint.snapshot is a DICT (Snapshot.to_dict()), not a Snapshot object —
      it must be JSON-serializable for cross-process persistence. Rebuild with
      Snapshot.from_dict() on resume.
    * Checkpoint.app_data is SEPARATE from Snapshot.app_data: the SDK never reads
      it; it's for your workflow metadata across checkpoint boundaries.
    * TYPES-ONLY in 1.42: AgentResult has no `checkpoint` field; no code sets
      stop_reason="checkpoint" (only the StopReason literal + the docstring exist);
      invoke/stream accept no checkpoint param. Auto pause/resume => Temporal.
    * Positions map to hooks: after_model=AfterModelCallEvent,
      after_tools=AfterToolCallEvent. Register with agent.add_hook(cb, EventClass);
      inside, event.agent.take_snapshot(...) works.
    * V0 limitations (from the SDK docstring): metrics reset on each resume;
      OpenAIResponsesModel(stateful=True) unsupported; Before/AfterInvocationEvent
      fire on every resume call.

Usage:
    LESSON_DOTENV=/path/to/.env uv run python 13_state_persistence/checkpoint.py
"""

import inspect
import json
import os
import sys
import typing

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands.experimental.checkpoint import CHECKPOINT_SCHEMA_VERSION, Checkpoint
from strands.hooks.events import AfterModelCallEvent, AfterToolCallEvent
from strands.types._snapshot import Snapshot

from tools import get_model

model = get_model("gemini-2.5-flash")

SYS = "Use the add tool for any arithmetic. Be terse."


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def build_agent() -> Agent:
    return Agent(model=model, tools=[add], system_prompt=SYS, callback_handler=None)


# ---------------------------------------------------------------------------
# ITERATION 1: the Checkpoint contract (real, verifiable)
# ---------------------------------------------------------------------------
# Goal: construct a Checkpoint around a real agent snapshot, round-trip it
# through JSON, and show schema-version gating. This is the durable payload.
def iteration_1_contract() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 1: the Checkpoint data contract")
    print("=" * 70)

    agent = build_agent()
    agent.state.set("run_id", "abc-123")
    snap = agent.take_snapshot(preset="session")  # an L64 Snapshot

    ckpt = Checkpoint(
        position="after_model",
        cycle_index=0,
        snapshot=snap.to_dict(),               # a DICT, not a Snapshot object
        app_data={"workflow": "demo", "step": 1},  # your metadata, ignored by SDK
    )
    print(f"  position={ckpt.position}  cycle_index={ckpt.cycle_index}  schema={ckpt.schema_version}")
    print(f"  snapshot is a dict: {isinstance(ckpt.snapshot, dict)}  app_data={ckpt.app_data}")

    wire = json.dumps(ckpt.to_dict())          # persist anywhere
    back = Checkpoint.from_dict(json.loads(wire))
    assert back.position == "after_model" and back.app_data["workflow"] == "demo"
    print(f"  JSON round-trip OK ({len(wire)} bytes) -> position={back.position}")

    # Schema gating: a checkpoint from another SDK version is rejected.
    bad = ckpt.to_dict()
    bad["schema_version"] = "9.9"
    try:
        Checkpoint.from_dict(bad)
        print("  WARN: bad schema_version did not raise")
    except ValueError:
        print(f"  schema_version='9.9' -> ValueError (current is {CHECKPOINT_SCHEMA_VERSION})")
    print("  OK: Checkpoint is a JSON-serializable, version-gated durable payload.")


# ---------------------------------------------------------------------------
# ITERATION 2: what's wired vs not (the probe, as a lesson)
# ---------------------------------------------------------------------------
# Goal: empirically confirm the AUTO trigger/resume runtime is absent in 1.42, so
# we don't pretend a feature works. The contract is shipped; the runtime is not.
def iteration_2_what_is_wired() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 2: is the auto trigger/resume wired in 1.42? (verify, don't assume)")
    print("=" * 70)

    from strands.agent.agent_result import AgentResult
    from strands.types.event_loop import StopReason

    result_fields = set(AgentResult.__dataclass_fields__)
    stop_reasons = set(typing.get_args(StopReason))
    invoke_params = set(inspect.signature(Agent.invoke_async).parameters)

    print(f"  AgentResult fields: {sorted(result_fields)}")
    print(f"  'checkpoint' is a declared StopReason: {'checkpoint' in stop_reasons}")
    print(f"  invoke_async params: {sorted(p for p in invoke_params if p != 'self')}")

    # The docstring promises these; 1.42 does not ship them.
    assert "checkpoint" not in result_fields, "no AgentResult.checkpoint field in 1.42"
    assert "checkpoint" in stop_reasons, "'checkpoint' IS a reserved StopReason literal"
    assert "checkpoint" not in invoke_params and "checkpointResume" not in invoke_params, \
        "no checkpoint/resume parameter on invoke in 1.42"
    print("  OK: the 'checkpoint' StopReason is reserved, but nothing sets it and there is")
    print("      no AgentResult.checkpoint nor resume param -> auto-runtime deferred (Temporal).")
    print("      => realize the pattern ourselves with hooks (iteration 3).")


# ---------------------------------------------------------------------------
# ITERATION 3: realize checkpoints with hooks (working, today)
# ---------------------------------------------------------------------------
# Goal: snapshot at the two CheckpointPositions via their matching hooks and
# collect real Checkpoint objects across the agent's ReAct cycles.
def capture_checkpoints(agent: Agent) -> list:
    """Register after_model / after_tools hooks that snapshot into Checkpoints."""
    checkpoints: list = []
    cycle = {"i": 0}

    def on_after_model(event) -> None:
        snap = event.agent.take_snapshot(preset="session").to_dict()
        checkpoints.append(Checkpoint(position="after_model", cycle_index=cycle["i"], snapshot=snap))

    def on_after_tools(event) -> None:
        snap = event.agent.take_snapshot(preset="session").to_dict()
        checkpoints.append(Checkpoint(position="after_tools", cycle_index=cycle["i"], snapshot=snap))
        cycle["i"] += 1  # after_tools closes a ReAct cycle

    agent.add_hook(on_after_model, AfterModelCallEvent)
    agent.add_hook(on_after_tools, AfterToolCallEvent)
    return checkpoints


def iteration_3_hook_realization() -> list:
    print("\n" + "=" * 70)
    print("ITERATION 3: realize checkpoints with hooks (after_model / after_tools)")
    print("=" * 70)

    agent = build_agent()
    checkpoints = capture_checkpoints(agent)

    result = agent("What is 12 + 30? Use the tool.")
    print(f"  final answer: {str(result).strip()[:40]!r}")
    for c in checkpoints:
        print(f"    checkpoint: position={c.position:12s} cycle={c.cycle_index} "
              f"messages={len(c.snapshot['data']['messages'])}")

    positions = {c.position for c in checkpoints}
    assert positions == {"after_model", "after_tools"}, "both checkpoint positions should fire"
    cycles = [c.cycle_index for c in checkpoints]
    assert cycles == sorted(cycles), "cycle_index should be non-decreasing"
    assert "42" in str(result), "the tool turn should compute 12 + 30 = 42"
    print("  OK: checkpoints captured at both positions across cycles, history growing.")
    return checkpoints


# ---------------------------------------------------------------------------
# ITERATION 4: crash & resume from the last checkpoint
# ---------------------------------------------------------------------------
# Goal: simulate a crash — throw away the agent, rebuild the last checkpoint's
# snapshot onto a FRESH agent, and continue with pre-crash memory intact.
def iteration_4_crash_resume(checkpoints: list) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 4: crash & resume — continue on a fresh agent")
    print("=" * 70)

    last = checkpoints[-1]
    print(f"  resuming from: position={last.position} cycle={last.cycle_index}")

    fresh = build_agent()  # the 'crashed' process is gone; this is a new one
    fresh.load_snapshot(Snapshot.from_dict(last.snapshot))  # rebuild state from the durable payload
    restored = len(fresh.messages)
    print(f"  fresh agent restored {restored} messages from the checkpoint")

    cont = str(fresh("What number did we just compute? One word.")).strip()
    print(f"  continuation: {cont[:40]!r}")
    assert restored == len(last.snapshot["data"]["messages"]), "all checkpoint messages should restore"
    assert "42" in cont, "the resumed agent should recall the pre-crash result"
    print("  OK: durable execution — the resumed agent remembered the answer (42).")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L65 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. Contract vs runtime
   SHIPPED (1.42): the Checkpoint data contract — position ("after_model"/
   "after_tools"), cycle_index, snapshot (a Snapshot.to_dict() dict), app_data,
   schema "1.0", JSON round-trip with version gating.
   NOT SHIPPED: the auto pause/resume. AgentResult has no `checkpoint` field,
   nothing sets stop_reason="checkpoint", invoke takes no resume param. That path
   needs a durability provider (Temporal) + a custom ToolExecutor.

2. Verify wiring, don't trust the docstring
   The module docstring describes the intended user-facing pattern; iteration 2
   proves the runtime isn't there. Probe the surface before building on it.

3. Realize it with hooks today
   after_model = AfterModelCallEvent, after_tools = AfterToolCallEvent. Snapshot in
   each hook -> a Checkpoint per cycle boundary. Same positions the auto-runtime
   will use; you just fire them yourself.

4. Resume = load a snapshot onto a fresh agent
   Checkpoint.snapshot -> Snapshot.from_dict -> agent.load_snapshot. The new
   process continues with full pre-crash history. (V0: metrics reset on resume.)

5. Where it sits
   L64 snapshot = the captured value; L65 checkpoint = that value tagged with a
   cycle position for durable execution; L57 session = continuous auto-persist.
   When the Temporal-backed runtime lands, swap the manual hooks for it.
""")


def main() -> None:
    iteration_1_contract()
    iteration_2_what_is_wired()
    checkpoints = iteration_3_hook_realization()
    iteration_4_crash_resume(checkpoints)
    summary()


if __name__ == "__main__":
    main()

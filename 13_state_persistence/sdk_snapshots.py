"""
Level 64: SDK Snapshots — Selective In-Memory State Capture / Restore
====================================================================
Strands SDK v1.42 — `Agent.take_snapshot(...)` / `Agent.load_snapshot(...)`.

Goal: capture a point-in-time copy of an agent's state as a plain, versioned,
JSON-serializable object you control — then restore it, serialize it, or BRANCH
from it. This is the explicit, in-memory counterpart to L57's session managers,
which auto-persist everything to a backend on every turn.

Snapshots vs sessions (the framing for the whole lesson):
    L57 SessionManager  — automatic, continuous, whole-state, disk/S3-backed,
                          one linear timeline. You opt OUT of persistence.
    L64 Snapshot        — manual, point-in-time, SELECTIVE fields, in-memory,
                          JSON-serializable, immutable. You opt IN, and you can
                          hold many snapshots and branch between them.

Why you'd reach for a snapshot:
    * checkpoint before a risky tool call, roll back if it goes wrong
    * branch one conversation into N "what-if" timelines from a single saved point
    * hand agent state across a process/wire boundary as JSON, with no backend
    * capture only the fields you care about (e.g. just `state`, not messages)

Depends on: L5 / L57 (sessions & state — the auto-persist baseline this contrasts)
Unlocks:    L65 (Experimental Checkpoint — event-positioned AUTO snapshots)

Iterations:
  1. Capture + restore round-trip   — snapshot, mutate, restore; state comes back.
  2. Selective capture              — preset -> include -> exclude; no-args RAISES.
  3. JSON round-trip                — to_dict / from_dict across a wire; schema check.
  4. Branch from one snapshot       — two divergent timelines from one saved point;
                                      the snapshot stays immutable.

Critical API facts (validated by probe + this lesson, not docs):
    * snap = agent.take_snapshot(preset=..., include=[...], exclude=[...], app_data={...})
      Returns a Snapshot. Fields resolve in order: preset -> +include -> -exclude.
    * Fields: messages, state, conversation_manager_state, interrupt_state, system_prompt.
      The ONLY preset, "session", captures the first FOUR (NOT system_prompt).
      Scope is always "agent"; schema_version is "1.0"; created_at auto-fills (ISO Z).
    * take_snapshot() with NO preset and NO include RAISES SnapshotException — the
      resolved field set is empty. exclude-only also raises. There is no "capture
      everything" default; you must name what you want.
    * agent.load_snapshot(snap) restores ONLY the fields present in snap.data;
      absent fields are left UNCHANGED. It validate()s first (bad schema/scope raises).
    * Snapshot.to_dict() -> plain JSON-compatible dict; Snapshot.from_dict(d) rebuilds
      and validates. So a snapshot crosses a process/wire/file boundary with no backend.
    * A snapshot is an immutable deepcopy taken at capture time — branching off it
      does not mutate it, so one snapshot seeds many timelines.
    * Everything here is SYNCHRONOUS and IN-MEMORY: no disk, no async, no backend
      (the whole point of the contrast with L57 FileSessionManager).

Usage:
    # Mechanics use agent.state (deterministic); one real turn powers the branch demo.
    LESSON_DOTENV=/path/to/.env uv run python 13_state_persistence/sdk_snapshots.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent
from strands.types._snapshot import Snapshot
from strands.types.exceptions import SnapshotException

from tools import get_model

model = get_model("gemini-2.5-flash")

SYS = "You are a terse assistant. Answer in as few words as possible."


def fresh_agent() -> Agent:
    return Agent(model=model, system_prompt=SYS, callback_handler=None)


# ---------------------------------------------------------------------------
# ITERATION 1: capture + restore round-trip
# ---------------------------------------------------------------------------
# Goal: snapshot the agent, mutate its state, then restore — the mutation is
# undone. agent.state is a deterministic key-value store, so this needs no LLM.
def iteration_1_round_trip() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 1: capture -> mutate -> restore (state comes back)")
    print("=" * 70)

    agent = fresh_agent()
    agent.state.set("topic", "lambda")
    print(f"  before snapshot: state={agent.state.get()}")

    snap = agent.take_snapshot(preset="session")
    print(f"  snapshot: fields={sorted(snap.data)}  schema={snap.schema_version}  created_at set={bool(snap.created_at)}")

    agent.state.set("topic", "fargate")  # mutate AFTER the snapshot
    print(f"  after mutate:    state={agent.state.get()}")

    agent.load_snapshot(snap)  # roll back
    print(f"  after restore:   state={agent.state.get()}")
    assert agent.state.get()["topic"] == "lambda", "restore should roll the mutation back"
    print("  OK: load_snapshot rolled state back to the captured value.")


# ---------------------------------------------------------------------------
# ITERATION 2: selective capture (preset -> include -> exclude)
# ---------------------------------------------------------------------------
# Goal: snapshots capture only the fields you name. Prove the resolution order
# and that an empty resolved set raises — there is no "everything" default.
def iteration_2_selective() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 2: selective capture — name your fields, or it raises")
    print("=" * 70)

    agent = fresh_agent()
    agent.state.set("k", "v")

    session = agent.take_snapshot(preset="session")
    print(f"  preset='session'         -> {sorted(session.data)}")
    assert "system_prompt" not in session.data, "the 'session' preset omits system_prompt"

    state_only = agent.take_snapshot(include=["state"])
    print(f"  include=['state']        -> {sorted(state_only.data)}")
    assert set(state_only.data) == {"state"}, "include=['state'] should capture only state"

    trimmed = agent.take_snapshot(preset="session", exclude=["messages"])
    print(f"  session minus messages   -> {sorted(trimmed.data)}")
    assert "messages" not in trimmed.data, "exclude should drop messages"

    # No preset and no include => empty resolved set => raises (no default).
    try:
        agent.take_snapshot()
        print("  WARN: no-args take_snapshot did not raise")
    except SnapshotException as e:
        print(f"  take_snapshot()          -> SnapshotException ({str(e)[:46]}...)")

    # An unknown field name is rejected up front.
    try:
        agent.take_snapshot(include=["not_a_field"])
        print("  WARN: invalid field did not raise")
    except SnapshotException:
        print("  include=['not_a_field']  -> SnapshotException (validated up front)")
    print("  OK: fields resolve preset->include->exclude; empty set or bad name raises.")


# ---------------------------------------------------------------------------
# ITERATION 3: JSON round-trip across a wire/file boundary
# ---------------------------------------------------------------------------
# Goal: a snapshot is plain JSON. Serialize it, send it "over a wire", rebuild
# it, and restore — no session backend involved. Tampering the schema is caught.
def iteration_3_json_round_trip() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 3: JSON round-trip — snapshots cross process boundaries")
    print("=" * 70)

    agent = fresh_agent()
    agent.state.set("region", "us-east-1")
    snap = agent.take_snapshot(preset="session")

    wire = json.dumps(snap.to_dict())  # to_dict -> JSON string (could be a file/DB/HTTP body)
    print(f"  serialized {len(wire)} bytes of JSON")
    rebuilt = Snapshot.from_dict(json.loads(wire))  # validates on the way in
    print(f"  rebuilt: fields={sorted(rebuilt.data)}  scope={rebuilt.scope}")

    other = fresh_agent()  # a DIFFERENT agent instance restores from the wire copy
    other.load_snapshot(rebuilt)
    assert other.state.get()["region"] == "us-east-1", "state should survive the JSON round-trip"
    print(f"  restored onto a fresh agent: state={other.state.get()}")

    # A snapshot from a future/unknown schema is rejected, not silently loaded.
    bad = snap.to_dict()
    bad["schema_version"] = "9.9"
    try:
        Snapshot.from_dict(bad)
        print("  WARN: bad schema_version did not raise")
    except SnapshotException:
        print("  schema_version='9.9' -> SnapshotException (version-gated load)")
    print("  OK: snapshots serialize to JSON and validate on load — no backend needed.")


# ---------------------------------------------------------------------------
# ITERATION 4: branch from one snapshot into divergent timelines
# ---------------------------------------------------------------------------
# Goal: one saved point seeds MANY futures. Establish a fact, snapshot, then
# restore-and-ask twice — two timelines, both seeing the fact, snapshot untouched.
def iteration_4_branching() -> None:
    print("\n" + "=" * 70)
    print("ITERATION 4: branch one snapshot into two timelines")
    print("=" * 70)

    agent = fresh_agent()
    agent("Remember: the codeword is ORCHID.")  # one real turn establishes shared history
    base = agent.take_snapshot(preset="session", app_data={"label": "after-codeword"})
    captured = len(base.data["messages"])
    print(f"  base snapshot: {captured} messages  app_data={base.app_data}")

    agent.load_snapshot(base)
    branch_a = str(agent("What is the codeword?")).strip()
    print(f"  branch A (ask plainly):  {branch_a[:50]!r}")

    agent.load_snapshot(base)  # rewind to the SAME point
    branch_b = str(agent("Spell the codeword backwards.")).strip()
    print(f"  branch B (ask reversed): {branch_b[:50]!r}")

    assert "ORCHID" in branch_a.upper(), "branch A should recall the codeword from the snapshot"
    assert len(base.data["messages"]) == captured, "the snapshot is immutable across branches"
    print(f"  base still has {len(base.data['messages'])} messages — branching never mutated it.")
    print("  OK: two divergent timelines grew from one immutable saved point.")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L64 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. What a snapshot is
   snap = agent.take_snapshot(preset="session")   # -> Snapshot (plain object)
   agent.load_snapshot(snap)                       # restore in place
   A point-in-time, SELECTIVE, JSON-serializable, IMMUTABLE copy of agent state.
   In-memory and synchronous — no backend, no async.

2. You name the fields (no "everything" default)
   Fields: messages, state, conversation_manager_state, interrupt_state, system_prompt.
   preset="session" = the first four. Resolution is preset -> +include -> -exclude.
   take_snapshot() with nothing resolved RAISES — capture is always explicit.

3. Restore is partial-by-design
   load_snapshot restores ONLY the fields present; absent fields stay as they are.
   So a `state`-only snapshot rolls back state without touching the transcript.

4. JSON in, JSON out
   to_dict()/from_dict() move a snapshot across a wire, file, or DB with no session
   manager, and from_dict() version-gates the load (schema "1.0").

5. Snapshot vs session vs checkpoint
   L57 session  : auto, continuous, whole-state, disk-backed, ONE timeline.
   L64 snapshot : manual, point-in-time, selective, in-memory, MANY timelines.
   L65 checkpoint (next): auto snapshots taken at event POSITIONS (after_model /
   after_tools) — the same Snapshot machinery, fired by the event loop.
""")


def main() -> None:
    iteration_1_round_trip()
    iteration_2_selective()
    iteration_3_json_round_trip()
    iteration_4_branching()
    summary()


if __name__ == "__main__":
    main()

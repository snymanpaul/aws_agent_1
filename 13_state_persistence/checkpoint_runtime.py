"""Level 95: Checkpoint Runtime End-to-End (SDK v1.48) — real crash, real resume.

L65 (SDK v1.42) found `strands.experimental.checkpoint` was TYPES-ONLY and realized durability via
hooks + snapshots. v1.43 wired the runtime: `Agent(checkpointing=True)` pauses at cycle boundaries
(`after_model`, `after_tools`) with `stop_reason="checkpoint"`, and resumes via
`{"checkpointResume": {"checkpoint": ckpt.to_dict()}}`. This level proves the wired runtime across
REAL OS processes, with the negative control the docs imply: a Checkpoint carries position only —
without a SessionManager there is no state.

Iterations:
  1. In-process resume loop — walk a 2-tool task through every checkpoint to completion; assert
     boundary alternation and exactly-once tool effects.
  2. Cross-process crash + resume — worker A checkpoints after tool 1, SIGKILLs itself (exit -9);
     worker B (fresh process, same FileSessionManager session) resumes from the serialized
     checkpoint, finishes, and must still know a runtime sentinel seen only by worker A.
  3. Negative control — worker C resumes the same checkpoint WITHOUT the session: the sentinel
     cannot appear (Checkpoint != state).
  4. Precedence — during a checkpointing cycle, a BeforeToolCallEvent interrupt wins:
     stop_reason == "interrupt", not "checkpoint" (interrupt > checkpoint).

Run: LESSON_DOTENV=<your dotenv> uv run python 13_state_persistence/checkpoint_runtime.py
"""

import json
import os
import secrets
import signal
import subprocess
import sys
from pathlib import Path

from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

sys.path.insert(0, ".")
from tools import get_model  # noqa: E402

RUN_DIR = Path("sessions") / "l95_runs"
MODEL_NAME = "gemini-2.5-flash"


def paths(run_id: str) -> dict[str, Path]:
    base = RUN_DIR / run_id
    return {
        "base": base,
        "ledger": base / "ledger.jsonl",  # every EXECUTED tool call lands here
        "ckpt": base / "checkpoint.json",
        "sessions": base / "sessions",
    }


def make_tools(ledger: Path):
    @tool
    def record_step(step: str) -> str:
        """Record a pipeline step as executed. Call with the step name."""
        with ledger.open("a") as f:
            f.write(json.dumps({"step": step, "pid": os.getpid()}) + "\n")
        return f"recorded {step}"

    return [record_step]


def build_agent(run_id: str, with_session: bool, session_id: str = "main") -> Agent:
    p = paths(run_id)
    kwargs = {}
    if with_session:
        from strands.session.file_session_manager import FileSessionManager

        p["sessions"].mkdir(parents=True, exist_ok=True)
        kwargs["session_manager"] = FileSessionManager(session_id=session_id, storage_dir=str(p["sessions"]))
    return Agent(
        model=get_model(MODEL_NAME),
        tools=make_tools(p["ledger"]),
        checkpointing=True,
        callback_handler=None,
        system_prompt="You are a terse pipeline runner. Use the record_step tool exactly as asked.",
        **kwargs,
    )


def drive(agent: Agent, first_input) -> tuple:
    """Resume through every checkpoint until a non-checkpoint stop. Returns (result, hops)."""
    result = agent(first_input)
    hops = []
    while result.stop_reason == "checkpoint":
        ck = result.checkpoint
        hops.append((ck.position, ck.cycle_index))
        result = agent({"checkpointResume": {"checkpoint": ck.to_dict()}})
    return result, hops


def ledger_steps(ledger: Path) -> list[str]:
    if not ledger.exists():
        return []
    return [json.loads(line)["step"] for line in ledger.read_text().splitlines()]


TASK = (
    "Remember this run code: {code}. First call record_step with 'one'. After it returns, call "
    "record_step with 'two'. Then reply with exactly: DONE <the run code>."
)


# --------------------------------------------------------------- iteration 1
def iteration_1_resume_loop() -> None:
    run_id = f"iter1-{secrets.token_hex(4)}"
    code = secrets.token_hex(6)
    p = paths(run_id)
    p["base"].mkdir(parents=True, exist_ok=True)
    agent = build_agent(run_id, with_session=False)

    result, hops = drive(agent, TASK.format(code=code))

    steps = ledger_steps(p["ledger"])
    assert steps.count("one") == 1 and steps.count("two") == 1, f"exactly-once violated: {steps}"
    assert len(hops) >= 2, f"expected multiple checkpoints, got {hops}"
    positions = {pos for pos, _ in hops}
    assert positions <= {"after_model", "after_tools"}, positions
    assert "after_tools" in positions, f"no after_tools checkpoint seen: {hops}"
    assert code in str(result), f"final answer lost the run code: {result}"
    print(f"  PASS  iter1: {len(hops)} checkpoints {hops}, ledger exactly-once, code returned")


# --------------------------------------------------------------- iteration 2 + 3 workers
def worker_crash(run_id: str, code: str) -> None:
    """Process A: run until the first after_tools checkpoint, persist it, then die hard."""
    p = paths(run_id)
    agent = build_agent(run_id, with_session=True)
    result = agent(TASK.format(code=code))
    while result.stop_reason == "checkpoint":
        ck = result.checkpoint
        if ck.position == "after_tools":
            p["ckpt"].write_text(json.dumps(ck.to_dict()))
            os.kill(os.getpid(), signal.SIGKILL)  # no cleanup, no atexit — a real crash
        result = agent({"checkpointResume": {"checkpoint": ck.to_dict()}})
    raise SystemExit(3)  # finished without an after_tools checkpoint: test design broken


def worker_resume(run_id: str, with_session: bool) -> None:
    """Process B (session) / C (no session): resume from the serialized checkpoint."""
    p = paths(run_id)
    ck = json.loads(p["ckpt"].read_text())
    agent = build_agent(run_id, with_session=with_session)
    result, _ = drive(agent, {"checkpointResume": {"checkpoint": ck}})
    print(f"FINAL::{result}")


def iteration_2_crash_resume() -> None:
    run_id = f"iter2-{secrets.token_hex(4)}"
    code = secrets.token_hex(6)
    p = paths(run_id)
    p["base"].mkdir(parents=True, exist_ok=True)

    a = subprocess.run([sys.executable, __file__, "worker-crash", run_id, code], capture_output=True, text=True)
    assert a.returncode == -signal.SIGKILL, f"worker A should die by SIGKILL, rc={a.returncode}\n{a.stderr[-400:]}"
    assert p["ckpt"].exists(), "worker A died before persisting its checkpoint"
    steps_after_crash = ledger_steps(p["ledger"])
    assert "one" in steps_after_crash, f"tool 1 should have executed pre-crash: {steps_after_crash}"

    b = subprocess.run([sys.executable, __file__, "worker-resume", run_id], capture_output=True, text=True)
    assert b.returncode == 0, f"worker B failed:\n{b.stderr[-600:]}"
    steps = ledger_steps(p["ledger"])
    assert steps.count("one") == 1, f"resume RE-RAN completed tool 'one': {steps}"
    assert steps.count("two") == 1, f"tool 'two' should run exactly once post-resume: {steps}"
    assert code in b.stdout, "resumed process lost the run code — session state did not survive"
    print(f"  PASS  iter2: SIGKILL at after_tools, fresh-process resume, 'one' x1 'two' x1, code survived")


def iteration_3_negative_no_session() -> None:
    run_id = f"iter3-{secrets.token_hex(4)}"
    code = secrets.token_hex(6)
    p = paths(run_id)
    p["base"].mkdir(parents=True, exist_ok=True)

    a = subprocess.run([sys.executable, __file__, "worker-crash", run_id, code], capture_output=True, text=True)
    assert a.returncode == -signal.SIGKILL and p["ckpt"].exists()

    c = subprocess.run([sys.executable, __file__, "worker-resume-nosession", run_id], capture_output=True, text=True)
    # Whether it errors or answers, the sentinel MUST be absent: the checkpoint carries no state.
    assert code not in c.stdout, "run code appeared WITHOUT a session — checkpoint leaked state?"
    print(f"  PASS  iter3 (negative): no session => code absent (rc={c.returncode}) — Checkpoint != state")


# --------------------------------------------------------------- iteration 4
class InterruptGate(HookProvider):
    """Interrupts the second tool call — during a cycle that would otherwise checkpoint."""

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.gate)

    def gate(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use["input"].get("step") == "two":
            event.interrupt("approve_step_two", reason={"step": "two"})


def iteration_4_precedence() -> None:
    run_id = f"iter4-{secrets.token_hex(4)}"
    code = secrets.token_hex(6)
    p = paths(run_id)
    p["base"].mkdir(parents=True, exist_ok=True)
    agent = build_agent(run_id, with_session=False)
    agent.hooks.add_hook(InterruptGate())

    result = agent(TASK.format(code=code))
    stops = [result.stop_reason]
    while result.stop_reason == "checkpoint":
        result = agent({"checkpointResume": {"checkpoint": result.checkpoint.to_dict()}})
        stops.append(result.stop_reason)

    assert result.stop_reason == "interrupt", f"expected interrupt to win, stops={stops}"
    assert result.interrupts, "interrupt stop without interrupts payload"
    assert "checkpoint" in stops, f"the run never checkpointed before the interrupt: {stops}"
    print(f"  PASS  iter4: stops={stops} — interrupt beat the checkpoint at the gated cycle")


def main() -> None:
    print(f"[L95] checkpoint runtime end-to-end — model={MODEL_NAME}, pid={os.getpid()}")
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    iteration_1_resume_loop()
    iteration_2_crash_resume()
    iteration_3_negative_no_session()
    iteration_4_precedence()
    print("[L95] PASS — wired checkpoint runtime: exactly-once across a real SIGKILL, "
          "state lives in the session (not the checkpoint), interrupt > checkpoint")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "worker-crash":
        worker_crash(sys.argv[2], sys.argv[3])
    elif len(sys.argv) > 1 and sys.argv[1] == "worker-resume":
        worker_resume(sys.argv[2], with_session=True)
    elif len(sys.argv) > 1 and sys.argv[1] == "worker-resume-nosession":
        worker_resume(sys.argv[2], with_session=False)
    else:
        main()

"""
Level 82: Durable Resume of a Multi-Agent Harness (across a real process crash)
=============================================================================
Closes the audit gap: durable resume was proven only for a SINGLE agent (L65/L70/L48);
a multi-agent pipeline with shared memory had never been resumed after a crash.

A 4-stage agent pipeline (intake -> enrich -> decide -> notify) persists each completed
stage to an on-disk ledger and shares memory via an on-disk store. Process 1 runs two
stages then CRASHES (os._exit). Process 2 (fresh) resumes: it SKIPS the completed stages
(idempotent) and finishes, with stage 1's shared memory still available to stage 4.

Anti-simulation design (no fakes/stubs):
  - Real Strands agents per stage; real OS process crash (os._exit), not a flag.
  - run and resume execute in SEPARATE subprocesses sharing only on-disk state.
  - "Not re-run" is measured by a persistent per-stage execution COUNTER that survives the
    crash: completed stages must stay at count 1 after resume (a re-run would bump them).
  - Shared memory is a runtime sentinel written by stage 1; it must survive the crash and
    reach stage 4 in the other process.

Run:
  podman start litellm-proxy
  uv run python 13_state_persistence/durable_multiagent_resume.py
"""

import json
import os
import subprocess
import sys
import uuid

from strands import Agent
from strands.models.openai import OpenAIModel

STAGES = ["intake", "enrich", "decide", "notify"]
PROMPTS = {
    "intake": "Acknowledge a customer billing complaint in one short sentence.",
    "enrich": "Add one short sentence of useful context to a billing complaint.",
    "decide": "Decide in one short sentence whether to refund a billing complaint.",
    "notify": "Draft a one-line customer message. You MUST include the ticket reference given to you.",
}


def _model():
    return OpenAIModel(model_id="gemini-2.5-flash",
                       client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
                       params={"temperature": 0.0})


def _d():
    return os.environ["L82_STATE_DIR"]


def _load(name):
    p = os.path.join(_d(), name)
    return json.load(open(p)) if os.path.exists(p) else {}


def _save(name, obj):
    json.dump(obj, open(os.path.join(_d(), name), "w"))


def run_pipeline(crash_after=None):
    ledger, counter, store = _load("ledger.json"), _load("counter.json"), _load("store.json")
    for stage in STAGES:
        if stage in ledger:          # idempotent: already completed in a prior process -> skip
            continue
        counter[stage] = counter.get(stage, 0) + 1   # this stage is actually RUNNING now
        _save("counter.json", counter)

        prompt = PROMPTS[stage]
        if stage == "notify":
            prompt += f"\nTicket reference (from shared memory): {store.get('ticket')}"
        result = str(Agent(model=_model(), callback_handler=None)(prompt)).strip()

        if stage == "intake":
            store["ticket"] = "TICKET-" + uuid.uuid4().hex[:8].upper()   # shared sentinel
            _save("store.json", store)
        ledger[stage] = result
        _save("ledger.json", ledger)

        if crash_after and stage == crash_after:
            os._exit(137)            # REAL crash mid-pipeline (in-memory state lost)


def _subproc(crash_after, state_dir):
    env = {**os.environ, "L82_STATE_DIR": state_dir}
    return subprocess.run([sys.executable, os.path.abspath(__file__), "run", crash_after or "none"],
                          capture_output=True, text=True, env=env)


def verify():
    import tempfile
    state = tempfile.mkdtemp(prefix="adk_l82_")
    try:
        # PROCESS 1: run intake + enrich, then crash
        p1 = _subproc("enrich", state)
        led1 = json.load(open(os.path.join(state, "ledger.json")))
        cnt1 = json.load(open(os.path.join(state, "counter.json")))
        ticket = json.load(open(os.path.join(state, "store.json"))).get("ticket")
        print(f"[L82] process1 exit={p1.returncode} (crash); done={list(led1)} counters={cnt1} ticket={ticket}")

        # PROCESS 2 (fresh): resume — must skip intake/enrich, finish decide/notify
        p2 = _subproc(None, state)
        led2 = json.load(open(os.path.join(state, "ledger.json")))
        cnt2 = json.load(open(os.path.join(state, "counter.json")))
        print(f"[L82] process2 exit={p2.returncode} (resume); done={list(led2)} counters={cnt2}")

        checks = {
            "process1 crashed (nonzero exit)": p1.returncode != 0,
            "after crash only intake+enrich done": set(led1) == {"intake", "enrich"},
            "resume completed all 4 stages": set(led2) == set(STAGES),
            "completed stages NOT re-run (intake count==1)": cnt2.get("intake") == 1,
            "completed stages NOT re-run (enrich count==1)": cnt2.get("enrich") == 1,
            "resume ran decide+notify once": cnt2.get("decide") == 1 and cnt2.get("notify") == 1,
            "shared memory survived crash: ticket reached stage 4": bool(ticket) and ticket in led2["notify"],
        }
        for k, v in checks.items():
            print(f"  {'PASS' if v else 'FAIL'}  {k}")
        assert all(checks.values()), "L82 FAILED"
        print("[L82] PASS — multi-agent pipeline resumed across a real crash; no re-runs; shared memory intact")
    finally:
        import shutil
        shutil.rmtree(state, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "run":
        crash = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "none" else None
        run_pipeline(crash_after=crash)
    else:
        verify()

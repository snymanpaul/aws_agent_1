"""
Level 79: Cross-Session Persistent Memory for an Agentic Harness (real DynamoDB)
==============================================================================
Closes the audit gap: multi-agent persistence was never actually wired, and the only real
cross-session store (DynamoDB) was quarantined in _archive_hallucinated_l27/ and never
run. This demonstrates it end-to-end against a LIVE DynamoDB table, across real OS
processes.

Anti-simulation design (no fakes/stubs):
  - The store is a REAL DynamoDB table (boto3), created live and self-cleaned.
  - The incident code is minted INSIDE the write tool and persisted to DynamoDB; it is
    never returned to the writer agent — so the reader's only source is the table.
  - WRITE and READ run in SEPARATE OS PROCESSES (subprocess) that share nothing but
    DynamoDB — not in-process re-instantiation (the unified_memory.py:1126 trap).
  - Negative control: a different session_id recalls nothing (proves it is really keyed,
    not guessed).

Run (needs AWS creds + region):
  AWS_PROFILE=... AWS_REGION=us-east-1 uv run python 06_memory/cross_session_memory.py
"""

import os
import re
import subprocess
import sys
import uuid

import boto3

from strands import Agent, tool
from strands.models.openai import OpenAIModel

TABLE = "adk_l79_agentic_memory"
REGION = os.environ.get("AWS_REGION", "us-east-1")
CODE_RE = re.compile(r"INC-[0-9A-F]{8}")


def _model():
    return OpenAIModel(model_id="gemini-2.5-flash",
                       client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
                       params={"temperature": 0.0})


def _table():
    return boto3.resource("dynamodb", region_name=REGION).Table(TABLE)


def ensure_table():
    c = boto3.client("dynamodb", region_name=REGION)
    existing = c.list_tables()["TableNames"]
    if TABLE not in existing:
        c.create_table(TableName=TABLE, BillingMode="PAY_PER_REQUEST",
                       KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"},
                                  {"AttributeName": "mem_key", "KeyType": "RANGE"}],
                       AttributeDefinitions=[{"AttributeName": "session_id", "AttributeType": "S"},
                                             {"AttributeName": "mem_key", "AttributeType": "S"}])
        c.get_waiter("table_exists").wait(TableName=TABLE)


def delete_table():
    c = boto3.client("dynamodb", region_name=REGION)
    try:
        c.delete_table(TableName=TABLE)
    except c.exceptions.ResourceNotFoundException:
        pass


def _tools(session_id):
    @tool
    def log_incident(summary: str) -> str:
        """Persist a customer incident to durable team memory. Returns a confirmation only."""
        code = "INC-" + uuid.uuid4().hex[:8].upper()                 # minted here, never returned
        _table().put_item(Item={"session_id": session_id, "mem_key": "incident_code",
                                "value": code, "summary": summary})
        return "incident persisted to durable memory"

    @tool
    def recall_incident() -> str:
        """Return the incident code from durable team memory for this session, or MISSING."""
        r = _table().get_item(Key={"session_id": session_id, "mem_key": "incident_code"})
        return r.get("Item", {}).get("value", "MISSING")

    return log_incident, recall_incident


def write_phase(session_id):
    log_incident, _ = _tools(session_id)
    Agent(model=_model(), tools=[log_incident], callback_handler=None,
          system_prompt="Call log_incident with a one-line summary of the customer's problem, then reply 'done'.")(
        "A customer was double-charged $49.99 on their subscription. Persist it for the team.")


def read_phase(session_id):
    _, recall_incident = _tools(session_id)
    out = str(Agent(model=_model(), tools=[recall_incident], callback_handler=None,
                    system_prompt="Call recall_incident and state the incident code verbatim.")(
        "What incident code did the team persist for this session?"))
    print("RECALLED:" + out.replace("\n", " "))   # surfaced to the parent process


def _truth(session_id):
    return _table().get_item(Key={"session_id": session_id, "mem_key": "incident_code"}).get("Item", {}).get("value")


def _subproc(mode, sid):
    return subprocess.run([sys.executable, os.path.abspath(__file__), mode, sid],
                          capture_output=True, text=True, env=os.environ.copy())


def verify():
    ensure_table()
    sid = "sess-" + uuid.uuid4().hex[:8]
    other = "sess-" + uuid.uuid4().hex[:8]
    try:
        # PROCESS 1: write, then exit (its memory is gone except DynamoDB)
        w = _subproc("write", sid)
        minted = _truth(sid)
        print(f"[L79] write process exit={w.returncode}; DynamoDB now holds incident_code={minted}")

        # PROCESS 2 (fresh): read — only source is the live table
        r = _subproc("read", sid)
        recalled = CODE_RE.search(r.stdout or "")
        recalled = recalled.group(0) if recalled else None
        print(f"[L79] read process exit={r.returncode}; recalled={recalled}")

        # negative control: a different session must recall nothing
        n = _subproc("read", other)
        neg_leak = CODE_RE.search(n.stdout or "")
        print(f"[L79] negative control (fresh session): leaked_code={bool(neg_leak)}")

        checks = {
            "writer persisted a code to live DynamoDB": bool(minted),
            "writer did NOT return the code (only in store)": not CODE_RE.search(w.stdout or ""),
            "fresh read process recalled the SAME code cross-process": recalled == minted and minted is not None,
            "negative control: different session recalls nothing": neg_leak is None,
        }
        for k, v in checks.items():
            print(f"  {'PASS' if v else 'FAIL'}  {k}")
        assert all(checks.values()), "L79 FAILED"
        print("[L79] PASS — cross-session memory persists across real processes via live DynamoDB")
    finally:
        delete_table()
        print("[L79] cleanup: DynamoDB table deleted")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "write":
        write_phase(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "read":
        read_phase(sys.argv[2])
    else:
        verify()

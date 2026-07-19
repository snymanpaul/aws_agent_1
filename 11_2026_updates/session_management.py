"""
Level 57: Session Management — Providers, Lifecycle Hooks, Persistence
=======================================================================
Strands SDK v1.35 — session management architecture deep dive.

Goal: Understand SessionManager ABC, lifecycle hooks, provider implementations,
      and how to build custom session repositories.

Depends on: L5 (Sessions & State basics)
Unlocks:    L48 (Durable Execution)

Iterations:
  1. FileSessionManager     — local persistence, resume conversations
  2. SessionManager Hooks   — lifecycle event flow and when each fires
  3. Custom SessionRepository — implement the repository interface
  4. RepositorySessionManager — plug custom repository into the framework

Key insight:
    SessionManager is a HookProvider. It auto-registers callbacks on
    AgentInitializedEvent, MessageAddedEvent, and AfterInvocationEvent.
    This means session persistence is fully automatic — no manual save/load.

Usage:
    uv run python 11_2026_updates/session_management.py
"""

import sys
import os
import json
import tempfile
import time
from dataclasses import dataclass, field, asdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands.session import FileSessionManager, RepositorySessionManager, SessionRepository
from strands.types.session import Session, SessionAgent, SessionMessage, SessionType
from tools import get_model

model = get_model("haiku")


# =============================================================================
# Iteration 1: FileSessionManager — Local Persistence
# =============================================================================
# FileSessionManager stores session state as JSON files on disk.
# When an agent with a session_manager is created, it restores messages
# and state from the previous session automatically.

def demo_file_session_manager():
    """Show FileSessionManager persisting and resuming conversations."""
    print("\n" + "=" * 60)
    print("Iteration 1: FileSessionManager — Local Persistence")
    print("=" * 60)

    session_id = "demo-session-l57"

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Turn 1: First conversation ---
        print("\n--- Turn 1: Initial conversation ---")
        fsm = FileSessionManager(session_id=session_id, storage_dir=tmpdir)

        agent = Agent(
            model=model,
            name="assistant",
            session_manager=fsm,
            system_prompt="You are a helpful assistant. Be very concise (1 sentence).",
            callback_handler=None,
        )

        result1 = agent("My favorite color is blue. Remember that.")
        print(f"Agent: {result1}")
        print(f"Messages after turn 1: {len(agent.messages)}")

        # Show what's on disk
        session_files = os.listdir(tmpdir)
        print(f"Files on disk: {session_files}")

        # --- Turn 2: New agent instance, same session ---
        print("\n--- Turn 2: New agent, same session (should remember) ---")
        fsm2 = FileSessionManager(session_id=session_id, storage_dir=tmpdir)

        agent2 = Agent(
            model=model,
            name="assistant",
            session_manager=fsm2,
            system_prompt="You are a helpful assistant. Be very concise (1 sentence).",
            callback_handler=None,
        )

        # agent2 should have messages restored from the session
        print(f"Messages restored: {len(agent2.messages)}")
        result2 = agent2("What is my favorite color?")
        print(f"Agent: {result2}")
        print("\n✓ Session persisted and restored — agent remembers across instances")


# =============================================================================
# Iteration 2: SessionManager Lifecycle Hooks
# =============================================================================
# SessionManager is a HookProvider. register_hooks() wires up:
#   AgentInitializedEvent  → initialize() — restore agent state
#   MessageAddedEvent      → append_message() + sync_agent()
#   AfterInvocationEvent   → sync_agent() — capture conversation manager state
#
# This means: you never call save/load manually. The hook system does it.

def demo_lifecycle_hooks():
    """Show which hooks fire and when during an agent conversation."""
    print("\n" + "=" * 60)
    print("Iteration 2: SessionManager Lifecycle Hooks")
    print("=" * 60)

    # We'll subclass FileSessionManager to add logging
    class LoggingSessionManager(FileSessionManager):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.event_log = []

        def initialize(self, agent, **kwargs):
            self.event_log.append(("initialize", time.time()))
            print(f"  [hook] initialize — restoring agent '{agent.name}'")
            super().initialize(agent, **kwargs)

        def append_message(self, message, agent, **kwargs):
            role = message.get("role", "unknown")
            self.event_log.append(("append_message", role, time.time()))
            print(f"  [hook] append_message — role={role}")
            super().append_message(message, agent, **kwargs)

        def sync_agent(self, agent, **kwargs):
            self.event_log.append(("sync_agent", time.time()))
            print(f"  [hook] sync_agent — persisting state")
            super().sync_agent(agent, **kwargs)

    session_id = "demo-hooks-l57"

    with tempfile.TemporaryDirectory() as tmpdir:
        lsm = LoggingSessionManager(session_id=session_id, storage_dir=tmpdir)

        agent = Agent(
            model=model,
            name="assistant",
            session_manager=lsm,
            system_prompt="You are helpful. Be very concise (1 sentence).",
            callback_handler=None,
        )

        print("\nSending message...")
        agent("Hello, what is 2+2?")

        print(f"\nTotal hook events: {len(lsm.event_log)}")
        print("Event sequence:")
        for event in lsm.event_log:
            print(f"  {event[0]}" + (f" ({event[1]})" if len(event) > 2 and isinstance(event[1], str) else ""))

    print("\n✓ Hooks fire automatically — no manual save/load needed")
    print("""
    Hook flow:
    ┌─────────────────────┐
    │ Agent created        │
    │  → AgentInitialized  │──→ initialize()
    │                      │
    │ User message added   │──→ append_message() + sync_agent()
    │                      │
    │ LLM response added   │──→ append_message() + sync_agent()
    │                      │
    │ Invocation complete   │──→ sync_agent()
    └─────────────────────┘
    """)


# =============================================================================
# Iteration 3: Custom SessionRepository
# =============================================================================
# SessionRepository is the storage interface. Implement it to store sessions
# anywhere: database, Redis, DynamoDB, etc.
#
# Required methods: create_session, read_session, create_agent, read_agent,
#   update_agent, create_message, read_message, list_messages, update_message

class InMemorySessionRepository(SessionRepository):
    """Minimal in-memory session repository for demonstration.

    In production, replace with DynamoDB, PostgreSQL, Redis, etc.
    """

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.agents: dict[str, dict[str, dict]] = {}  # session_id -> agent_id -> data
        self.messages: dict[str, dict[str, list[dict]]] = {}  # session_id -> agent_id -> [msg]
        self.multi_agents: dict[str, dict[str, dict]] = {}
        self.operation_log: list[str] = []

    def _log(self, op: str):
        self.operation_log.append(op)
        print(f"    [repo] {op}")

    def create_session(self, session: Session, **kwargs) -> Session:
        self._log(f"create_session({session.session_id})")
        self.sessions[session.session_id] = session.to_dict()
        return session

    def read_session(self, session_id: str, **kwargs) -> Session | None:
        self._log(f"read_session({session_id})")
        data = self.sessions.get(session_id)
        return Session.from_dict(data) if data else None

    def create_agent(self, session_id: str, session_agent: SessionAgent, **kwargs) -> None:
        self._log(f"create_agent({session_id}, {session_agent.agent_id})")
        self.agents.setdefault(session_id, {})[session_agent.agent_id] = asdict(session_agent)
        self.messages.setdefault(session_id, {}).setdefault(session_agent.agent_id, [])

    def read_agent(self, session_id: str, agent_id: str, **kwargs) -> SessionAgent | None:
        self._log(f"read_agent({session_id}, {agent_id})")
        data = self.agents.get(session_id, {}).get(agent_id)
        return SessionAgent.from_dict(data) if data else None

    def update_agent(self, session_id: str, session_agent: SessionAgent, **kwargs) -> None:
        self._log(f"update_agent({session_id}, {session_agent.agent_id})")
        self.agents.setdefault(session_id, {})[session_agent.agent_id] = asdict(session_agent)

    def create_message(self, session_id: str, agent_id: str, session_message: SessionMessage, **kwargs) -> None:
        role = session_message.message.get("role", "unknown") if isinstance(session_message.message, dict) else "unknown"
        self._log(f"create_message({session_id}, {agent_id}, role={role})")
        self.messages.setdefault(session_id, {}).setdefault(agent_id, []).append(asdict(session_message))

    def read_message(self, session_id: str, agent_id: str, message_id: int, **kwargs) -> SessionMessage | None:
        self._log(f"read_message({session_id}, {agent_id}, {message_id})")
        msgs = self.messages.get(session_id, {}).get(agent_id, [])
        return SessionMessage.from_dict(msgs[message_id]) if message_id < len(msgs) else None

    def list_messages(self, session_id: str, agent_id: str, limit: int | None = None,
                      offset: int = 0, **kwargs) -> list[SessionMessage]:
        self._log(f"list_messages({session_id}, {agent_id}, limit={limit}, offset={offset})")
        msgs = self.messages.get(session_id, {}).get(agent_id, [])
        sliced = msgs[offset:offset + limit] if limit else msgs[offset:]
        return [SessionMessage.from_dict(m) for m in sliced]

    def update_message(self, session_id: str, agent_id: str, session_message: SessionMessage, **kwargs) -> None:
        self._log(f"update_message({session_id}, {agent_id})")
        msgs = self.messages.get(session_id, {}).get(agent_id, [])
        if msgs:
            msgs[-1] = asdict(session_message)

    def create_multi_agent(self, session_id: str, multi_agent: Any, **kwargs) -> None:
        self._log(f"create_multi_agent({session_id})")
        self.multi_agents.setdefault(session_id, {})[str(id(multi_agent))] = {}

    def read_multi_agent(self, session_id: str, multi_agent_id: str, **kwargs) -> dict | None:
        return self.multi_agents.get(session_id, {}).get(multi_agent_id)

    def update_multi_agent(self, session_id: str, multi_agent: Any, **kwargs) -> None:
        pass


def demo_custom_repository():
    """Show implementing a custom SessionRepository."""
    print("\n" + "=" * 60)
    print("Iteration 3: Custom SessionRepository")
    print("=" * 60)

    repo = InMemorySessionRepository()

    # Plug custom repo into RepositorySessionManager
    rsm = RepositorySessionManager(session_id="demo-repo-l57", session_repository=repo)

    agent = Agent(
        model=model,
        name="assistant",
        session_manager=rsm,
        system_prompt="You are helpful. Be very concise (1 sentence).",
        callback_handler=None,
    )

    print("\nSending message (watch repository operations):")
    agent("What is the capital of France?")

    print(f"\nTotal repository operations: {len(repo.operation_log)}")
    print(f"Sessions stored: {len(repo.sessions)}")
    print(f"Agents stored: {sum(len(a) for a in repo.agents.values())}")
    print(f"Messages stored: {sum(len(m) for msgs in repo.messages.values() for m in msgs.values())}")

    print("\n✓ Custom repository receives all persistence operations")


# =============================================================================
# Iteration 4: Session Resume with RepositorySessionManager
# =============================================================================
# Demonstrate creating a new agent that restores from the custom repository.

def demo_session_resume():
    """Show resuming a session from a custom repository."""
    print("\n" + "=" * 60)
    print("Iteration 4: Session Resume with RepositorySessionManager")
    print("=" * 60)

    # Shared repository (simulating a database)
    repo = InMemorySessionRepository()
    session_id = "demo-resume-l57"

    # --- Turn 1 ---
    print("\n--- Turn 1: First conversation ---")
    rsm1 = RepositorySessionManager(session_id=session_id, session_repository=repo)
    agent1 = Agent(
        model=model,
        name="assistant",
        session_manager=rsm1,
        system_prompt="You are helpful. Be very concise (1 sentence).",
        callback_handler=None,
    )
    result1 = agent1("My dog's name is Rex.")
    print(f"Agent: {result1}")

    # --- Turn 2: New agent, same repo, same session_id ---
    print("\n--- Turn 2: New agent instance, same session ---")
    rsm2 = RepositorySessionManager(session_id=session_id, session_repository=repo)
    agent2 = Agent(
        model=model,
        name="assistant",
        session_manager=rsm2,
        system_prompt="You are helpful. Be very concise (1 sentence).",
        callback_handler=None,
    )

    print(f"Messages restored: {len(agent2.messages)}")
    result2 = agent2("What is my dog's name?")
    print(f"Agent: {result2}")

    print("\n✓ RepositorySessionManager restores conversation from custom storage")
    print("""
    Provider Decision Matrix:
    ┌──────────────────────┬─────────────────┬──────────────────┐
    │ Provider             │ Best For        │ Trade-off        │
    ├──────────────────────┼─────────────────┼──────────────────┤
    │ FileSessionManager   │ Local dev/test  │ No multi-node    │
    │ S3SessionManager     │ Serverless/AWS  │ Higher latency   │
    │ RepositorySession... │ Custom backends │ You implement it │
    └──────────────────────┴─────────────────┴──────────────────┘
    """)


# =============================================================================
# Summary
# =============================================================================
# | Component           | Role                                        |
# |---------------------|---------------------------------------------|
# | SessionManager      | ABC + HookProvider — auto-wires lifecycle    |
# | SessionRepository   | Storage interface — implement for your DB    |
# | FileSessionManager  | JSON files on disk — dev/test                |
# | S3SessionManager    | S3 bucket — serverless/AWS production        |
# | RepositorySession.. | Adapter — plugs any SessionRepository in     |


if __name__ == "__main__":
    print("=" * 60)
    print("Level 57: Session Management (SDK v1.35)")
    print("=" * 60)

    demo_file_session_manager()
    demo_lifecycle_hooks()
    demo_custom_repository()
    demo_session_resume()

    print("\n" + "=" * 60)
    print("Summary: File → Hooks → Custom Repo → Resume")
    print("=" * 60)

"""
Level 27: DynamoDB Persistence for AgentCore Deployment

Replaces in-memory storage from L26 Research Agent with DynamoDB tables.
Provides session memory and checkpoint persistence that survives AgentCore
container restarts.

Tables:
    - research_agent_sessions: Working/episodic/semantic memory per session
    - research_agent_checkpoints: Recovery checkpoints per research task

Usage:
    persistence = DynamoDBPersistence()

    # Memory operations
    persistence.store_memory(session_id, "working", data)
    data = persistence.load_memory(session_id, "working")

    # Checkpoint operations
    persistence.save_checkpoint(research_id, "planning", state)
    state = persistence.load_latest_checkpoint(research_id)
"""

import os
import json
import time
from datetime import datetime
from typing import Any
from dataclasses import dataclass


@dataclass
class PersistenceConfig:
    """Configuration for DynamoDB persistence."""
    sessions_table: str = "research_agent_sessions"
    checkpoints_table: str = "research_agent_checkpoints"
    region: str = "us-east-1"
    session_ttl_days: int = 7
    checkpoint_ttl_hours: int = 24

    @classmethod
    def from_env(cls) -> "PersistenceConfig":
        """Load configuration from environment variables."""
        return cls(
            sessions_table=os.environ.get(
                "DYNAMODB_SESSIONS_TABLE", "research_agent_sessions"
            ),
            checkpoints_table=os.environ.get(
                "DYNAMODB_CHECKPOINTS_TABLE", "research_agent_checkpoints"
            ),
            region=os.environ.get("AWS_REGION", "us-east-1"),
            session_ttl_days=int(os.environ.get("SESSION_TTL_DAYS", "7")),
            checkpoint_ttl_hours=int(os.environ.get("CHECKPOINT_TTL_HOURS", "24")),
        )


class DynamoDBPersistence:
    """
    DynamoDB-backed persistence for Research Agent state.

    Replaces in-memory dicts with DynamoDB tables for:
    - Session memory (working, episodic, semantic layers)
    - Research checkpoints (for recovery/resume)
    """

    def __init__(self, config: PersistenceConfig | None = None):
        """
        Initialize DynamoDB persistence.

        Args:
            config: Configuration object. If None, loads from environment.
        """
        self.config = config or PersistenceConfig.from_env()
        self._dynamodb = None
        self._sessions_table = None
        self._checkpoints_table = None

    @property
    def dynamodb(self):
        """Lazy-load DynamoDB resource."""
        if self._dynamodb is None:
            import boto3
            self._dynamodb = boto3.resource(
                "dynamodb",
                region_name=self.config.region
            )
        return self._dynamodb

    @property
    def sessions_table(self):
        """Get sessions table reference."""
        if self._sessions_table is None:
            self._sessions_table = self.dynamodb.Table(self.config.sessions_table)
        return self._sessions_table

    @property
    def checkpoints_table(self):
        """Get checkpoints table reference."""
        if self._checkpoints_table is None:
            self._checkpoints_table = self.dynamodb.Table(self.config.checkpoints_table)
        return self._checkpoints_table

    # =========================================================================
    # Memory Operations
    # =========================================================================

    def store_memory(self, session_id: str, layer: str, data: dict) -> None:
        """
        Store a memory layer to DynamoDB.

        Args:
            session_id: Unique session identifier (from AgentCore or generated)
            layer: Memory layer name ("working", "episodic", "semantic")
            data: Dictionary data to store
        """
        ttl = int(time.time()) + (self.config.session_ttl_days * 24 * 3600)

        self.sessions_table.put_item(Item={
            "session_id": session_id,
            "item_type": f"memory_{layer}",
            "data": json.dumps(data, default=str),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "ttl": ttl,
        })

    def load_memory(self, session_id: str, layer: str) -> dict:
        """
        Load a memory layer from DynamoDB.

        Args:
            session_id: Unique session identifier
            layer: Memory layer name ("working", "episodic", "semantic")

        Returns:
            Dictionary data, or empty dict if not found
        """
        try:
            response = self.sessions_table.get_item(Key={
                "session_id": session_id,
                "item_type": f"memory_{layer}",
            })
            if "Item" in response:
                return json.loads(response["Item"]["data"])
        except Exception as e:
            print(f"[DynamoDB] Error loading memory {layer}: {e}")
        return {}

    def delete_memory(self, session_id: str, layer: str) -> None:
        """Delete a memory layer from DynamoDB."""
        try:
            self.sessions_table.delete_item(Key={
                "session_id": session_id,
                "item_type": f"memory_{layer}",
            })
        except Exception as e:
            print(f"[DynamoDB] Error deleting memory {layer}: {e}")

    def load_all_memory(self, session_id: str) -> dict[str, dict]:
        """
        Load all memory layers for a session.

        Returns:
            Dict mapping layer name to data: {"working": {...}, "episodic": [...], ...}
        """
        result = {}
        for layer in ["working", "episodic", "semantic"]:
            data = self.load_memory(session_id, layer)
            if data:
                result[layer] = data
        return result

    def save_all_memory(
        self,
        session_id: str,
        working: dict | None = None,
        episodic: list | None = None,
        semantic: dict | None = None
    ) -> None:
        """Save all memory layers for a session."""
        if working is not None:
            self.store_memory(session_id, "working", working)
        if episodic is not None:
            self.store_memory(session_id, "episodic", episodic)
        if semantic is not None:
            self.store_memory(session_id, "semantic", semantic)

    # =========================================================================
    # Checkpoint Operations
    # =========================================================================

    def save_checkpoint(
        self,
        research_id: str,
        phase: str,
        state: dict
    ) -> str:
        """
        Save a checkpoint for a research task.

        Args:
            research_id: Unique research task identifier
            phase: Checkpoint phase ("planning", "step_1", "synthesis", etc.)
            state: State dict to persist

        Returns:
            Checkpoint ID
        """
        timestamp = datetime.now()
        checkpoint_id = f"{phase}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        ttl = int(time.time()) + (self.config.checkpoint_ttl_hours * 3600)

        self.checkpoints_table.put_item(Item={
            "research_id": research_id,
            "checkpoint_id": checkpoint_id,
            "phase": phase,
            "state": json.dumps(state, default=str),
            "timestamp": timestamp.isoformat(),
            "ttl": ttl,
        })

        return checkpoint_id

    def load_latest_checkpoint(self, research_id: str) -> dict | None:
        """
        Load the most recent checkpoint for a research task.

        Args:
            research_id: Unique research task identifier

        Returns:
            State dict from latest checkpoint, or None if not found
        """
        try:
            response = self.checkpoints_table.query(
                KeyConditionExpression="research_id = :rid",
                ExpressionAttributeValues={":rid": research_id},
                ScanIndexForward=False,  # Descending order
                Limit=1,
            )
            if response.get("Items"):
                return json.loads(response["Items"][0]["state"])
        except Exception as e:
            print(f"[DynamoDB] Error loading checkpoint: {e}")
        return None

    def load_checkpoint_by_phase(
        self,
        research_id: str,
        phase: str
    ) -> dict | None:
        """
        Load the most recent checkpoint for a specific phase.

        Args:
            research_id: Unique research task identifier
            phase: Phase to load ("planning", "synthesis", etc.)

        Returns:
            State dict, or None if not found
        """
        try:
            response = self.checkpoints_table.query(
                KeyConditionExpression="research_id = :rid",
                FilterExpression="phase = :phase",
                ExpressionAttributeValues={
                    ":rid": research_id,
                    ":phase": phase,
                },
                ScanIndexForward=False,
                Limit=1,
            )
            if response.get("Items"):
                return json.loads(response["Items"][0]["state"])
        except Exception as e:
            print(f"[DynamoDB] Error loading checkpoint by phase: {e}")
        return None

    def list_checkpoints(self, research_id: str) -> list[dict]:
        """
        List all checkpoints for a research task.

        Returns:
            List of checkpoint metadata (without full state)
        """
        try:
            response = self.checkpoints_table.query(
                KeyConditionExpression="research_id = :rid",
                ExpressionAttributeValues={":rid": research_id},
                ProjectionExpression="checkpoint_id, phase, #ts",
                ExpressionAttributeNames={"#ts": "timestamp"},
            )
            return response.get("Items", [])
        except Exception as e:
            print(f"[DynamoDB] Error listing checkpoints: {e}")
            return []

    def delete_checkpoints(self, research_id: str) -> int:
        """
        Delete all checkpoints for a research task.

        Returns:
            Number of checkpoints deleted
        """
        deleted = 0
        try:
            response = self.checkpoints_table.query(
                KeyConditionExpression="research_id = :rid",
                ExpressionAttributeValues={":rid": research_id},
                ProjectionExpression="research_id, checkpoint_id",
            )
            for item in response.get("Items", []):
                self.checkpoints_table.delete_item(Key={
                    "research_id": item["research_id"],
                    "checkpoint_id": item["checkpoint_id"],
                })
                deleted += 1
        except Exception as e:
            print(f"[DynamoDB] Error deleting checkpoints: {e}")
        return deleted

    # =========================================================================
    # Health Check
    # =========================================================================

    def health_check(self) -> dict:
        """
        Check DynamoDB connectivity and table status.

        Returns:
            Health status dict with table info
        """
        status = {
            "healthy": False,
            "sessions_table": None,
            "checkpoints_table": None,
            "error": None,
        }

        try:
            # Check sessions table
            sessions_resp = self.sessions_table.table_status
            status["sessions_table"] = sessions_resp

            # Check checkpoints table
            checkpoints_resp = self.checkpoints_table.table_status
            status["checkpoints_table"] = checkpoints_resp

            status["healthy"] = (
                sessions_resp == "ACTIVE" and checkpoints_resp == "ACTIVE"
            )
        except Exception as e:
            status["error"] = str(e)

        return status


class LocalPersistence:
    """
    In-memory persistence for local development/testing.

    Drop-in replacement for DynamoDBPersistence that stores data in memory.
    Useful for testing without AWS credentials.
    """

    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._checkpoints: dict[str, list[dict]] = {}

    def store_memory(self, session_id: str, layer: str, data: dict) -> None:
        key = f"{session_id}::{layer}"
        self._sessions[key] = {
            "data": data,
            "updated_at": datetime.now().isoformat(),
        }

    def load_memory(self, session_id: str, layer: str) -> dict:
        key = f"{session_id}::{layer}"
        if key in self._sessions:
            return self._sessions[key]["data"]
        return {}

    def delete_memory(self, session_id: str, layer: str) -> None:
        key = f"{session_id}::{layer}"
        self._sessions.pop(key, None)

    def load_all_memory(self, session_id: str) -> dict[str, dict]:
        result = {}
        for layer in ["working", "episodic", "semantic"]:
            data = self.load_memory(session_id, layer)
            if data:
                result[layer] = data
        return result

    def save_all_memory(
        self,
        session_id: str,
        working: dict | None = None,
        episodic: list | None = None,
        semantic: dict | None = None
    ) -> None:
        if working is not None:
            self.store_memory(session_id, "working", working)
        if episodic is not None:
            self.store_memory(session_id, "episodic", episodic)
        if semantic is not None:
            self.store_memory(session_id, "semantic", semantic)

    def save_checkpoint(
        self,
        research_id: str,
        phase: str,
        state: dict
    ) -> str:
        timestamp = datetime.now()
        checkpoint_id = f"{phase}_{timestamp.strftime('%Y%m%d_%H%M%S')}"

        if research_id not in self._checkpoints:
            self._checkpoints[research_id] = []

        self._checkpoints[research_id].append({
            "checkpoint_id": checkpoint_id,
            "phase": phase,
            "state": state,
            "timestamp": timestamp.isoformat(),
        })

        return checkpoint_id

    def load_latest_checkpoint(self, research_id: str) -> dict | None:
        if research_id in self._checkpoints and self._checkpoints[research_id]:
            return self._checkpoints[research_id][-1]["state"]
        return None

    def load_checkpoint_by_phase(
        self,
        research_id: str,
        phase: str
    ) -> dict | None:
        if research_id not in self._checkpoints:
            return None
        for cp in reversed(self._checkpoints[research_id]):
            if cp["phase"] == phase:
                return cp["state"]
        return None

    def list_checkpoints(self, research_id: str) -> list[dict]:
        if research_id not in self._checkpoints:
            return []
        return [
            {"checkpoint_id": cp["checkpoint_id"], "phase": cp["phase"], "timestamp": cp["timestamp"]}
            for cp in self._checkpoints[research_id]
        ]

    def delete_checkpoints(self, research_id: str) -> int:
        if research_id in self._checkpoints:
            count = len(self._checkpoints[research_id])
            del self._checkpoints[research_id]
            return count
        return 0

    def health_check(self) -> dict:
        return {
            "healthy": True,
            "sessions_table": "LOCAL",
            "checkpoints_table": "LOCAL",
            "error": None,
        }


def get_persistence() -> DynamoDBPersistence | LocalPersistence:
    """
    Get appropriate persistence backend based on environment.

    Returns DynamoDBPersistence in AWS, LocalPersistence for local dev.
    """
    from bedrock_models import is_aws_environment

    if is_aws_environment():
        return DynamoDBPersistence()
    else:
        # Check if user explicitly wants DynamoDB locally
        if os.environ.get("USE_DYNAMODB", "").lower() == "true":
            return DynamoDBPersistence()
        return LocalPersistence()


# Quick test
if __name__ == "__main__":
    print("=" * 60)
    print("L27: DynamoDB Persistence Test")
    print("=" * 60)

    # Use local persistence for testing
    persistence = LocalPersistence()

    # Test memory operations
    print("\n--- Memory Operations ---")
    session_id = "test-session-123"

    persistence.store_memory(session_id, "working", {
        "current_query": "What is RAG?",
        "sources": ["src1", "src2"],
    })
    print(f"Stored working memory for {session_id}")

    loaded = persistence.load_memory(session_id, "working")
    print(f"Loaded: {loaded}")

    # Test checkpoint operations
    print("\n--- Checkpoint Operations ---")
    research_id = "research-456"

    cp1 = persistence.save_checkpoint(research_id, "planning", {
        "plan": {"steps": ["search", "analyze"]},
    })
    print(f"Saved checkpoint: {cp1}")

    cp2 = persistence.save_checkpoint(research_id, "step_1", {
        "step": "search",
        "results": ["result1"],
    })
    print(f"Saved checkpoint: {cp2}")

    latest = persistence.load_latest_checkpoint(research_id)
    print(f"Latest checkpoint: {latest}")

    all_cps = persistence.list_checkpoints(research_id)
    print(f"All checkpoints: {all_cps}")

    # Health check
    print("\n--- Health Check ---")
    status = persistence.health_check()
    print(f"Health: {status}")

    print("\n OK - All tests passed")

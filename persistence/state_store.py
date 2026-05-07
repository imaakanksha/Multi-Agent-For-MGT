"""
Durable State Store — Azure Table Storage with SQLite fallback.

Provides persistent, queryable storage for workflow state across
all stages. Every stage transition is recorded as a row, giving
a complete audit trail of the workflow execution.

Production: Uses Azure Table Storage (serverless, pay-per-operation).
Local dev:  Falls back to SQLite (zero-config, file-based).

References:
  - Azure Table Storage: https://learn.microsoft.com/azure/storage/tables/
  - Suitable for Azure Functions Consumption free grant.
"""

from __future__ import annotations
import json
import sqlite3
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from config import config

logger = logging.getLogger(__name__)


class StateStore:
    """
    Unified state store interface with Azure Table Storage backend
    and automatic SQLite fallback for local development.

    Each workflow run is identified by a correlation_id. State
    transitions are appended as rows, never overwritten — this
    provides a complete history of every stage the workflow passed
    through, including retries and failures.

    Table Schema:
        PartitionKey  = correlation_id
        RowKey        = stage_name + timestamp
        status        = pending | running | completed | failed | dead_lettered
        stage         = planner | gatherer | extractor | comparator | writer | finalize
        state_json    = serialized workflow state snapshot
        error_message = error details (if failed)
        created_at    = ISO timestamp
    """

    def __init__(self):
        self._azure_table = None
        self._sqlite_conn = None
        self._backend = "none"
        self._initialize()

    def _initialize(self):
        """Try Azure Table Storage first, fall back to SQLite."""
        # ── Attempt Azure Table Storage ────────────────────────────
        azure_conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        if azure_conn_str:
            try:
                from azure.data.tables import TableServiceClient
                service = TableServiceClient.from_connection_string(azure_conn_str)
                table_name = os.getenv("AZURE_TABLE_NAME", "workflowstate")
                self._azure_table = service.create_table_if_not_exists(table_name)
                self._backend = "azure_table"
                logger.info("State store: Azure Table Storage (%s)", table_name)
                return
            except Exception as e:
                logger.warning("Azure Table Storage init failed: %s", e)

        # ── Fallback: SQLite ───────────────────────────────────────
        db_dir = Path("data")
        db_dir.mkdir(exist_ok=True)
        db_path = db_dir / "workflow_state.db"
        self._sqlite_conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._sqlite_conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_state (
                correlation_id TEXT NOT NULL,
                row_key TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                state_json TEXT,
                error_message TEXT,
                confidence REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                PRIMARY KEY (correlation_id, row_key)
            )
        """)
        self._sqlite_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_corr_id
            ON workflow_state(correlation_id)
        """)
        self._sqlite_conn.commit()
        self._backend = "sqlite"
        logger.info("State store: SQLite (%s)", db_path)

    # ── Public API ─────────────────────────────────────────────────

    def record_transition(
        self,
        correlation_id: str,
        stage: str,
        status: str,
        state_snapshot: dict | None = None,
        error_message: str | None = None,
        confidence: float = 0.0,
    ) -> None:
        """
        Record a stage transition for a workflow run.

        Args:
            correlation_id: Unique workflow run identifier.
            stage: Current stage name (e.g., 'planner', 'gatherer').
            status: Transition status (pending|running|completed|failed|dead_lettered).
            state_snapshot: Optional serialized state at this point.
            error_message: Error details if status is 'failed'.
            confidence: Current confidence score (for branching audit).
        """
        now = datetime.now(timezone.utc).isoformat()
        row_key = f"{stage}_{now}"

        # Serialize state, truncating to prevent oversized rows
        state_json = None
        if state_snapshot:
            try:
                state_json = json.dumps(state_snapshot, default=str)
                if len(state_json) > 60000:  # Azure Table 64KB property limit
                    state_json = json.dumps({"_truncated": True, "stage": stage})
            except Exception:
                state_json = json.dumps({"_serialization_error": True})

        if self._backend == "azure_table":
            self._write_azure(correlation_id, row_key, stage, status,
                              state_json, error_message, confidence, now)
        elif self._backend == "sqlite":
            self._write_sqlite(correlation_id, row_key, stage, status,
                               state_json, error_message, confidence, now)

        logger.debug("State transition: [%s] %s → %s (confidence=%.2f)",
                     correlation_id[:8], stage, status, confidence)

    def get_workflow_history(self, correlation_id: str) -> list[dict]:
        """Retrieve all state transitions for a workflow run."""
        if self._backend == "azure_table":
            return self._query_azure(correlation_id)
        elif self._backend == "sqlite":
            return self._query_sqlite(correlation_id)
        return []

    def get_workflow_status(self, correlation_id: str) -> dict | None:
        """Get the latest status of a workflow run."""
        history = self.get_workflow_history(correlation_id)
        if not history:
            return None
        latest = history[-1]
        return {
            "correlation_id": correlation_id,
            "current_stage": latest["stage"],
            "status": latest["status"],
            "total_transitions": len(history),
            "last_updated": latest["created_at"],
            "confidence": latest.get("confidence", 0.0),
        }

    def list_workflows(self, status_filter: str | None = None, limit: int = 50) -> list[dict]:
        """List recent workflows, optionally filtered by status."""
        if self._backend == "sqlite":
            return self._list_sqlite(status_filter, limit)
        elif self._backend == "azure_table":
            return self._list_azure(status_filter, limit)
        return []

    # ── Azure Table Storage Backend ────────────────────────────────

    def _write_azure(self, corr_id, row_key, stage, status,
                     state_json, error_msg, confidence, timestamp):
        try:
            entity = {
                "PartitionKey": corr_id,
                "RowKey": row_key,
                "stage": stage,
                "status": status,
                "state_json": state_json or "",
                "error_message": error_msg or "",
                "confidence": confidence,
                "created_at": timestamp,
            }
            self._azure_table.upsert_entity(entity)
        except Exception as e:
            logger.error("Azure Table write failed: %s", e)

    def _query_azure(self, corr_id):
        try:
            query = f"PartitionKey eq '{corr_id}'"
            entities = self._azure_table.query_entities(query)
            return [
                {
                    "stage": e["stage"],
                    "status": e["status"],
                    "error_message": e.get("error_message", ""),
                    "confidence": e.get("confidence", 0.0),
                    "created_at": e["created_at"],
                }
                for e in sorted(entities, key=lambda x: x["created_at"])
            ]
        except Exception as e:
            logger.error("Azure Table query failed: %s", e)
            return []

    def _list_azure(self, status_filter, limit):
        try:
            query = f"status eq '{status_filter}'" if status_filter else None
            entities = self._azure_table.query_entities(query) if query else self._azure_table.list_entities()
            results = []
            seen = set()
            for e in entities:
                cid = e["PartitionKey"]
                if cid not in seen:
                    seen.add(cid)
                    results.append({
                        "correlation_id": cid,
                        "stage": e["stage"],
                        "status": e["status"],
                        "created_at": e["created_at"],
                    })
                if len(results) >= limit:
                    break
            return results
        except Exception as e:
            logger.error("Azure Table list failed: %s", e)
            return []

    # ── SQLite Backend ─────────────────────────────────────────────

    def _write_sqlite(self, corr_id, row_key, stage, status,
                      state_json, error_msg, confidence, timestamp):
        try:
            self._sqlite_conn.execute(
                """INSERT OR REPLACE INTO workflow_state
                   (correlation_id, row_key, stage, status, state_json,
                    error_message, confidence, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (corr_id, row_key, stage, status, state_json,
                 error_msg, confidence, timestamp),
            )
            self._sqlite_conn.commit()
        except Exception as e:
            logger.error("SQLite write failed: %s", e)

    def _query_sqlite(self, corr_id):
        try:
            cursor = self._sqlite_conn.execute(
                """SELECT stage, status, error_message, confidence, created_at
                   FROM workflow_state
                   WHERE correlation_id = ?
                   ORDER BY created_at ASC""",
                (corr_id,),
            )
            return [
                {"stage": r[0], "status": r[1], "error_message": r[2],
                 "confidence": r[3], "created_at": r[4]}
                for r in cursor.fetchall()
            ]
        except Exception as e:
            logger.error("SQLite query failed: %s", e)
            return []

    def _list_sqlite(self, status_filter, limit):
        try:
            if status_filter:
                cursor = self._sqlite_conn.execute(
                    """SELECT DISTINCT correlation_id, stage, status, created_at
                       FROM workflow_state
                       WHERE status = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (status_filter, limit),
                )
            else:
                cursor = self._sqlite_conn.execute(
                    """SELECT correlation_id, stage, status, created_at
                       FROM workflow_state
                       GROUP BY correlation_id
                       ORDER BY MAX(created_at) DESC LIMIT ?""",
                    (limit,),
                )
            return [
                {"correlation_id": r[0], "stage": r[1],
                 "status": r[2], "created_at": r[3]}
                for r in cursor.fetchall()
            ]
        except Exception as e:
            logger.error("SQLite list failed: %s", e)
            return []


# ── Singleton ──────────────────────────────────────────────────────
_store_instance: StateStore | None = None


def get_state_store() -> StateStore:
    """Get or create the singleton StateStore instance."""
    global _store_instance
    if _store_instance is None:
        _store_instance = StateStore()
    return _store_instance

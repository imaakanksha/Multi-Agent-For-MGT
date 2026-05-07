"""
Dead-Letter Queue — captures workflows that exhaust all retries.

When a workflow fails beyond recovery (max retries exceeded at any
stage), it is moved to the dead-letter store instead of being silently
dropped. This enables:
  - Operational alerting on persistent failures
  - Manual inspection and replay of failed workflows
  - Root-cause analysis from preserved state snapshots

Production: Uses Azure Queue Storage (or Service Bus dead-letter).
Local dev:  Falls back to a SQLite table + JSON file.
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class DeadLetterQueue:
    """
    Dead-letter queue for workflows that fail terminally.

    Each dead-letter entry contains:
      - correlation_id: The failed workflow's tracking ID
      - failed_stage: Which stage exhausted retries
      - retry_count: How many retries were attempted
      - error_log: All accumulated errors
      - state_snapshot: The state at time of failure
      - created_at: When the failure was recorded
    """

    def __init__(self):
        self._backend = "none"
        self._azure_queue = None
        self._sqlite_conn = None
        self._initialize()

    def _initialize(self):
        """Try Azure Queue Storage first, fall back to SQLite."""
        azure_conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        if azure_conn_str:
            try:
                from azure.storage.queue import QueueServiceClient
                service = QueueServiceClient.from_connection_string(azure_conn_str)
                queue_name = os.getenv("AZURE_DEAD_LETTER_QUEUE", "research-dead-letter")
                self._azure_queue = service.create_queue(queue_name)
                self._backend = "azure_queue"
                logger.info("Dead-letter queue: Azure Queue Storage (%s)", queue_name)
                return
            except Exception as e:
                # Queue might already exist
                try:
                    from azure.storage.queue import QueueServiceClient
                    service = QueueServiceClient.from_connection_string(azure_conn_str)
                    queue_name = os.getenv("AZURE_DEAD_LETTER_QUEUE", "research-dead-letter")
                    self._azure_queue = service.get_queue_client(queue_name)
                    self._backend = "azure_queue"
                    logger.info("Dead-letter queue: Azure Queue Storage (%s)", queue_name)
                    return
                except Exception as e2:
                    logger.warning("Azure Queue init failed: %s", e2)

        # ── Fallback: SQLite ───────────────────────────────────────
        import sqlite3
        db_dir = Path("data")
        db_dir.mkdir(exist_ok=True)
        db_path = db_dir / "dead_letter.db"
        self._sqlite_conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._sqlite_conn.execute("""
            CREATE TABLE IF NOT EXISTS dead_letter (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                correlation_id TEXT NOT NULL,
                failed_stage TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                error_log TEXT,
                state_snapshot TEXT,
                created_at TEXT NOT NULL
            )
        """)
        self._sqlite_conn.commit()
        self._backend = "sqlite"
        logger.info("Dead-letter queue: SQLite (%s)", db_path)

    def enqueue(
        self,
        correlation_id: str,
        failed_stage: str,
        retry_count: int,
        error_log: list[str],
        state_snapshot: dict | None = None,
    ) -> None:
        """
        Send a failed workflow to the dead-letter queue.

        Args:
            correlation_id: The workflow's tracking ID.
            failed_stage: Stage that failed terminally.
            retry_count: Number of retries attempted.
            error_log: All errors accumulated during the run.
            state_snapshot: State at time of terminal failure.
        """
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "correlation_id": correlation_id,
            "failed_stage": failed_stage,
            "retry_count": retry_count,
            "error_log": error_log,
            "created_at": now,
        }

        logger.warning(
            "DEAD-LETTER: Workflow %s failed at stage '%s' after %d retries",
            correlation_id[:12], failed_stage, retry_count,
        )

        if self._backend == "azure_queue":
            try:
                msg = json.dumps(entry, default=str)
                self._azure_queue.send_message(msg)
            except Exception as e:
                logger.error("Azure Queue send failed: %s", e)
                self._write_to_file_fallback(entry)

        elif self._backend == "sqlite":
            try:
                self._sqlite_conn.execute(
                    """INSERT INTO dead_letter
                       (correlation_id, failed_stage, retry_count,
                        error_log, state_snapshot, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        correlation_id,
                        failed_stage,
                        retry_count,
                        json.dumps(error_log),
                        json.dumps(state_snapshot, default=str) if state_snapshot else None,
                        now,
                    ),
                )
                self._sqlite_conn.commit()
            except Exception as e:
                logger.error("SQLite dead-letter write failed: %s", e)
                self._write_to_file_fallback(entry)

    def list_entries(self, limit: int = 50) -> list[dict]:
        """List recent dead-letter entries for inspection."""
        if self._backend == "sqlite" and self._sqlite_conn:
            try:
                cursor = self._sqlite_conn.execute(
                    """SELECT id, correlation_id, failed_stage, retry_count,
                              error_log, state_snapshot, created_at
                       FROM dead_letter ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                )
                return [
                    {
                        "id": r[0],
                        "correlation_id": r[1],
                        "failed_stage": r[2],
                        "retry_count": r[3],
                        "error_log": json.loads(r[4]) if r[4] else [],
                        "state_snapshot": json.loads(r[5]) if r[5] else None,
                        "created_at": r[6],
                    }
                    for r in cursor.fetchall()
                ]
            except Exception as e:
                logger.error("Dead-letter list failed: %s", e)
        return []

    def get_entry(self, correlation_id: str) -> dict | None:
        """Get a specific dead-letter entry by correlation_id."""
        if self._backend == "sqlite" and self._sqlite_conn:
            try:
                cursor = self._sqlite_conn.execute(
                    """SELECT id, correlation_id, failed_stage, retry_count,
                              error_log, state_snapshot, created_at
                       FROM dead_letter WHERE correlation_id = ?
                       ORDER BY created_at DESC LIMIT 1""",
                    (correlation_id,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "correlation_id": row[1],
                        "failed_stage": row[2],
                        "retry_count": row[3],
                        "error_log": json.loads(row[4]) if row[4] else [],
                        "state_snapshot": json.loads(row[5]) if row[5] else None,
                        "created_at": row[6],
                    }
            except Exception as e:
                logger.error("Dead-letter get_entry failed: %s", e)
        return None

    def replay(self, correlation_id: str, modified_prompt: str | None = None) -> dict:
        """
        Replay a dead-lettered workflow.

        Retrieves the original prompt from the dead-letter entry and
        re-submits it to the pipeline with a new correlation_id.

        Args:
            correlation_id: The dead-lettered workflow's correlation ID.
            modified_prompt: Optional modified prompt. If None, uses
                the original prompt from the state snapshot.

        Returns:
            Dict with new_correlation_id and replay status.
        """
        entry = self.get_entry(correlation_id)
        if not entry:
            return {
                "status": "error",
                "message": f"Dead-letter entry not found: {correlation_id}",
            }

        # Extract original prompt from state snapshot
        snapshot = entry.get("state_snapshot") or {}
        original_prompt = modified_prompt or snapshot.get("research_prompt", "")

        if not original_prompt:
            return {
                "status": "error",
                "message": "No prompt available in dead-letter entry (state_snapshot missing)",
            }

        # Create new workflow run
        from orchestration.correlation import generate_correlation_id
        from orchestration.state import create_initial_state

        new_corr_id = generate_correlation_id()

        logger.info(
            "REPLAY: Dead-lettered workflow %s → new run %s",
            correlation_id[:12], new_corr_id[:12],
        )

        # Mark the old entry as replayed
        self._mark_replayed(correlation_id, new_corr_id)

        return {
            "status": "replayed",
            "original_correlation_id": correlation_id,
            "new_correlation_id": new_corr_id,
            "prompt": original_prompt,
            "failed_stage": entry.get("failed_stage"),
            "original_retry_count": entry.get("retry_count", 0),
        }

    def _mark_replayed(self, old_corr_id: str, new_corr_id: str) -> None:
        """Mark a dead-letter entry as replayed with the new correlation_id."""
        if self._backend == "sqlite" and self._sqlite_conn:
            try:
                # Add a note to the error_log indicating replay
                self._sqlite_conn.execute(
                    """UPDATE dead_letter
                       SET error_log = json_insert(error_log, '$[#]', ?)
                       WHERE correlation_id = ?""",
                    (f"REPLAYED → {new_corr_id}", old_corr_id),
                )
                self._sqlite_conn.commit()
            except Exception as e:
                logger.warning("Failed to mark as replayed: %s", e)

    def _write_to_file_fallback(self, entry: dict):
        """Last-resort: append to a JSON-lines file if all stores fail."""
        try:
            fallback_path = Path("data") / "dead_letter_fallback.jsonl"
            fallback_path.parent.mkdir(exist_ok=True)
            with open(fallback_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
            logger.info("Dead-letter written to fallback file: %s", fallback_path)
        except Exception as e:
            logger.critical("ALL dead-letter backends failed: %s", e)


# ── Singleton ──────────────────────────────────────────────────────
_dlq_instance: DeadLetterQueue | None = None


def get_dead_letter_queue() -> DeadLetterQueue:
    """Get or create the singleton DeadLetterQueue instance."""
    global _dlq_instance
    if _dlq_instance is None:
        _dlq_instance = DeadLetterQueue()
    return _dlq_instance

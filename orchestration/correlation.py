"""
Correlation ID & Status Transition Manager.

Provides cross-step state management by:
  1. Generating unique correlation IDs for each workflow run
  2. Tracking stage transitions with timestamps
  3. Recording confidence scores at each decision point
  4. Integrating with the persistent StateStore

This is the glue between the LangGraph state (in-memory) and
the durable persistence layer (Azure Table / SQLite).
"""

from __future__ import annotations
import uuid
import logging
from datetime import datetime, timezone
from enum import Enum

from persistence.state_store import get_state_store
from persistence.dead_letter import get_dead_letter_queue

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """Finite state machine for workflow lifecycle."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"

    # Valid transitions:
    #   PENDING → RUNNING
    #   RUNNING → COMPLETED | FAILED
    #   FAILED  → RUNNING (retry) | DEAD_LETTERED (terminal)


class StageStatus(str, Enum):
    """Status of an individual stage execution."""
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


def generate_correlation_id() -> str:
    """
    Generate a unique correlation ID for a workflow run.

    Format: res-<uuid4-short>-<timestamp>
    Example: res-a1b2c3d4-20260507T120000Z

    The timestamp suffix aids visual debugging and log correlation.
    """
    short_uuid = uuid.uuid4().hex[:8]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"res-{short_uuid}-{ts}"


class WorkflowTracker:
    """
    Tracks a single workflow run across all stages.

    Created at the start of each workflow, this object:
    - Holds the correlation_id
    - Records every stage transition to the StateStore
    - Provides helper methods for the graph nodes to report progress
    - Handles dead-lettering on terminal failure

    Usage in graph nodes:
        tracker = WorkflowTracker.from_state(state)
        tracker.stage_started("planner")
        # ... do work ...
        tracker.stage_completed("planner", confidence=0.85)
    """

    def __init__(self, correlation_id: str):
        self.correlation_id = correlation_id
        self._store = get_state_store()
        self._dlq = get_dead_letter_queue()
        self._transitions: list[dict] = []

    @classmethod
    def from_state(cls, state: dict) -> WorkflowTracker:
        """Create or recover a tracker from the workflow state."""
        corr_id = state.get("correlation_id", generate_correlation_id())
        return cls(corr_id)

    def workflow_started(self, prompt: str) -> None:
        """Record workflow initiation."""
        self._record("workflow", StageStatus.STARTED, metadata={"prompt": prompt[:200]})

    def stage_started(self, stage: str) -> None:
        """Record the start of a pipeline stage."""
        self._record(stage, StageStatus.STARTED)

    def stage_completed(self, stage: str, confidence: float = 0.0) -> None:
        """Record successful completion of a stage."""
        self._record(stage, StageStatus.COMPLETED, confidence=confidence)

    def stage_failed(self, stage: str, error: str, retry_count: int = 0) -> None:
        """Record a stage failure (may be retried)."""
        self._record(stage, StageStatus.FAILED, error_message=error)
        logger.warning(
            "[%s] Stage '%s' failed (retry %d): %s",
            self.correlation_id[:12], stage, retry_count, error[:100],
        )

    def stage_retrying(self, stage: str, attempt: int) -> None:
        """Record a retry attempt for a stage."""
        self._record(stage, StageStatus.RETRYING,
                     metadata={"attempt": attempt})

    def workflow_completed(self, confidence: float = 0.0) -> None:
        """Record successful workflow completion."""
        self._record("workflow", StageStatus.COMPLETED, confidence=confidence)
        logger.info(
            "[%s] Workflow completed (confidence=%.2f)",
            self.correlation_id[:12], confidence,
        )

    def workflow_failed(self, stage: str, error_log: list[str],
                        retry_count: int, state_snapshot: dict | None = None) -> None:
        """Record terminal workflow failure and dead-letter it."""
        self._record("workflow", StageStatus.FAILED,
                     error_message="; ".join(error_log[-3:]))

        # Dead-letter the failed workflow
        self._dlq.enqueue(
            correlation_id=self.correlation_id,
            failed_stage=stage,
            retry_count=retry_count,
            error_log=error_log,
            state_snapshot=state_snapshot,
        )

        # Update state store with dead-letter status
        self._store.record_transition(
            correlation_id=self.correlation_id,
            stage=stage,
            status=WorkflowStatus.DEAD_LETTERED,
            error_message=f"Dead-lettered after {retry_count} retries",
        )

    def get_history(self) -> list[dict]:
        """Get the complete transition history for this workflow."""
        return self._store.get_workflow_history(self.correlation_id)

    def _record(self, stage: str, status: StageStatus,
                confidence: float = 0.0, error_message: str | None = None,
                metadata: dict | None = None) -> None:
        """Internal: record a transition to the persistent store."""
        transition = {
            "stage": stage,
            "status": status.value,
            "confidence": confidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if error_message:
            transition["error"] = error_message
        if metadata:
            transition.update(metadata)
        self._transitions.append(transition)

        self._store.record_transition(
            correlation_id=self.correlation_id,
            stage=stage,
            status=status.value,
            error_message=error_message,
            confidence=confidence,
        )

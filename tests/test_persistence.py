"""Tests for the persistence layer (state store + dead-letter queue)."""
import os
import pytest
from persistence.state_store import StateStore
from persistence.dead_letter import DeadLetterQueue
from orchestration.correlation import generate_correlation_id, WorkflowTracker


def test_generate_correlation_id_format():
    """Verify correlation_id format: res-<hex8>-<timestamp>."""
    cid = generate_correlation_id()
    assert cid.startswith("res-")
    parts = cid.split("-")
    assert len(parts) >= 3


def test_generate_unique_ids():
    """Verify uniqueness across multiple generations."""
    ids = {generate_correlation_id() for _ in range(20)}
    assert len(ids) == 20


def test_state_store_sqlite_write_and_read():
    """Test SQLite backend write and read cycle."""
    store = StateStore()
    cid = generate_correlation_id()

    store.record_transition(cid, "planner", "started")
    store.record_transition(cid, "planner", "completed", confidence=0.85)

    history = store.get_workflow_history(cid)
    assert len(history) == 2
    assert history[0]["stage"] == "planner"
    assert history[0]["status"] == "started"
    assert history[1]["status"] == "completed"
    assert history[1]["confidence"] == 0.85


def test_state_store_get_status():
    """Test getting latest workflow status."""
    store = StateStore()
    cid = generate_correlation_id()

    store.record_transition(cid, "planner", "started")
    store.record_transition(cid, "gatherer", "completed", confidence=0.7)

    status = store.get_workflow_status(cid)
    assert status is not None
    assert status["current_stage"] == "gatherer"
    assert status["status"] == "completed"
    assert status["total_transitions"] == 2


def test_state_store_missing_workflow():
    """Test querying non-existent workflow returns None."""
    store = StateStore()
    status = store.get_workflow_status("non-existent-id")
    assert status is None


def test_dead_letter_queue_sqlite():
    """Test dead-letter queue write and list."""
    dlq = DeadLetterQueue()
    cid = generate_correlation_id()

    dlq.enqueue(
        correlation_id=cid,
        failed_stage="extractor",
        retry_count=3,
        error_log=["Error 1", "Error 2"],
    )

    entries = dlq.list_entries(limit=10)
    assert len(entries) >= 1
    match = [e for e in entries if e["correlation_id"] == cid]
    assert len(match) == 1
    assert match[0]["failed_stage"] == "extractor"
    assert match[0]["retry_count"] == 3


def test_workflow_tracker_records_transitions():
    """Test that WorkflowTracker records to state store."""
    cid = generate_correlation_id()
    tracker = WorkflowTracker(cid)

    tracker.workflow_started("test prompt")
    tracker.stage_started("planner")
    tracker.stage_completed("planner", confidence=0.9)

    history = tracker.get_history()
    assert len(history) >= 3
    stages = [h["stage"] for h in history]
    assert "workflow" in stages
    assert "planner" in stages

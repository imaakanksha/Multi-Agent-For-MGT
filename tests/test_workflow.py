"""Tests for the complete workflow state management."""
from orchestration.state import create_initial_state


def test_create_initial_state():
    state = create_initial_state("Test prompt")
    assert state["research_prompt"] == "Test prompt"
    assert state["workflow_status"] == "running"
    assert state["current_stage"] == "planning"
    assert state["messages"] == []
    assert state["extracted_facts"] == []
    assert state["retry_count"] == 0
    assert state["revision_count"] == 0


def test_initial_state_empty_collections():
    state = create_initial_state("Another test")
    assert state["raw_sources"] == []
    assert state["comparisons"] == []
    assert state["open_questions"] == []
    assert state["error_log"] == []
    assert state["final_report"] is None
    assert state["outline"] is None


def test_correlation_id_auto_generated():
    """Verify a correlation_id is auto-generated if not provided."""
    state = create_initial_state("Test prompt")
    assert "correlation_id" in state
    assert state["correlation_id"].startswith("res-")
    assert len(state["correlation_id"]) > 10


def test_correlation_id_custom():
    """Verify a custom correlation_id is preserved."""
    state = create_initial_state("Test prompt", correlation_id="custom-id-123")
    assert state["correlation_id"] == "custom-id-123"


def test_cross_step_state_fields():
    """Verify new cross-step state management fields exist."""
    state = create_initial_state("Test prompt")
    assert state["status_transitions"] == []
    assert state["retry_backoff_seconds"] == 1.0
    assert isinstance(state["correlation_id"], str)


def test_unique_correlation_ids():
    """Verify each call generates a unique correlation_id."""
    ids = {create_initial_state("test")["correlation_id"] for _ in range(10)}
    assert len(ids) == 10  # All unique

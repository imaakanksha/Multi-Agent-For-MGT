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

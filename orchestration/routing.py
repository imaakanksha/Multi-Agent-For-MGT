"""
Conditional routing logic for the LangGraph workflow.

These functions are used as conditional edges in the StateGraph to
determine which agent should execute next, based on the current state.
This implements the "reflection loop" pattern where the Writer's output
can be routed back for revision if quality thresholds aren't met.
"""

from __future__ import annotations
from config import config


def route_after_planning(state: dict) -> str:
    """
    Route after the Planner Agent completes.

    Decision logic:
      - If planning failed (no outline or queries): retry or abort
      - If planning succeeded: proceed to gathering
    """
    if state.get("outline") is None or not state.get("search_queries"):
        retry_count = state.get("retry_count", 0)
        if retry_count < config.workflow.max_retries:
            return "planner"  # Retry planning
        return "error_handler"  # Give up
    return "gatherer"


def route_after_gathering(state: dict) -> str:
    """
    Route after the Gatherer Agent completes.

    Decision logic:
      - If no sources retrieved at all: retry or abort
      - If fewer than 2 sources: log warning, proceed anyway
      - If sufficient sources: proceed to extraction
    """
    raw_sources = state.get("raw_sources", [])
    successful = [s for s in raw_sources if s.retrieval_status == "success"]

    if not successful:
        retry_count = state.get("retry_count", 0)
        if retry_count < config.workflow.max_retries:
            return "gatherer"
        return "error_handler"

    return "extractor"


def route_after_extraction(state: dict) -> str:
    """
    Route after the Extractor Agent completes.

    Decision logic:
      - If no facts extracted: retry or abort
      - If facts extracted: proceed to comparison
    """
    facts = state.get("extracted_facts", [])
    if not facts:
        retry_count = state.get("retry_count", 0)
        if retry_count < config.workflow.max_retries:
            return "extractor"
        return "error_handler"
    return "comparator"


def route_after_comparison(state: dict) -> str:
    """
    Route after the Comparator Agent completes.

    Always proceeds to the Writer. Comparisons are best-effort;
    even if no cross-source comparisons could be made, the Writer
    should still produce a report noting this limitation.
    """
    return "writer"


def route_after_writing(state: dict) -> str:
    """
    Route after the Writer Agent completes — implements the reflection loop.

    Decision logic:
      - If report confidence < threshold AND revisions remain: loop back
        to comparator for re-analysis, then to writer for revision
      - If report meets quality bar OR max revisions reached: finish
    """
    report = state.get("final_report")
    revision_count = state.get("revision_count", 0)

    if report is None:
        return "error_handler"

    # Reflection loop: check if report quality meets threshold
    if (report.metadata.overall_confidence < config.workflow.confidence_threshold
            and revision_count < config.workflow.max_revision_loops):
        return "comparator"  # Re-analyze, then re-write

    return "finalize"


def handle_error(state: dict) -> str:
    """
    Error handler routing. Logs the error and determines whether
    to abort or attempt recovery.
    """
    return "finalize"  # Graceful degradation: produce partial report

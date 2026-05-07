"""
Conditional routing logic for the LangGraph workflow.

These functions are used as conditional edges in the StateGraph to
determine which agent should execute next, based on the current state.
This implements:
  - Confidence-aware branching (reflection loop)
  - Exponential backoff retries with jitter
  - Dead-letter routing on terminal failure

Error Strategy:
  retry_count < MAX_RETRIES → retry with exponential backoff
  retry_count >= MAX_RETRIES → dead-letter + finalize
"""

from __future__ import annotations
import time
import random
import logging
from datetime import datetime, timezone
from config import config

logger = logging.getLogger(__name__)


def _record_transition(state: dict, stage: str, status: str,
                       confidence: float = 0.0) -> dict:
    """Build a status transition record for the audit trail."""
    return {
        "stage": stage,
        "status": status,
        "confidence": confidence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": state.get("correlation_id", "unknown"),
    }


def _should_retry(state: dict) -> bool:
    """Check if retry budget remains."""
    return state.get("retry_count", 0) < config.workflow.max_retries


def _apply_backoff(state: dict) -> None:
    """
    Apply exponential backoff with jitter before retry.

    Formula: delay = min(base * 2^attempt + jitter, max_delay)
    This prevents thundering-herd problems when multiple
    workflow instances retry simultaneously.
    """
    attempt = state.get("retry_count", 0)
    base_delay = state.get("retry_backoff_seconds", 1.0)
    delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), 30.0)
    logger.info(
        "[%s] Backoff: %.1fs before retry #%d",
        state.get("correlation_id", "?")[:12], delay, attempt + 1,
    )
    time.sleep(delay)


def route_after_planning(state: dict) -> str:
    """
    Route after the Planner Agent completes.

    Decision logic:
      - If planning produced valid outline + queries → gatherer
      - If planning failed and retries remain → planner (with backoff)
      - If retries exhausted → error_handler (dead-letter)
    """
    if state.get("outline") is None or not state.get("search_queries"):
        if _should_retry(state):
            _apply_backoff(state)
            logger.info("[%s] Planner retry #%d",
                        state.get("correlation_id", "?")[:12],
                        state.get("retry_count", 0) + 1)
            return "planner"
        logger.error("[%s] Planner exhausted retries → dead-letter",
                     state.get("correlation_id", "?")[:12])
        return "error_handler"
    return "gatherer"


def route_after_gathering(state: dict) -> str:
    """
    Route after the Gatherer Agent completes.

    Decision logic:
      - If ≥1 source retrieved successfully → extractor
      - If 0 sources and retries remain → gatherer (with backoff)
      - If retries exhausted → error_handler (dead-letter)
    """
    raw_sources = state.get("raw_sources", [])
    successful = [s for s in raw_sources if s.retrieval_status == "success"]

    if not successful:
        if _should_retry(state):
            _apply_backoff(state)
            return "gatherer"
        return "error_handler"

    # Log a warning if fewer than 2 distinct source types
    source_types = set(s.source_type.value for s in successful)
    if len(source_types) < 2:
        logger.warning(
            "[%s] Only %d source type(s) retrieved: %s — proceeding anyway",
            state.get("correlation_id", "?")[:12],
            len(source_types), source_types,
        )

    return "extractor"


def route_after_extraction(state: dict) -> str:
    """
    Route after the Extractor Agent completes.

    Decision logic:
      - If facts extracted → comparator
      - If no facts and retries remain → extractor (with backoff)
      - If retries exhausted → error_handler (dead-letter)
    """
    facts = state.get("extracted_facts", [])
    if not facts:
        if _should_retry(state):
            _apply_backoff(state)
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
    Route after the Writer Agent completes.

    CONFIDENCE-AWARE BRANCHING:
      - If report is None → error_handler
      - If confidence < threshold AND revisions remain →
        loop back to comparator for re-analysis (reflection loop)
      - If confidence ≥ threshold OR max revisions reached → finalize
    """
    report = state.get("final_report")
    revision_count = state.get("revision_count", 0)
    corr_id = state.get("correlation_id", "?")[:12]

    if report is None:
        logger.error("[%s] Writer produced no report → error_handler", corr_id)
        return "error_handler"

    confidence = report.metadata.overall_confidence
    threshold = config.workflow.confidence_threshold

    # ── Confidence-aware branching ─────────────────────────────────
    if confidence < threshold and revision_count < config.workflow.max_revision_loops:
        logger.info(
            "[%s] Confidence %.2f < %.2f threshold — revision #%d (reflection loop)",
            corr_id, confidence, threshold, revision_count + 1,
        )
        return "comparator"  # Re-analyze, then re-write

    if confidence < threshold:
        logger.warning(
            "[%s] Confidence %.2f below threshold but max revisions reached — finalizing anyway",
            corr_id, confidence,
        )

    return "finalize"


def handle_error(state: dict) -> str:
    """
    Error handler routing. Logs the error and determines whether
    to abort or attempt recovery.
    """
    return "finalize"  # Graceful degradation: produce partial report

"""
LangGraph StateGraph definition — the core orchestration layer.

This module assembles the complete multi-agent workflow as a directed
graph with conditional edges, parallel execution paths, and a
reflection loop for quality assurance.

Architecture Pattern: Supervisor with Reflection
  - Linear pipeline: Planner → Gatherer → Extractor → Comparator → Writer
  - Reflection loop: Writer ⟷ Comparator (if confidence < threshold)
  - Error recovery: Any failed stage can retry or gracefully degrade
  - Dead-letter: Terminal failures are captured for inspection/replay

References:
  - LangGraph Docs: https://langchain-ai.github.io/langgraph/
  - Multi-agent patterns: https://langchain-ai.github.io/langgraph/concepts/multi_agent/
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from orchestration.state import ResearchState
from orchestration.routing import (
    route_after_planning,
    route_after_gathering,
    route_after_extraction,
    route_after_comparison,
    route_after_writing,
)
from orchestration.correlation import WorkflowTracker
from agents.planner import planner_node
from agents.gatherer import gatherer_node
from agents.extractor import extractor_node
from agents.comparator import comparator_node
from agents.writer import writer_node

logger = logging.getLogger(__name__)


# ── Persistence-Aware Node Wrappers ──────────────────────────────────
# These wrappers add state tracking around each agent node, recording
# every transition to the durable StateStore for audit and recovery.

def _wrap_with_tracking(node_fn, stage_name: str):
    """
    Wrap a graph node function to add persistence tracking.

    Before the node runs: records 'started' transition
    After success: records 'completed' with confidence
    On failure: records 'failed' with error details
    """
    def tracked_node(state: dict) -> dict:
        tracker = WorkflowTracker.from_state(state)
        tracker.stage_started(stage_name)

        transition = {
            "stage": stage_name,
            "status": "started",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": state.get("correlation_id", "unknown"),
        }

        try:
            result = node_fn(state)

            # Record completion
            confidence = 0.0
            if stage_name == "writer" and result.get("final_report"):
                confidence = result["final_report"].metadata.overall_confidence
            tracker.stage_completed(stage_name, confidence=confidence)

            # Add transition to result
            completed_transition = {
                "stage": stage_name,
                "status": "completed",
                "confidence": confidence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "correlation_id": state.get("correlation_id", "unknown"),
            }
            result.setdefault("status_transitions", [])
            result["status_transitions"] = [transition, completed_transition]

            return result

        except Exception as e:
            logger.error("[%s] Node '%s' crashed: %s",
                         state.get("correlation_id", "?")[:12], stage_name, e)
            tracker.stage_failed(stage_name, str(e),
                                 retry_count=state.get("retry_count", 0))

            failed_transition = {
                "stage": stage_name,
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "correlation_id": state.get("correlation_id", "unknown"),
            }
            return {
                "current_stage": stage_name,
                "error_log": [f"{stage_name} error: {str(e)}"],
                "retry_count": state.get("retry_count", 0) + 1,
                "status_transitions": [transition, failed_transition],
            }

    tracked_node.__name__ = f"tracked_{stage_name}"
    return tracked_node


def _error_handler_node(state: dict) -> dict:
    """
    Error handler node — dead-letters the workflow and produces
    a partial report or logs the terminal failure.

    This node is triggered when a stage exhausts all retry attempts.
    It persists the failure to the dead-letter queue so operators
    can inspect and manually replay the workflow.
    """
    corr_id = state.get("correlation_id", "unknown")
    error_log = state.get("error_log", [])
    failed_stage = state.get("current_stage", "unknown")
    retry_count = state.get("retry_count", 0)

    logger.error(
        "[%s] TERMINAL FAILURE at stage '%s' after %d retries. Errors: %s",
        corr_id[:12], failed_stage, retry_count, error_log[-3:],
    )

    # Record to persistent tracker + dead-letter queue
    tracker = WorkflowTracker.from_state(state)
    tracker.workflow_failed(
        stage=failed_stage,
        error_log=error_log,
        retry_count=retry_count,
    )

    transition = {
        "stage": "error_handler",
        "status": "dead_lettered",
        "error": "; ".join(error_log[-3:]),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": corr_id,
    }

    return {
        "workflow_status": "failed",
        "current_stage": "error_handler",
        "error_log": [f"Dead-lettered: workflow failed at '{failed_stage}' after {retry_count} retries"],
        "status_transitions": [transition],
    }


def _finalize_node(state: dict) -> dict:
    """
    Finalization node — marks the workflow as completed, records
    the terminal state, and persists the final outcome.
    """
    corr_id = state.get("correlation_id", "unknown")
    report = state.get("final_report")
    status = "completed" if report else "partial"
    confidence = report.metadata.overall_confidence if report else 0.0

    tracker = WorkflowTracker.from_state(state)
    if status == "completed":
        tracker.workflow_completed(confidence=confidence)
    else:
        tracker.stage_completed("finalize", confidence=0.0)

    logger.info("[%s] Workflow finalized: status=%s, confidence=%.2f",
                corr_id[:12], status, confidence)

    transition = {
        "stage": "finalize",
        "status": status,
        "confidence": confidence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": corr_id,
    }

    return {
        "workflow_status": status,
        "current_stage": "finalized",
        "status_transitions": [transition],
    }


def build_research_graph(use_memory_checkpoint: bool = True) -> StateGraph:
    """
    Build and compile the complete research workflow graph.

    Args:
        use_memory_checkpoint: If True, uses in-memory checkpointing.
            For production, replace with a persistent checkpointer
            (e.g., CosmosDBSaver or PostgresSaver).

    Returns:
        A compiled LangGraph StateGraph ready for invocation.

    Graph Structure:
    ┌──────────┐
    │  START    │
    └────┬─────┘
         │
         ▼
    ┌──────────┐     retry (exponential backoff)
    │ Planner  │◄──────────┐
    └────┬─────┘           │
         │ success         │ fail
         ▼                 │
    ┌──────────┐     retry │
    │ Gatherer │◄─────┐    │
    └────┬─────┘      │    │
         │ success    │ fail
         ▼            │
    ┌───────────┐     │
    │ Extractor │◄────┘
    └────┬──────┘
         │
         ▼
    ┌────────────┐   ◄── reflection loop ──┐
    │ Comparator │    (confidence < 0.7)   │
    └────┬───────┘                         │
         │                                 │
         ▼                                 │
    ┌─────────┐    low confidence          │
    │  Writer  │───────────────────────────┘
    └────┬─────┘
         │ high confidence
         ▼
    ┌──────────┐
    │ Finalize │───▶ Persist report + status
    └────┬─────┘
         │                    ┌──────────────┐
         ▼                    │ Dead-Letter   │
    ┌──────────┐              │ Queue         │
    │   END    │     ◄────────│ (on failure)  │
    └──────────┘              └──────────────┘
    """

    # ── Build the graph ────────────────────────────────────────────
    builder = StateGraph(ResearchState)

    # ── Add nodes with persistence tracking wrappers ───────────────
    builder.add_node("planner", _wrap_with_tracking(planner_node, "planner"))
    builder.add_node("gatherer", _wrap_with_tracking(gatherer_node, "gatherer"))
    builder.add_node("extractor", _wrap_with_tracking(extractor_node, "extractor"))
    builder.add_node("comparator", _wrap_with_tracking(comparator_node, "comparator"))
    builder.add_node("writer", _wrap_with_tracking(writer_node, "writer"))
    builder.add_node("error_handler", _error_handler_node)
    builder.add_node("finalize", _finalize_node)

    # ── Add edges ──────────────────────────────────────────────────

    # Entry point: always start with the Planner
    builder.add_edge(START, "planner")

    # After Planner: check if planning succeeded
    builder.add_conditional_edges(
        "planner",
        route_after_planning,
        {
            "planner": "planner",          # Retry (with backoff)
            "gatherer": "gatherer",        # Success → next stage
            "error_handler": "error_handler",  # Dead-letter
        }
    )

    # After Gatherer: check if sources were retrieved
    builder.add_conditional_edges(
        "gatherer",
        route_after_gathering,
        {
            "gatherer": "gatherer",        # Retry (with backoff)
            "extractor": "extractor",      # Success → next stage
            "error_handler": "error_handler",  # Dead-letter
        }
    )

    # After Extractor: check if facts were extracted
    builder.add_conditional_edges(
        "extractor",
        route_after_extraction,
        {
            "extractor": "extractor",      # Retry (with backoff)
            "comparator": "comparator",    # Success → next stage
            "error_handler": "error_handler",  # Dead-letter
        }
    )

    # After Comparator: always proceed to Writer
    builder.add_conditional_edges(
        "comparator",
        route_after_comparison,
        {
            "writer": "writer",
        }
    )

    # After Writer: confidence-aware branching
    builder.add_conditional_edges(
        "writer",
        route_after_writing,
        {
            "comparator": "comparator",    # Reflection loop: revise
            "finalize": "finalize",        # Quality met → finish
            "error_handler": "error_handler",  # Dead-letter
        }
    )

    # Error handler → always finalize (graceful degradation)
    builder.add_edge("error_handler", "finalize")

    # Finalize → END
    builder.add_edge("finalize", END)

    # ── Compile with checkpointing ─────────────────────────────────
    checkpointer = MemorySaver() if use_memory_checkpoint else None
    graph = builder.compile(checkpointer=checkpointer)

    logger.info("Research workflow graph compiled successfully.")
    return graph

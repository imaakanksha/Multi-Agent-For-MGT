"""
LangGraph StateGraph definition — the core orchestration layer.

This module assembles the complete multi-agent workflow as a directed
graph with conditional edges, parallel execution paths, and a
reflection loop for quality assurance.

Architecture Pattern: Supervisor with Reflection
  - Linear pipeline: Planner → Gatherer → Extractor → Comparator → Writer
  - Reflection loop: Writer ⟷ Comparator (if confidence < threshold)
  - Error recovery: Any failed stage can retry or gracefully degrade

References:
  - LangGraph Docs: https://langchain-ai.github.io/langgraph/
  - Multi-agent patterns: https://langchain-ai.github.io/langgraph/concepts/multi_agent/
"""

from __future__ import annotations
import logging
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
from agents.planner import planner_node
from agents.gatherer import gatherer_node
from agents.extractor import extractor_node
from agents.comparator import comparator_node
from agents.writer import writer_node

logger = logging.getLogger(__name__)


def _error_handler_node(state: dict) -> dict:
    """
    Error handler node — produces a partial report or logs final failure.
    Implements graceful degradation: the system always attempts to
    produce some output rather than failing silently.
    """
    logger.error("Workflow entered error handler. Errors: %s", state.get("error_log", []))
    return {
        "workflow_status": "failed",
        "current_stage": "error",
        "error_log": [f"Workflow failed at stage: {state.get('current_stage', 'unknown')}"],
    }


def _finalize_node(state: dict) -> dict:
    """
    Finalization node — marks the workflow as completed and performs
    any final cleanup or persistence operations.
    """
    status = "completed" if state.get("final_report") else "partial"
    logger.info("Workflow finalized with status: %s", status)
    return {
        "workflow_status": status,
        "current_stage": "finalized",
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
    ┌──────────┐     retry
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
    │ Comparator │                         │
    └────┬───────┘                         │
         │                                 │
         ▼                                 │
    ┌─────────┐    low confidence          │
    │  Writer  │───────────────────────────┘
    └────┬─────┘
         │ high confidence
         ▼
    ┌──────────┐
    │ Finalize │
    └────┬─────┘
         │
         ▼
    ┌──────────┐
    │   END    │
    └──────────┘
    """

    # ── Build the graph ────────────────────────────────────────────
    builder = StateGraph(ResearchState)

    # ── Add nodes (each node = one specialized agent) ──────────────
    builder.add_node("planner", planner_node)
    builder.add_node("gatherer", gatherer_node)
    builder.add_node("extractor", extractor_node)
    builder.add_node("comparator", comparator_node)
    builder.add_node("writer", writer_node)
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
            "planner": "planner",          # Retry
            "gatherer": "gatherer",        # Success → next stage
            "error_handler": "error_handler",
        }
    )

    # After Gatherer: check if sources were retrieved
    builder.add_conditional_edges(
        "gatherer",
        route_after_gathering,
        {
            "gatherer": "gatherer",        # Retry
            "extractor": "extractor",      # Success → next stage
            "error_handler": "error_handler",
        }
    )

    # After Extractor: check if facts were extracted
    builder.add_conditional_edges(
        "extractor",
        route_after_extraction,
        {
            "extractor": "extractor",      # Retry
            "comparator": "comparator",    # Success → next stage
            "error_handler": "error_handler",
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

    # After Writer: reflection loop or finalize
    builder.add_conditional_edges(
        "writer",
        route_after_writing,
        {
            "comparator": "comparator",    # Reflection loop: revise
            "finalize": "finalize",        # Quality met → finish
            "error_handler": "error_handler",
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

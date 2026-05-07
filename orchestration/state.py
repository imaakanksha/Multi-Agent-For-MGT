"""
Typed state schema for the Multi-Agent Research Workflow.

This is the shared "whiteboard" that all agents read from and write to.
Uses TypedDict with Annotated reducer functions to safely handle
parallel state updates — a LangGraph best practice.

References:
  - LangGraph State Management: https://langchain-ai.github.io/langgraph/concepts/low_level/#state
  - Reducer functions prevent data loss during parallel node execution.
"""

from __future__ import annotations
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

from models.source import (
    SearchQuery,
    RawSourceData,
    ExtractedFact,
    ComparisonResult,
)
from models.report import (
    ResearchOutline,
    ResearchReport,
    OpenQuestion,
)


# ─── Reducer Functions ────────────────────────────────────────────────
# These functions define HOW state fields are merged when multiple
# agents update the same field. Without reducers, the last write wins
# and earlier updates are lost — a critical bug in parallel workflows.

def merge_lists(existing: list, new: list) -> list:
    """Append new items to existing list (deduplicate by identity)."""
    if existing is None:
        return new or []
    if new is None:
        return existing
    return existing + new


def replace_value(existing, new):
    """Last-write-wins replacement for scalar values."""
    return new if new is not None else existing


# ─── Workflow State Schema ────────────────────────────────────────────

class ResearchState(TypedDict):
    """
    Complete state schema for the research workflow.

    This TypedDict is the single source of truth passed between all
    agents in the LangGraph StateGraph. Each field is annotated with
    a reducer function that controls how concurrent updates are merged.

    State Flow:
        1. Planner writes: research_prompt, outline, search_queries
        2. Gatherer writes: raw_sources
        3. Extractor writes: extracted_facts
        4. Comparator writes: comparisons, open_questions
        5. Writer writes: final_report
    """

    # ── Input ──────────────────────────────────────────────────────
    research_prompt: Annotated[str, replace_value]

    # ── Message history (for agent communication & debugging) ──────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Stage 1: Planning ──────────────────────────────────────────
    outline: Annotated[ResearchOutline | None, replace_value]
    search_queries: Annotated[list[SearchQuery], merge_lists]

    # ── Stage 2: Gathering ─────────────────────────────────────────
    raw_sources: Annotated[list[RawSourceData], merge_lists]

    # ── Stage 3: Extraction ────────────────────────────────────────
    extracted_facts: Annotated[list[ExtractedFact], merge_lists]

    # ── Stage 4: Comparison ────────────────────────────────────────
    comparisons: Annotated[list[ComparisonResult], merge_lists]
    open_questions: Annotated[list[OpenQuestion], merge_lists]

    # ── Stage 5: Writing ───────────────────────────────────────────
    final_report: Annotated[ResearchReport | None, replace_value]

    # ── Control Flow ───────────────────────────────────────────────
    current_stage: Annotated[str, replace_value]       # Current pipeline stage
    error_log: Annotated[list[str], merge_lists]       # Accumulated errors
    retry_count: Annotated[int, replace_value]         # Current retry counter
    revision_count: Annotated[int, replace_value]      # Writer revision loops
    workflow_status: Annotated[str, replace_value]     # running | completed | failed


def create_initial_state(research_prompt: str) -> dict:
    """
    Create a fresh initial state for a new research workflow run.

    Args:
        research_prompt: The user's research question or topic.

    Returns:
        Dictionary matching the ResearchState schema, ready to be
        passed into the LangGraph StateGraph.
    """
    return {
        "research_prompt": research_prompt,
        "messages": [],
        "outline": None,
        "search_queries": [],
        "raw_sources": [],
        "extracted_facts": [],
        "comparisons": [],
        "open_questions": [],
        "final_report": None,
        "current_stage": "planning",
        "error_log": [],
        "retry_count": 0,
        "revision_count": 0,
        "workflow_status": "running",
    }

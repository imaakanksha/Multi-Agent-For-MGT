"""
Planner Agent — Stage 1 of the Research Workflow.

═══════════════════════════════════════════════════════════════════
PURPOSE:
    Analyzes the user's research prompt and produces a structured
    research outline with targeted search queries.

HOW IT WORKS (Step-by-Step):
    1. Receives the raw research prompt from the state.
    2. Sends the prompt to a high-capability LLM (e.g., GPT-4o)
       with a structured output schema.
    3. The LLM generates:
       - A research outline (title, objective, sections, key questions)
       - A set of search queries optimized for different source types
    4. Writes the outline and queries back to the shared state.

WHY PLANNING FIRST?
    Planning before research prevents "scope drift" — where an agent
    retrieves too much irrelevant information or misses critical angles.
    The outline acts as a roadmap that keeps all downstream agents focused.

TRIGGER:
    This is always the first node executed (entry edge from START).

ERROR HANDLING:
    - If the LLM fails to produce valid structured output, the planner
      returns an error flag, and the router retries up to MAX_RETRIES.
    - Malformed JSON is caught and logged.
═══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import json
import uuid
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from config import config
from models.source import SearchQuery, SourceType
from models.report import ResearchOutline

logger = logging.getLogger(__name__)

# ── System Prompt ──────────────────────────────────────────────────────
PLANNER_SYSTEM_PROMPT = """You are a Research Planner Agent. Your job is to analyze a research prompt and create a structured research plan.

Given a research prompt, you must produce a JSON response with the following structure:

{
    "title": "A concise, descriptive title for the research report",
    "objective": "A clear 1-2 sentence statement of what this research aims to discover",
    "sections": [
        "Section 1 Title",
        "Section 2 Title",
        "Section 3 Title"
    ],
    "key_questions": [
        "Question 1 that the research should answer",
        "Question 2 that the research should answer"
    ],
    "search_strategy": "Brief description of the search approach",
    "search_queries": [
        {
            "query_text": "Specific search query optimized for web search",
            "target_source": "web_api",
            "priority": 1,
            "rationale": "Why this query is important"
        },
        {
            "query_text": "Another search query for document sources",
            "target_source": "document",
            "priority": 2,
            "rationale": "Why this query is needed"
        }
    ]
}

RULES:
- Generate at least 4 search queries targeting at least 2 different source types
- Each section should represent a distinct aspect of the research topic
- Key questions should be specific and answerable
- Search queries should use varied phrasing to maximize source diversity
- Prioritize queries (1=most important, 5=least important)
- ONLY output valid JSON. No markdown, no explanation text.
"""


def planner_node(state: dict) -> dict:
    """
    Planner Agent node function for LangGraph.

    Args:
        state: Current ResearchState dictionary.

    Returns:
        State update with outline, search_queries, and control fields.
    """
    prompt = state.get("research_prompt", "")
    logger.info("Planner Agent activated for prompt: %s", prompt[:100])

    try:
        # ── Step 1: Initialize the LLM ────────────────────────────
        llm = ChatOpenAI(
            model=config.llm.model_planning,
            api_key=config.llm.api_key,
            temperature=0.3,  # Low temperature for structured planning
            response_format={"type": "json_object"},
        )

        # ── Step 2: Construct the messages ─────────────────────────
        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=f"Research Prompt: {prompt}"),
        ]

        # ── Step 3: Invoke the LLM ────────────────────────────────
        response = llm.invoke(messages)
        plan_data = json.loads(response.content)

        # ── Step 4: Parse into typed models ────────────────────────
        outline = ResearchOutline(
            title=plan_data.get("title", "Untitled Research"),
            objective=plan_data.get("objective", ""),
            sections=plan_data.get("sections", []),
            key_questions=plan_data.get("key_questions", []),
            search_strategy=plan_data.get("search_strategy", ""),
        )

        search_queries = []
        for q in plan_data.get("search_queries", []):
            search_queries.append(SearchQuery(
                query_text=q.get("query_text", ""),
                target_source=SourceType(q.get("target_source", "web_api")),
                priority=q.get("priority", 3),
                rationale=q.get("rationale", ""),
            ))

        logger.info(
            "Planner produced outline with %d sections and %d queries",
            len(outline.sections), len(search_queries)
        )

        # ── Step 5: Return state update ────────────────────────────
        return {
            "outline": outline,
            "search_queries": search_queries,
            "current_stage": "planning_complete",
            "messages": [HumanMessage(
                content=f"[Planner] Created outline: '{outline.title}' "
                        f"with {len(outline.sections)} sections and "
                        f"{len(search_queries)} search queries."
            )],
        }

    except json.JSONDecodeError as e:
        logger.error("Planner failed to parse LLM JSON response: %s", e)
        return {
            "current_stage": "planning",
            "retry_count": state.get("retry_count", 0) + 1,
            "error_log": [f"Planner JSON parse error: {str(e)}"],
            "messages": [HumanMessage(
                content=f"[Planner] ERROR: Failed to parse planning output. Retry #{state.get('retry_count', 0) + 1}"
            )],
        }
    except Exception as e:
        logger.error("Planner encountered unexpected error: %s", e)
        return {
            "current_stage": "planning",
            "retry_count": state.get("retry_count", 0) + 1,
            "error_log": [f"Planner error: {str(e)}"],
            "messages": [HumanMessage(
                content=f"[Planner] ERROR: {str(e)}"
            )],
        }

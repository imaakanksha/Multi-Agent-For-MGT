"""
Comparator Agent — Stage 4 of the Research Workflow.

PURPOSE: Cross-references extracted facts to identify agreements,
conflicts, and gaps between sources.

STEPS:
  1. Groups extracted facts by category
  2. Sends grouped facts to LLM for cross-source comparison
  3. Produces ComparisonResult objects and identifies open questions
"""

from __future__ import annotations
import json
import logging
from collections import defaultdict
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import config
from models.source import ComparisonResult, SourceAgreement, ExtractedFact
from models.report import OpenQuestion

logger = logging.getLogger(__name__)

COMPARATOR_SYSTEM_PROMPT = """You are a Source Comparison Agent. Compare facts from multiple sources to find agreements and conflicts.

Given facts grouped by category, return JSON:
{
    "comparisons": [
        {
            "topic": "The claim being compared",
            "agreement_status": "agree|conflict|partial|unique",
            "supporting_fact_ids": ["id1", "id2"],
            "conflicting_fact_ids": ["id3"],
            "explanation": "Why sources agree or conflict",
            "confidence": 0.8
        }
    ],
    "open_questions": [
        {
            "question": "What remains unanswered?",
            "context": "Why this is unresolved",
            "priority": "high|medium|low"
        }
    ]
}
ONLY output valid JSON."""


def comparator_node(state: dict) -> dict:
    facts = state.get("extracted_facts", [])
    logger.info("Comparator activated with %d facts", len(facts))

    # Group facts by category
    by_category = defaultdict(list)
    for f in facts:
        by_category[f.category].append(f)

    # Build fact map for lookup
    fact_map = {f.fact_id: f for f in facts}

    llm = ChatOpenAI(
        model=config.llm.model_planning, api_key=config.llm.api_key,
        temperature=0.2, response_format={"type": "json_object"},
    )

    all_comparisons = []
    all_questions = []

    for category, cat_facts in by_category.items():
        if len(cat_facts) < 1:
            continue

        facts_text = "\n".join(
            f"- [{f.fact_id[:8]}] (source: {f.citations[0].source_name if f.citations else 'unknown'}) "
            f"{f.claim}" for f in cat_facts
        )

        messages = [
            SystemMessage(content=COMPARATOR_SYSTEM_PROMPT),
            HumanMessage(content=f"Category: {category}\n\nFacts:\n{facts_text}"),
        ]

        try:
            response = llm.invoke(messages)
            data = json.loads(response.content)

            for c in data.get("comparisons", []):
                supporting = [fact_map[fid] for fid in c.get("supporting_fact_ids", []) if fid in fact_map]
                conflicting = [fact_map[fid] for fid in c.get("conflicting_fact_ids", []) if fid in fact_map]

                all_comparisons.append(ComparisonResult(
                    topic=c.get("topic", ""),
                    agreement_status=SourceAgreement(c.get("agreement_status", "unique")),
                    supporting_facts=supporting,
                    conflicting_facts=conflicting,
                    explanation=c.get("explanation", ""),
                    confidence=float(c.get("confidence", 0.5)),
                ))

            for q in data.get("open_questions", []):
                all_questions.append(OpenQuestion(
                    question=q.get("question", ""),
                    context=q.get("context", ""),
                    priority=q.get("priority", "medium"),
                ))

        except Exception as e:
            logger.warning("Comparison failed for category '%s': %s", category, e)

    logger.info("Comparator completed: %d comparisons, %d open questions",
                len(all_comparisons), len(all_questions))

    return {
        "comparisons": all_comparisons,
        "open_questions": all_questions,
        "current_stage": "comparison_complete",
        "messages": [HumanMessage(
            content=f"[Comparator] Found {len(all_comparisons)} comparisons, "
                    f"{len(all_questions)} open questions"
        )],
    }

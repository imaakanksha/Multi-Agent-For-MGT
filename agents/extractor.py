"""
Extractor Agent — Stage 3 of the Research Workflow.

PURPOSE: Processes raw source material and extracts structured facts
with confidence scores using a cost-efficient LLM.

STEPS:
  1. Reads raw_sources from state
  2. Sends each source to GPT-4o-mini for fact extraction
  3. Returns structured ExtractedFact objects with citations
"""

from __future__ import annotations
import json
import uuid
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import config
from models.source import ExtractedFact, Citation, RawSourceData

logger = logging.getLogger(__name__)

EXTRACTOR_SYSTEM_PROMPT = """You are a Fact Extraction Agent. Extract discrete factual claims from source material.
Return JSON: {"facts": [{"claim": "...", "category": "...", "confidence": 0.85, "is_quantitative": true, "raw_value": "$4.2B"}]}
Rules: Only verifiable facts, 3-10 per source, confidence 0-1, ONLY valid JSON."""


def _extract_from_source(source, llm, outline_sections):
    if not source.raw_content or source.retrieval_status != "success":
        return []
    content = source.raw_content[:8000]
    section_hint = ", ".join(outline_sections) if outline_sections else "General"
    messages = [
        SystemMessage(content=EXTRACTOR_SYSTEM_PROMPT),
        HumanMessage(content=f"Source: {source.source_name}\nSections: {section_hint}\n\nContent:\n{content}"),
    ]
    try:
        response = llm.invoke(messages)
        data = json.loads(response.content)
        facts = []
        for f in data.get("facts", []):
            citation = Citation(
                source_id=source.source_id, source_name=source.source_name,
                source_type=source.source_type, url=source.url,
                snippet=f.get("claim", "")[:200],
            )
            facts.append(ExtractedFact(
                fact_id=str(uuid.uuid4()), claim=f.get("claim", ""),
                category=f.get("category", "Other"),
                confidence=float(f.get("confidence", 0.5)),
                citations=[citation], is_quantitative=f.get("is_quantitative", False),
                raw_value=f.get("raw_value"),
            ))
        return facts
    except Exception as e:
        logger.warning("Extraction failed for '%s': %s", source.source_name, e)
        return []


def extractor_node(state: dict) -> dict:
    raw_sources = state.get("raw_sources", [])
    outline = state.get("outline")
    outline_sections = outline.sections if outline else []
    logger.info("Extractor activated with %d sources", len(raw_sources))

    llm = ChatOpenAI(
        model=config.llm.model_extraction, api_key=config.llm.api_key,
        temperature=0.1, response_format={"type": "json_object"},
    )
    all_facts = []
    for source in raw_sources:
        if source.retrieval_status != "success":
            continue
        facts = _extract_from_source(source, llm, outline_sections)
        all_facts.extend(facts)

    high_conf = [f for f in all_facts if f.confidence >= 0.3]
    return {
        "extracted_facts": high_conf,
        "current_stage": "extraction_complete",
        "messages": [HumanMessage(content=f"[Extractor] Extracted {len(high_conf)} facts")],
    }

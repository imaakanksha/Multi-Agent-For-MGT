"""
Extractor Agent — Stage 3 of the Research Workflow.

═══════════════════════════════════════════════════════════════════
PURPOSE:
    Processes raw source material and extracts structured factual
    claims with confidence scores using a cost-efficient LLM.

LLM-DRIVEN DECISION MAKING:
    The Extractor doesn't just parse text — it uses the LLM to:
    1. Identify which claims are factual vs. opinion
    2. Assign confidence scores based on source reliability
    3. Classify facts into outline categories
    4. Decide whether quantitative values can be extracted

GUARDRAILS INTEGRATION:
    - Output schema enforcement (valid JSON with required keys)
    - LLM refusal detection (route gracefully if model refuses)
    - Content truncation to avoid token limits

STEPS:
    1. Reads raw_sources from state
    2. Sends each source to GPT-4o-mini for fact extraction
    3. Validates output with guardrails (schema + refusal check)
    4. Returns structured ExtractedFact objects with citations
═══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import json
import uuid
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import config
from models.source import ExtractedFact, Citation, RawSourceData
from guardrails import enforce_json_schema, detect_refusal

logger = logging.getLogger(__name__)

EXTRACTOR_SYSTEM_PROMPT = """You are a Fact Extraction Agent. Extract discrete factual claims from source material.

Return JSON:
{
    "facts": [
        {
            "claim": "A specific, verifiable factual statement",
            "category": "Category matching the research outline section",
            "confidence": 0.85,
            "is_quantitative": true,
            "raw_value": "$4.2B"
        }
    ]
}

Rules:
- Extract 3-10 facts per source
- Only include verifiable factual claims, not opinions
- Confidence 0.0-1.0 based on source reliability and specificity
- Mark claims with numbers/percentages as is_quantitative=true
- Include the raw numerical value when quantitative
- Category should match one of the research outline sections if possible
- ONLY output valid JSON. No markdown, no explanation text.
"""


def _extract_from_source(source: RawSourceData, llm, outline_sections: list[str]) -> list[ExtractedFact]:
    """
    Extract facts from a single source using LLM + guardrails.

    The LLM decides:
      - Which statements are factual claims
      - What confidence to assign each (LLM-driven scoring)
      - How to categorize each fact against the outline
      - Whether quantitative data can be extracted
    """
    if not source.raw_content or source.retrieval_status != "success":
        return []

    # Truncate to prevent token limit errors
    content = source.raw_content[:8000]
    section_hint = ", ".join(outline_sections) if outline_sections else "General"

    messages = [
        SystemMessage(content=EXTRACTOR_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"Source: {source.source_name}\n"
            f"Source Type: {source.source_type.value}\n"
            f"Research Sections: {section_hint}\n\n"
            f"Content:\n{content}"
        )),
    ]

    try:
        response = llm.invoke(messages)

        # ── Guardrail 1: Check for LLM refusal ────────────────────
        refusal_result = detect_refusal(response.content)
        if refusal_result.is_refusal:
            logger.warning(
                "Extractor LLM refused for source '%s' (type=%s). Skipping.",
                source.source_name, refusal_result.refusal_type,
            )
            return []

        # ── Guardrail 2: Enforce output JSON schema ───────────────
        schema_result = enforce_json_schema(
            response.content,
            required_keys=["facts"],
        )
        if not schema_result.is_valid:
            logger.warning(
                "Extractor output schema invalid for '%s': %s",
                source.source_name, schema_result.errors,
            )
            return []

        data = schema_result.parsed_data

        # ── Parse validated facts ─────────────────────────────────
        facts = []
        for f in data.get("facts", []):
            # Validate individual fact fields
            claim = f.get("claim", "").strip()
            if not claim or len(claim) < 5:
                continue  # Skip empty/trivial claims

            confidence = float(f.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]

            citation = Citation(
                source_id=source.source_id,
                source_name=source.source_name,
                source_type=source.source_type,
                url=source.url,
                snippet=claim[:200],
            )

            facts.append(ExtractedFact(
                fact_id=str(uuid.uuid4()),
                claim=claim,
                category=f.get("category", "Other"),
                confidence=confidence,
                citations=[citation],
                is_quantitative=bool(f.get("is_quantitative", False)),
                raw_value=f.get("raw_value"),
            ))

        logger.info(
            "Extracted %d facts from '%s' (confidence range: %.2f-%.2f)",
            len(facts), source.source_name,
            min((f.confidence for f in facts), default=0),
            max((f.confidence for f in facts), default=0),
        )
        return facts

    except json.JSONDecodeError as e:
        logger.warning("Extraction JSON parse failed for '%s': %s", source.source_name, e)
        return []
    except Exception as e:
        logger.warning("Extraction failed for '%s': %s", source.source_name, e)
        return []


def extractor_node(state: dict) -> dict:
    """
    Extractor Agent node function for LangGraph.

    Uses LLM to make extraction decisions:
      - Which statements are factual claims (decision)
      - Confidence scoring per fact (decision)
      - Category assignment (decision)
      - Quantitative value extraction (decision)

    All outputs pass through guardrails before being accepted.
    """
    raw_sources = state.get("raw_sources", [])
    outline = state.get("outline")
    outline_sections = outline.sections if outline else []
    corr_id = state.get("correlation_id", "?")[:12]

    logger.info("[%s] Extractor activated with %d sources", corr_id, len(raw_sources))

    llm = ChatOpenAI(
        model=config.llm.model_extraction,
        api_key=config.llm.api_key,
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    all_facts = []
    extraction_stats = {"processed": 0, "skipped": 0, "refusals": 0}

    for source in raw_sources:
        if source.retrieval_status != "success":
            extraction_stats["skipped"] += 1
            continue

        extraction_stats["processed"] += 1
        facts = _extract_from_source(source, llm, outline_sections)
        all_facts.extend(facts)

    # Filter low-confidence facts (LLM-assigned threshold)
    high_conf = [f for f in all_facts if f.confidence >= 0.3]
    filtered_count = len(all_facts) - len(high_conf)

    logger.info(
        "[%s] Extractor completed: %d facts extracted, %d filtered (low confidence), "
        "stats: %s",
        corr_id, len(high_conf), filtered_count, extraction_stats,
    )

    return {
        "extracted_facts": high_conf,
        "current_stage": "extraction_complete",
        "messages": [HumanMessage(
            content=f"[Extractor] Extracted {len(high_conf)} facts "
                    f"from {extraction_stats['processed']} sources "
                    f"({filtered_count} filtered for low confidence)"
        )],
    }

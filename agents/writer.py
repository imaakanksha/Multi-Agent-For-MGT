"""
Writer Agent — Stage 5 of the Research Workflow.

PURPOSE: Synthesizes all extracted facts, comparisons, and open
questions into a polished, structured research report.

STEPS:
  1. Reads outline, facts, comparisons, and open_questions from state
  2. Constructs a comprehensive prompt with all context
  3. Sends to a high-capability LLM for report generation
  4. Parses output into the ResearchReport Pydantic model
  5. Calculates overall confidence and metadata
"""

from __future__ import annotations
import json
import uuid
import time
import logging
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import config
from models.source import Citation, ComparisonResult, SourceAgreement
from models.report import (
    ResearchReport, ReportMetadata, ReportSection,
    ReportBulletPoint, AgreementSummary, OpenQuestion,
)

logger = logging.getLogger(__name__)

WRITER_SYSTEM_PROMPT = """You are a Research Report Writer Agent. Synthesize research findings into a structured report.

Given an outline, extracted facts, and source comparisons, produce JSON:
{
    "executive_summary": "2-3 paragraph summary of key findings",
    "sections": [
        {
            "title": "Section Title",
            "summary": "Brief section summary",
            "bullet_points": [
                {"text": "Key finding with specific data", "citation_sources": ["Source Name"]}
            ]
        }
    ]
}

Rules:
- Every bullet point should cite its source
- Highlight where sources agree or conflict
- Be specific with numbers and data
- Write in professional, analytical tone
- ONLY output valid JSON"""


def writer_node(state: dict) -> dict:
    start_time = time.time()
    outline = state.get("outline")
    facts = state.get("extracted_facts", [])
    comparisons = state.get("comparisons", [])
    open_questions = state.get("open_questions", [])
    prompt = state.get("research_prompt", "")
    revision_count = state.get("revision_count", 0)

    logger.info("Writer activated (revision #%d) with %d facts, %d comparisons",
                revision_count, len(facts), len(comparisons))

    llm = ChatOpenAI(
        model=config.llm.model_writing, api_key=config.llm.api_key,
        temperature=0.4, response_format={"type": "json_object"},
    )

    # Build context for the writer
    facts_text = "\n".join(f"- [{f.category}] {f.claim} (confidence: {f.confidence})" for f in facts[:50])
    comparisons_text = "\n".join(
        f"- [{c.agreement_status.value}] {c.topic}: {c.explanation}" for c in comparisons[:20]
    )
    outline_text = ""
    if outline:
        outline_text = f"Title: {outline.title}\nSections: {', '.join(outline.sections)}"

    messages = [
        SystemMessage(content=WRITER_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"Research Prompt: {prompt}\n\n"
            f"Outline:\n{outline_text}\n\n"
            f"Extracted Facts:\n{facts_text}\n\n"
            f"Source Comparisons:\n{comparisons_text}"
        )),
    ]

    try:
        response = llm.invoke(messages)
        data = json.loads(response.content)

        # Build citation index
        all_citations = []
        for f in facts:
            all_citations.extend(f.citations)
        unique_citations = {c.source_id: c for c in all_citations}

        # Build sections
        sections = []
        for s in data.get("sections", []):
            bps = []
            for bp in s.get("bullet_points", []):
                cited = [unique_citations[cid] for cid in unique_citations
                         if any(name in unique_citations[cid].source_name
                                for name in bp.get("citation_sources", []))]
                bps.append(ReportBulletPoint(
                    text=bp.get("text", ""), citations=cited[:3],
                ))
            # Attach relevant comparisons to section
            section_comps = [c for c in comparisons if any(
                kw.lower() in s.get("title", "").lower()
                for kw in c.topic.split()[:3]
            )]
            sections.append(ReportSection(
                title=s.get("title", ""),
                summary=s.get("summary", ""),
                bullet_points=bps,
                source_comparisons=section_comps[:5],
            ))

        # Calculate agreement summary
        agree_count = sum(1 for c in comparisons if c.agreement_status == SourceAgreement.AGREE)
        conflict_count = sum(1 for c in comparisons if c.agreement_status == SourceAgreement.CONFLICT)
        partial_count = sum(1 for c in comparisons if c.agreement_status == SourceAgreement.PARTIAL)
        unique_count = sum(1 for c in comparisons if c.agreement_status == SourceAgreement.UNIQUE)
        total = len(comparisons) or 1

        agreement_summary = AgreementSummary(
            total_comparisons=len(comparisons),
            agreements=agree_count, conflicts=conflict_count,
            partial_agreements=partial_count, unique_claims=unique_count,
            agreement_rate=agree_count / total,
        )

        # Calculate overall confidence
        fact_conf = sum(f.confidence for f in facts) / max(len(facts), 1)
        comp_conf = sum(c.confidence for c in comparisons) / max(len(comparisons), 1)
        overall_conf = (fact_conf + comp_conf) / 2

        raw_sources = state.get("raw_sources", [])
        elapsed = time.time() - start_time

        report = ResearchReport(
            metadata=ReportMetadata(
                report_id=str(uuid.uuid4()),
                research_prompt=prompt,
                total_sources_consulted=len(raw_sources),
                total_facts_extracted=len(facts),
                overall_confidence=overall_conf,
                generation_time_seconds=elapsed,
                model_versions={
                    "planning": config.llm.model_planning,
                    "extraction": config.llm.model_extraction,
                    "writing": config.llm.model_writing,
                },
                revision_count=revision_count,
            ),
            executive_summary=data.get("executive_summary", ""),
            sections=sections,
            source_agreement_summary=agreement_summary,
            key_conflicts=[c for c in comparisons if c.agreement_status == SourceAgreement.CONFLICT],
            open_questions=open_questions,
            all_citations=list(unique_citations.values()),
        )

        logger.info("Writer completed. Confidence: %.2f, Sections: %d",
                     overall_conf, len(sections))

        return {
            "final_report": report,
            "current_stage": "writing_complete",
            "revision_count": revision_count + 1,
            "messages": [HumanMessage(
                content=f"[Writer] Report generated with {len(sections)} sections, "
                        f"confidence: {overall_conf:.2f}"
            )],
        }

    except Exception as e:
        logger.error("Writer failed: %s", e)
        return {
            "current_stage": "writing",
            "error_log": [f"Writer error: {str(e)}"],
            "revision_count": revision_count + 1,
            "messages": [HumanMessage(content=f"[Writer] ERROR: {str(e)}")],
        }

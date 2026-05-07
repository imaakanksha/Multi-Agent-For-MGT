"""
Evaluation Harness — Deterministic fixtures, scoring, and test cases
for validating multi-agent research workflow quality.

Provides:
  1. DETERMINISTIC FIXTURES: Pre-built inputs and expected outputs
     that produce repeatable results without calling live LLMs.

  2. SCORING HARNESS: Automated quality metrics for generated reports
     (coverage, citation density, conflict detection, etc.).

  3. REGRESSION TEST CASES: End-to-end assertions that the pipeline
     produces structurally valid output for known inputs.

Usage:
    python -m pytest evaluation/ -v
    python -m evaluation.scoring --report sample_output/sample_report.json
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from models.source import (
    ExtractedFact, Citation, SourceType,
    ComparisonResult, SourceAgreement, RawSourceData,
)
from models.report import (
    ResearchReport, ReportMetadata, ReportSection,
    ReportBulletPoint, AgreementSummary, OpenQuestion,
    ResearchOutline,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# 1. DETERMINISTIC FIXTURES
# ══════════════════════════════════════════════════════════════════════

def get_fixture_outline() -> ResearchOutline:
    """Deterministic research outline for testing."""
    return ResearchOutline(
        title="AI Developer Tools Market Analysis 2026",
        objective="Analyze market size, competition, and trends in AI dev tools",
        sections=[
            "Market Size & Growth",
            "Competitive Landscape",
            "Productivity Impact",
            "Future Outlook",
        ],
        key_questions=[
            "What is the total addressable market?",
            "Who are the top 3 players by market share?",
            "What ROI do enterprises see from AI tools?",
        ],
        search_strategy="Multi-source: analyst reports + surveys + press releases",
    )


def get_fixture_sources() -> list[RawSourceData]:
    """Deterministic raw sources for testing extraction."""
    return [
        RawSourceData(
            source_id="fixture-src-001",
            source_name="Gartner AI Dev Tools Report",
            source_type=SourceType.WEB_API,
            url="https://gartner.com/ai-dev-tools-2026",
            raw_content=(
                "The global AI developer tools market reached $15.2 billion in 2026, "
                "growing 35% year-over-year. GitHub Copilot leads with approximately "
                "40% market share and over 15 million subscribers. Enterprise adoption "
                "hit 67% for organizations with 500+ developers. The compound annual "
                "growth rate is projected at 32.8% through 2030."
            ),
            retrieval_status="success",
        ),
        RawSourceData(
            source_id="fixture-src-002",
            source_name="IDC Worldwide AI Software Forecast",
            source_type=SourceType.DOCUMENT,
            url="https://idc.com/ai-software-forecast",
            raw_content=(
                "IDC estimates the AI developer tools market at $18.7 billion in 2026, "
                "with 42% growth. Amazon CodeWhisperer holds 12% share through AWS "
                "bundling. Cursor has captured 18% share with its AI-first IDE approach. "
                "Developer productivity gains average 30-55% for routine tasks."
            ),
            retrieval_status="success",
        ),
    ]


def get_fixture_facts() -> list[ExtractedFact]:
    """Deterministic extracted facts for testing comparison."""
    return [
        ExtractedFact(
            fact_id="fix-f001",
            claim="AI dev tools market size is $15.2 billion in 2026",
            category="Market Size & Growth",
            confidence=0.88,
            citations=[Citation(
                source_id="fixture-src-001",
                source_name="Gartner AI Dev Tools Report",
                source_type=SourceType.WEB_API,
                url="https://gartner.com/ai-dev-tools-2026",
                snippet="market reached $15.2 billion",
            )],
            is_quantitative=True,
            raw_value="$15.2B",
        ),
        ExtractedFact(
            fact_id="fix-f002",
            claim="AI dev tools market size is $18.7 billion in 2026",
            category="Market Size & Growth",
            confidence=0.85,
            citations=[Citation(
                source_id="fixture-src-002",
                source_name="IDC Worldwide AI Software Forecast",
                source_type=SourceType.DOCUMENT,
                url="https://idc.com/ai-software-forecast",
                snippet="market at $18.7 billion",
            )],
            is_quantitative=True,
            raw_value="$18.7B",
        ),
        ExtractedFact(
            fact_id="fix-f003",
            claim="GitHub Copilot leads with ~40% market share",
            category="Competitive Landscape",
            confidence=0.90,
            citations=[Citation(
                source_id="fixture-src-001",
                source_name="Gartner AI Dev Tools Report",
                source_type=SourceType.WEB_API,
                url="https://gartner.com/ai-dev-tools-2026",
                snippet="Copilot leads with approximately 40%",
            )],
            is_quantitative=True,
            raw_value="40%",
        ),
        ExtractedFact(
            fact_id="fix-f004",
            claim="Developer productivity gains average 30-55% for routine tasks",
            category="Productivity Impact",
            confidence=0.82,
            citations=[Citation(
                source_id="fixture-src-002",
                source_name="IDC Worldwide AI Software Forecast",
                source_type=SourceType.DOCUMENT,
                url="https://idc.com/ai-software-forecast",
                snippet="productivity gains average 30-55%",
            )],
            is_quantitative=True,
            raw_value="30-55%",
        ),
    ]


def get_fixture_report() -> ResearchReport:
    """Deterministic complete report for testing scoring."""
    facts = get_fixture_facts()
    all_citations = []
    for f in facts:
        all_citations.extend(f.citations)

    return ResearchReport(
        metadata=ReportMetadata(
            report_id="fixture-report-001",
            research_prompt="Analyze AI developer tools market in 2026",
            total_sources_consulted=2,
            total_facts_extracted=4,
            overall_confidence=0.82,
            generation_time_seconds=12.5,
            model_versions={"planning": "gpt-4o", "extraction": "gpt-4o-mini", "writing": "gpt-4o"},
            revision_count=1,
        ),
        executive_summary="The AI developer tools market has grown to $15-19B in 2026...",
        sections=[
            ReportSection(
                title="Market Size & Growth",
                summary="Market valued between $15.2B and $18.7B depending on source.",
                bullet_points=[
                    ReportBulletPoint(text="Market size $15.2B (Gartner)", citations=[all_citations[0]]),
                    ReportBulletPoint(text="Market size $18.7B (IDC)", citations=[all_citations[1]]),
                ],
                source_comparisons=[
                    ComparisonResult(
                        topic="Market size valuation",
                        agreement_status=SourceAgreement.PARTIAL,
                        supporting_facts=[facts[0]],
                        conflicting_facts=[facts[1]],
                        explanation="Gartner and IDC differ by 23% on market size",
                        confidence=0.80,
                    ),
                ],
            ),
            ReportSection(
                title="Competitive Landscape",
                summary="GitHub Copilot leads the market.",
                bullet_points=[
                    ReportBulletPoint(text="Copilot ~40% share", citations=[all_citations[2]]),
                ],
            ),
        ],
        source_agreement_summary=AgreementSummary(
            total_comparisons=3, agreements=2, conflicts=0,
            partial_agreements=1, unique_claims=0, agreement_rate=0.67,
        ),
        open_questions=[
            OpenQuestion(
                question="Long-term impact on developer skills?",
                context="No longitudinal studies beyond 18 months",
                priority="high",
            ),
        ],
        all_citations=list({c.source_id: c for c in all_citations}.values()),
    )


# ══════════════════════════════════════════════════════════════════════
# 2. SCORING HARNESS
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ReportScorecard:
    """Quality scorecard for a generated research report."""
    overall_score: float = 0.0          # 0-100
    structure_score: float = 0.0        # Has all required sections?
    citation_score: float = 0.0         # Are facts properly cited?
    coverage_score: float = 0.0         # Are outline sections covered?
    conflict_detection_score: float = 0.0  # Did it find conflicts?
    open_questions_score: float = 0.0   # Are gaps identified?
    source_diversity_score: float = 0.0 # Multiple source types?
    details: dict = field(default_factory=dict)
    passed: bool = False

    def to_dict(self) -> dict:
        return {
            "overall_score": round(self.overall_score, 1),
            "structure_score": round(self.structure_score, 1),
            "citation_score": round(self.citation_score, 1),
            "coverage_score": round(self.coverage_score, 1),
            "conflict_detection_score": round(self.conflict_detection_score, 1),
            "open_questions_score": round(self.open_questions_score, 1),
            "source_diversity_score": round(self.source_diversity_score, 1),
            "passed": self.passed,
            "details": self.details,
        }


def score_report(
    report: ResearchReport,
    expected_min_sections: int = 2,
    expected_min_sources: int = 2,
    passing_threshold: float = 60.0,
) -> ReportScorecard:
    """
    Score a research report on multiple quality dimensions.

    Dimensions (each 0-100, weighted equally):
      1. Structure: Has executive summary, sections, bibliography
      2. Citations: What % of bullet points have citations
      3. Coverage: How many sections were generated vs expected
      4. Conflict Detection: Were source conflicts identified
      5. Open Questions: Are research gaps documented
      6. Source Diversity: Multiple source types consulted

    Args:
        report: The ResearchReport to evaluate.
        expected_min_sections: Minimum sections expected.
        expected_min_sources: Minimum distinct sources expected.
        passing_threshold: Minimum overall score to pass (0-100).

    Returns:
        ReportScorecard with dimensional scores and pass/fail.
    """
    card = ReportScorecard()
    details = {}

    # ── 1. Structure Score ────────────────────────────────────────
    structure_checks = {
        "has_executive_summary": len(report.executive_summary) > 20,
        "has_sections": len(report.sections) >= expected_min_sections,
        "has_metadata": report.metadata.report_id != "",
        "has_bibliography": len(report.all_citations) > 0,
        "has_agreement_summary": report.source_agreement_summary.total_comparisons > 0,
    }
    card.structure_score = (sum(structure_checks.values()) / len(structure_checks)) * 100
    details["structure"] = structure_checks

    # ── 2. Citation Score ─────────────────────────────────────────
    total_bullets = sum(len(s.bullet_points) for s in report.sections)
    cited_bullets = sum(
        1 for s in report.sections
        for bp in s.bullet_points if bp.citations
    )
    card.citation_score = (cited_bullets / max(total_bullets, 1)) * 100
    details["citations"] = {"total_bullets": total_bullets, "cited_bullets": cited_bullets}

    # ── 3. Coverage Score ─────────────────────────────────────────
    section_count = len(report.sections)
    card.coverage_score = min((section_count / max(expected_min_sections, 1)) * 100, 100)
    details["coverage"] = {"sections_generated": section_count, "expected_min": expected_min_sections}

    # ── 4. Conflict Detection Score ───────────────────────────────
    has_comparisons = report.source_agreement_summary.total_comparisons > 0
    has_conflicts = len(report.key_conflicts) > 0
    has_partial = report.source_agreement_summary.partial_agreements > 0
    conflict_checks = sum([has_comparisons, has_conflicts or has_partial])
    card.conflict_detection_score = (conflict_checks / 2) * 100
    details["conflicts"] = {
        "comparisons_made": report.source_agreement_summary.total_comparisons,
        "conflicts_found": len(report.key_conflicts),
    }

    # ── 5. Open Questions Score ───────────────────────────────────
    card.open_questions_score = min(len(report.open_questions) * 33.3, 100)
    details["open_questions"] = {"count": len(report.open_questions)}

    # ── 6. Source Diversity Score ─────────────────────────────────
    source_types = set(c.source_type for c in report.all_citations)
    card.source_diversity_score = min((len(source_types) / max(expected_min_sources, 1)) * 100, 100)
    details["source_diversity"] = {
        "unique_types": [st.value for st in source_types],
        "unique_sources": len(report.all_citations),
    }

    # ── Overall Score (equally weighted) ──────────────────────────
    scores = [
        card.structure_score,
        card.citation_score,
        card.coverage_score,
        card.conflict_detection_score,
        card.open_questions_score,
        card.source_diversity_score,
    ]
    card.overall_score = sum(scores) / len(scores)
    card.details = details
    card.passed = card.overall_score >= passing_threshold

    return card


# ══════════════════════════════════════════════════════════════════════
# 3. CLI ENTRY POINT — Score a report file
# ══════════════════════════════════════════════════════════════════════

def score_report_file(report_path: str) -> ReportScorecard:
    """Score a report from a JSON file path."""
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    report = ResearchReport.model_validate(data)
    return score_report(report)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = "sample_output/sample_report.json"

    print(f"Scoring report: {path}")
    card = score_report_file(path)
    print(json.dumps(card.to_dict(), indent=2))
    print(f"\n{'✅ PASSED' if card.passed else '❌ FAILED'} (score: {card.overall_score:.1f}/100)")

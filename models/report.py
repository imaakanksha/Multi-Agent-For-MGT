"""
Pydantic models for the final research report structure.
Defines the schema for JSON and formatted report output.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from .source import Citation, ComparisonResult, SourceAgreement


class ReportBulletPoint(BaseModel):
    """A single bullet point within a report section."""
    text: str = Field(..., description="The bullet point content")
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class ReportSection(BaseModel):
    """A major section within the research report."""
    title: str = Field(..., description="Section heading")
    summary: str = Field("", description="Brief summary paragraph for this section")
    bullet_points: list[ReportBulletPoint] = Field(default_factory=list)
    subsections: list[ReportSection] = Field(default_factory=list)
    source_comparisons: list[ComparisonResult] = Field(
        default_factory=list,
        description="Where sources agree or conflict in this section"
    )


class OpenQuestion(BaseModel):
    """An identified gap or unresolved question in the research."""
    question: str = Field(..., description="The open question")
    context: str = Field("", description="Why this question remains open")
    suggested_sources: list[str] = Field(
        default_factory=list,
        description="Suggested sources to resolve this question"
    )
    priority: str = Field("medium", description="high | medium | low")


class ResearchOutline(BaseModel):
    """The structured outline produced by the Planner Agent."""
    title: str
    objective: str
    sections: list[str] = Field(default_factory=list)
    key_questions: list[str] = Field(default_factory=list)
    search_strategy: str = ""


class ReportMetadata(BaseModel):
    """Metadata about the generated report."""
    report_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    research_prompt: str
    total_sources_consulted: int = 0
    total_facts_extracted: int = 0
    overall_confidence: float = Field(0.0, ge=0.0, le=1.0)
    generation_time_seconds: float = 0.0
    model_versions: dict = Field(default_factory=dict)
    revision_count: int = 0


class AgreementSummary(BaseModel):
    """Summary statistics of source agreement across the report."""
    total_comparisons: int = 0
    agreements: int = 0
    conflicts: int = 0
    partial_agreements: int = 0
    unique_claims: int = 0
    agreement_rate: float = Field(0.0, ge=0.0, le=1.0)


class ResearchReport(BaseModel):
    """The complete research report - the final output of the workflow."""
    metadata: ReportMetadata
    executive_summary: str = Field("", description="High-level summary of findings")
    sections: list[ReportSection] = Field(default_factory=list)
    source_agreement_summary: AgreementSummary = Field(default_factory=AgreementSummary)
    key_conflicts: list[ComparisonResult] = Field(
        default_factory=list,
        description="Highlighted conflicts between sources"
    )
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    all_citations: list[Citation] = Field(
        default_factory=list,
        description="Complete bibliography of all sources cited"
    )

    def to_markdown(self) -> str:
        """Convert the report to a formatted Markdown document."""
        lines = []
        lines.append(f"# {self.metadata.research_prompt}\n")
        lines.append(f"*Generated: {self.metadata.generated_at.strftime('%Y-%m-%d %H:%M UTC')}*  ")
        lines.append(f"*Sources consulted: {self.metadata.total_sources_consulted} | "
                      f"Facts extracted: {self.metadata.total_facts_extracted} | "
                      f"Confidence: {self.metadata.overall_confidence:.0%}*\n")

        # Executive Summary
        lines.append("## Executive Summary\n")
        lines.append(f"{self.executive_summary}\n")

        # Main Sections
        for section in self.sections:
            lines.append(f"## {section.title}\n")
            if section.summary:
                lines.append(f"{section.summary}\n")
            for bp in section.bullet_points:
                cite_refs = ", ".join(
                    f"[{c.source_name}]({c.url})" if c.url else f"[{c.source_name}]"
                    for c in bp.citations
                )
                cite_str = f" ({cite_refs})" if cite_refs else ""
                lines.append(f"- {bp.text}{cite_str}")

            # Source comparisons within section
            if section.source_comparisons:
                lines.append(f"\n### Source Analysis — {section.title}\n")
                for comp in section.source_comparisons:
                    icon = {"agree": "✅", "conflict": "⚠️", "partial": "🔶", "unique": "ℹ️"}.get(
                        comp.agreement_status.value, "•"
                    )
                    lines.append(f"- {icon} **{comp.topic}**: {comp.explanation}")
            lines.append("")

        # Key Conflicts
        if self.key_conflicts:
            lines.append("## ⚠️ Key Conflicts Between Sources\n")
            for conflict in self.key_conflicts:
                lines.append(f"### {conflict.topic}\n")
                lines.append(f"{conflict.explanation}\n")
                if conflict.supporting_facts:
                    lines.append("**Supporting:**")
                    for f in conflict.supporting_facts:
                        lines.append(f"- {f.claim}")
                if conflict.conflicting_facts:
                    lines.append("**Conflicting:**")
                    for f in conflict.conflicting_facts:
                        lines.append(f"- {f.claim}")
                lines.append("")

        # Source Agreement Summary
        lines.append("## 📊 Source Agreement Summary\n")
        s = self.source_agreement_summary
        lines.append(f"| Metric | Count |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total Comparisons | {s.total_comparisons} |")
        lines.append(f"| Agreements | {s.agreements} |")
        lines.append(f"| Conflicts | {s.conflicts} |")
        lines.append(f"| Partial Agreements | {s.partial_agreements} |")
        lines.append(f"| Unique Claims | {s.unique_claims} |")
        lines.append(f"| **Agreement Rate** | **{s.agreement_rate:.0%}** |")
        lines.append("")

        # Open Questions
        if self.open_questions:
            lines.append("## ❓ Open Questions\n")
            for q in self.open_questions:
                lines.append(f"### {q.question}\n")
                lines.append(f"{q.context}\n")
                if q.suggested_sources:
                    lines.append(f"*Suggested sources: {', '.join(q.suggested_sources)}*\n")

        # Bibliography
        lines.append("## 📚 Bibliography\n")
        for i, cite in enumerate(self.all_citations, 1):
            url_str = f" — [{cite.url}]({cite.url})" if cite.url else ""
            lines.append(f"{i}. **{cite.source_name}** [{cite.source_type.value}]{url_str}")

        return "\n".join(lines)

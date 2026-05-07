"""Models package for the Multi-Agent Research Workflow."""

from .source import (
    SourceType,
    Citation,
    ExtractedFact,
    SourceAgreement,
    ComparisonResult,
    SearchQuery,
    RawSourceData,
)
from .report import (
    ReportBulletPoint,
    ReportSection,
    OpenQuestion,
    ResearchOutline,
    ReportMetadata,
    AgreementSummary,
    ResearchReport,
)

__all__ = [
    "SourceType",
    "Citation",
    "ExtractedFact",
    "SourceAgreement",
    "ComparisonResult",
    "SearchQuery",
    "RawSourceData",
    "ReportBulletPoint",
    "ReportSection",
    "OpenQuestion",
    "ResearchOutline",
    "ReportMetadata",
    "AgreementSummary",
    "ResearchReport",
]

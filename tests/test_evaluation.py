"""
Tests for the evaluation harness — deterministic fixtures and scoring.
"""
import pytest
from evaluation import (
    get_fixture_outline,
    get_fixture_sources,
    get_fixture_facts,
    get_fixture_report,
    score_report,
    ReportScorecard,
)


# ══════════════════════════════════════════════════════════════════════
# Deterministic Fixture Tests
# ══════════════════════════════════════════════════════════════════════

class TestFixtures:
    """Verify deterministic fixtures produce repeatable, valid objects."""

    def test_fixture_outline_valid(self):
        outline = get_fixture_outline()
        assert outline.title == "AI Developer Tools Market Analysis 2026"
        assert len(outline.sections) == 4
        assert len(outline.key_questions) == 3

    def test_fixture_sources_valid(self):
        sources = get_fixture_sources()
        assert len(sources) == 2
        assert all(s.retrieval_status == "success" for s in sources)
        # Must have at least 2 distinct source types
        types = {s.source_type for s in sources}
        assert len(types) >= 2

    def test_fixture_facts_valid(self):
        facts = get_fixture_facts()
        assert len(facts) == 4
        assert all(f.confidence > 0.5 for f in facts)
        assert all(len(f.citations) >= 1 for f in facts)

    def test_fixture_facts_have_conflict(self):
        """Fixtures intentionally include a market size conflict."""
        facts = get_fixture_facts()
        market_facts = [f for f in facts if "market size" in f.claim.lower()]
        assert len(market_facts) == 2  # $15.2B vs $18.7B
        values = {f.raw_value for f in market_facts}
        assert "$15.2B" in values
        assert "$18.7B" in values

    def test_fixture_report_valid(self):
        report = get_fixture_report()
        assert report.metadata.report_id == "fixture-report-001"
        assert len(report.sections) >= 2
        assert len(report.all_citations) >= 1

    def test_fixture_report_has_open_questions(self):
        report = get_fixture_report()
        assert len(report.open_questions) >= 1

    def test_fixture_report_deterministic(self):
        """Two calls should return identical objects."""
        r1 = get_fixture_report()
        r2 = get_fixture_report()
        assert r1.metadata.report_id == r2.metadata.report_id
        assert len(r1.sections) == len(r2.sections)


# ══════════════════════════════════════════════════════════════════════
# Scoring Harness Tests
# ══════════════════════════════════════════════════════════════════════

class TestScoring:
    """Verify the scoring harness produces expected scores."""

    def test_fixture_report_passes(self):
        """The fixture report should score above 60%."""
        report = get_fixture_report()
        card = score_report(report)
        assert card.passed is True
        assert card.overall_score >= 60.0

    def test_structure_score_components(self):
        report = get_fixture_report()
        card = score_report(report)
        assert card.structure_score > 0
        assert "structure" in card.details

    def test_citation_score(self):
        report = get_fixture_report()
        card = score_report(report)
        assert card.citation_score > 0
        assert card.details["citations"]["cited_bullets"] > 0

    def test_coverage_score(self):
        report = get_fixture_report()
        card = score_report(report, expected_min_sections=2)
        assert card.coverage_score == 100.0

    def test_source_diversity_score(self):
        report = get_fixture_report()
        card = score_report(report)
        assert card.source_diversity_score > 0
        assert len(card.details["source_diversity"]["unique_types"]) >= 1

    def test_open_questions_score(self):
        report = get_fixture_report()
        card = score_report(report)
        assert card.open_questions_score > 0

    def test_scorecard_serializable(self):
        report = get_fixture_report()
        card = score_report(report)
        d = card.to_dict()
        assert isinstance(d["overall_score"], float)
        assert isinstance(d["passed"], bool)
        assert isinstance(d["details"], dict)

    def test_strict_threshold_fails(self):
        """With a very high threshold, the fixture should fail."""
        report = get_fixture_report()
        card = score_report(report, passing_threshold=99.0)
        assert card.passed is False

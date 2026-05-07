"""Tests for the Planner Agent."""
import pytest
from models.report import ResearchOutline
from models.source import SearchQuery, SourceType


def test_research_outline_creation():
    outline = ResearchOutline(
        title="Test Research",
        objective="Test objective",
        sections=["Section 1", "Section 2"],
        key_questions=["Q1?", "Q2?"],
    )
    assert outline.title == "Test Research"
    assert len(outline.sections) == 2


def test_search_query_validation():
    query = SearchQuery(
        query_text="test query",
        target_source=SourceType.WEB_API,
        priority=1,
        rationale="Testing",
    )
    assert query.priority >= 1
    assert query.priority <= 5


def test_search_query_priority_bounds():
    with pytest.raises(Exception):
        SearchQuery(query_text="test", target_source=SourceType.WEB_API, priority=0)

    with pytest.raises(Exception):
        SearchQuery(query_text="test", target_source=SourceType.WEB_API, priority=6)

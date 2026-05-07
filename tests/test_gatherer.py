"""Tests for the Gatherer Agent tools."""
from tools.web_search import _mock_web_results
from tools.document_loader import _mock_document_results


def test_mock_web_results():
    results = _mock_web_results("test query")
    assert len(results) == 2
    assert all("url" in r for r in results)
    assert all("content" in r for r in results)


def test_mock_document_results():
    results = _mock_document_results("test query")
    assert len(results) == 1
    assert "content" in results[0]

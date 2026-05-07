"""
Document loader tool for PDF and text document retrieval.
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


def load_documents(query: str, doc_paths: list[str] | None = None) -> list[dict]:
    """
    Load and search documents for relevant content.

    Args:
        query: Search query to match against documents.
        doc_paths: Optional list of file paths to search.

    Returns:
        List of dicts with keys: title, content, source, metadata.
    """
    try:
        if doc_paths:
            return _load_from_paths(doc_paths, query)
        return _mock_document_results(query)
    except Exception as e:
        logger.error("Document loading failed: %s", e)
        return []


def _load_from_paths(paths: list[str], query: str) -> list[dict]:
    """Load documents from file paths."""
    results = []
    for path in paths:
        try:
            if path.endswith(".pdf"):
                from pypdf import PdfReader
                reader = PdfReader(path)
                content = "\n".join(page.extract_text() or "" for page in reader.pages)
            else:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            results.append({
                "title": path.split("/")[-1],
                "content": content[:5000],
                "source": path,
                "metadata": {"file_path": path, "query": query},
            })
        except Exception as e:
            logger.warning("Failed to load %s: %s", path, e)
    return results


def _mock_document_results(query: str) -> list[dict]:
    """Mock document results for testing."""
    return [{
        "title": f"Document: {query[:40]}",
        "content": f"Mock document content related to {query}.",
        "source": "internal_documents",
        "metadata": {"type": "mock"},
    }]

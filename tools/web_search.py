"""
Web search tool using Tavily API.
Provides a unified interface for web-based information retrieval.
"""

from __future__ import annotations
import logging
from config import config

logger = logging.getLogger(__name__)


def search_web_tavily(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the web using Tavily API.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.

    Returns:
        List of dicts with keys: title, url, content, score.
    """
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=config.search.tavily_api_key)
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced",
            include_raw_content=False,
        )
        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0.0),
            })
        logger.info("Tavily search returned %d results for: %s", len(results), query[:60])
        return results
    except ImportError:
        logger.warning("Tavily not installed. Returning mock results.")
        return _mock_web_results(query)
    except Exception as e:
        logger.error("Tavily search failed: %s", e)
        return _mock_web_results(query)


def _mock_web_results(query: str) -> list[dict]:
    """Fallback mock results for testing without API keys."""
    return [
        {
            "title": f"Research: {query[:50]}",
            "url": "https://example.com/article-1",
            "content": f"Mock research content about {query}. This provides general data and statistics.",
            "score": 0.85,
        },
        {
            "title": f"Analysis: {query[:50]}",
            "url": "https://example.com/article-2",
            "content": f"Mock analysis about {query}. Contains comparative data from industry reports.",
            "score": 0.78,
        },
    ]

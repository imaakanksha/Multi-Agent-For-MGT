"""
Vector store integration using Azure AI Search.

Stores document embeddings for semantic retrieval during the
Gatherer stage, enabling RAG-style document search.
"""

from __future__ import annotations
import logging
from config import config

logger = logging.getLogger(__name__)


class AzureVectorStore:
    """
    Vector store backed by Azure AI Search for semantic document retrieval.

    Used by the Gatherer Agent to find relevant documents beyond
    keyword matching — especially useful for internal knowledge bases.
    """

    def __init__(self):
        self.client = None
        self._initialize()

    def _initialize(self):
        try:
            from azure.search.documents import SearchClient
            from azure.core.credentials import AzureKeyCredential
            self.client = SearchClient(
                endpoint=config.azure_search.endpoint,
                index_name=config.azure_search.index_name,
                credential=AzureKeyCredential(config.azure_search.key),
            )
            logger.info("Azure AI Search vector store initialized")
        except Exception as e:
            logger.warning("Azure AI Search not available: %s", e)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self.client:
            return []
        try:
            results = self.client.search(search_text=query, top=top_k)
            return [{"content": r.get("content", ""), "title": r.get("title", ""),
                      "url": r.get("url", "")} for r in results]
        except Exception as e:
            logger.error("Vector search failed: %s", e)
            return []

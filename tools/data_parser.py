"""
Data parser tool for structured/provided data sources.
"""

from __future__ import annotations
import json
import logging

logger = logging.getLogger(__name__)


def parse_provided_data(query: str, data_path: str | None = None) -> list[dict]:
    """
    Parse provided or structured data sources.

    Args:
        query: Context query for data relevance.
        data_path: Optional path to a JSON/CSV data file.

    Returns:
        List of dicts with keys: name, content, metadata.
    """
    if data_path:
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return [{
                "name": data_path.split("/")[-1],
                "content": json.dumps(raw, indent=2)[:5000],
                "metadata": {"source_path": data_path},
            }]
        except Exception as e:
            logger.error("Failed to parse data file %s: %s", data_path, e)
    return []

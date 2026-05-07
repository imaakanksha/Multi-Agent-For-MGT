"""
State checkpointer using Azure Cosmos DB.

Provides durable state persistence so workflows can be resumed
after crashes, and enables human-in-the-loop review patterns.

For local dev, falls back to in-memory checkpointing via LangGraph's MemorySaver.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime
from config import config

logger = logging.getLogger(__name__)


class CosmosDBCheckpointer:
    """
    Custom checkpointer that persists LangGraph state to Azure Cosmos DB.

    In production, this replaces MemorySaver to provide:
    - Crash recovery (resume from last checkpoint)
    - Audit trail (full state history)
    - Multi-instance coordination
    """

    def __init__(self):
        self.client = None
        self.container = None
        self._initialize()

    def _initialize(self):
        try:
            from azure.cosmos import CosmosClient
            self.client = CosmosClient(config.cosmos.endpoint, config.cosmos.key)
            db = self.client.get_database_client(config.cosmos.database)
            self.container = db.get_container_client(config.cosmos.container)
            logger.info("Cosmos DB checkpointer initialized")
        except Exception as e:
            logger.warning("Cosmos DB not available, using in-memory: %s", e)

    def save_checkpoint(self, thread_id: str, state: dict, step: int):
        if not self.container:
            return
        try:
            doc = {
                "id": f"{thread_id}_{step}",
                "thread_id": thread_id,
                "step": step,
                "state": json.dumps(state, default=str),
                "timestamp": datetime.utcnow().isoformat(),
            }
            self.container.upsert_item(doc)
        except Exception as e:
            logger.error("Checkpoint save failed: %s", e)

    def load_checkpoint(self, thread_id: str):
        if not self.container:
            return None
        try:
            query = (f"SELECT TOP 1 * FROM c WHERE c.thread_id = '{thread_id}' "
                     f"ORDER BY c.step DESC")
            items = list(self.container.query_items(query, enable_cross_partition_query=True))
            if items:
                return json.loads(items[0]["state"])
        except Exception as e:
            logger.error("Checkpoint load failed: %s", e)
        return None

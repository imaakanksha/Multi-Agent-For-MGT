"""
Configuration management for the Multi-Agent Research Workflow.
Loads environment variables and provides typed config access.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    """Configuration for LLM providers with model-tier strategy."""
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    model_planning: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL_PLANNING", "gpt-4o"))
    model_extraction: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL_EXTRACTION", "gpt-4o-mini"))
    model_writing: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL_WRITING", "gpt-4o"))


@dataclass
class SearchConfig:
    """Configuration for web search tools."""
    tavily_api_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))
    max_search_results: int = field(default_factory=lambda: int(os.getenv("MAX_SEARCH_RESULTS", "10")))


@dataclass
class AzureCosmosConfig:
    """Configuration for Azure Cosmos DB persistence."""
    endpoint: str = field(default_factory=lambda: os.getenv("AZURE_COSMOS_ENDPOINT", ""))
    key: str = field(default_factory=lambda: os.getenv("AZURE_COSMOS_KEY", ""))
    database: str = field(default_factory=lambda: os.getenv("AZURE_COSMOS_DATABASE", "research_agent_db"))
    container: str = field(default_factory=lambda: os.getenv("AZURE_COSMOS_CONTAINER", "workflow_state"))


@dataclass
class AzureSearchConfig:
    """Configuration for Azure AI Search vector store."""
    endpoint: str = field(default_factory=lambda: os.getenv("AZURE_SEARCH_ENDPOINT", ""))
    key: str = field(default_factory=lambda: os.getenv("AZURE_SEARCH_KEY", ""))
    index_name: str = field(default_factory=lambda: os.getenv("AZURE_SEARCH_INDEX", "research-documents"))


@dataclass
class AzureStorageConfig:
    """Configuration for Azure Table Storage & Queue Storage."""
    connection_string: str = field(default_factory=lambda: os.getenv("AZURE_STORAGE_CONNECTION_STRING", ""))
    table_name: str = field(default_factory=lambda: os.getenv("AZURE_TABLE_NAME", "workflowstate"))
    dead_letter_queue: str = field(default_factory=lambda: os.getenv("AZURE_DEAD_LETTER_QUEUE", "research-dead-letter"))


@dataclass
class WorkflowConfig:
    """Configuration for workflow behavior."""
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    confidence_threshold: float = field(default_factory=lambda: float(os.getenv("CONFIDENCE_THRESHOLD", "0.7")))
    max_revision_loops: int = field(default_factory=lambda: int(os.getenv("MAX_REVISION_LOOPS", "2")))


@dataclass
class AppConfig:
    """Root application configuration."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    cosmos: AzureCosmosConfig = field(default_factory=AzureCosmosConfig)
    azure_search: AzureSearchConfig = field(default_factory=AzureSearchConfig)
    azure_storage: AzureStorageConfig = field(default_factory=AzureStorageConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)


# Singleton config instance
config = AppConfig()

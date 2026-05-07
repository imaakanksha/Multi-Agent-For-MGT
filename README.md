# 🔬 Multi-Agent Research Report Generator (MGT)

A production-grade, multi-agent AI workflow for generating structured research reports from multiple sources. Built with **LangGraph** for orchestration, **Azure Cosmos DB** for state persistence, and **Azure AI Search** for vector-based retrieval.

## Architecture Overview

This system decomposes the research report generation task into five specialized agents orchestrated through a LangGraph `StateGraph`:

| Agent | Role |
|-------|------|
| **Planner Agent** | Analyzes the research prompt, generates a structured outline, and identifies search queries |
| **Gatherer Agent** | Executes parallel searches across multiple sources (Web APIs, document stores, provided data) |
| **Extractor Agent** | Extracts structured facts, claims, and data points from raw source material |
| **Comparator Agent** | Cross-references extracted facts to find agreements, conflicts, and gaps |
| **Writer Agent** | Synthesizes all findings into a polished, cited research report |

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables
cp .env.example .env
# Edit .env with your API keys

# 3. Run a sample research query
python main.py --prompt "Analyze the current market trend for AI-powered developer tools in 2026"
```

## Project Structure

```
Multi-Agent For MGT/
├── main.py                    # Entry point & CLI
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable template
├── config.py                  # Configuration management
├── docs/
│   ├── ARCHITECTURE.md        # Detailed architecture documentation
│   ├── AGENT_DETAILS.md       # Step-by-step agent explanations
│   └── BEST_PRACTICES.md      # Best practices & references
├── agents/
│   ├── __init__.py
│   ├── planner.py             # Planner Agent
│   ├── gatherer.py            # Gatherer Agent
│   ├── extractor.py           # Extractor Agent
│   ├── comparator.py          # Comparator Agent
│   └── writer.py              # Writer Agent
├── orchestration/
│   ├── __init__.py
│   ├── graph.py               # LangGraph StateGraph definition
│   ├── state.py               # Typed state schema
│   └── routing.py             # Conditional edge logic
├── persistence/
│   ├── __init__.py
│   ├── checkpointer.py        # State checkpointing (Azure Cosmos DB)
│   └── vector_store.py        # Vector store for document retrieval
├── tools/
│   ├── __init__.py
│   ├── web_search.py          # Web search tool (Tavily/Bing)
│   ├── document_loader.py     # Document/PDF loader
│   └── data_parser.py         # Structured data parser
├── models/
│   ├── __init__.py
│   ├── report.py              # Report Pydantic models
│   └── source.py              # Source & citation models
├── sample_output/
│   ├── sample_report.json     # Sample JSON report output
│   └── sample_report.md       # Sample formatted report
└── tests/
    ├── __init__.py
    ├── test_planner.py
    ├── test_gatherer.py
    └── test_workflow.py
```

## License

MIT

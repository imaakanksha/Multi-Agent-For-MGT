# Multi-Agent Research Report Generator

A production-grade, multi-agent AI workflow for generating structured research reports from multiple sources. Built with **LangGraph** for orchestration, **FastAPI** for the HTTP trigger, and a dual-stack persistence layer (Azure Table Storage or SQLite).

> **Cost:** Runs end-to-end locally at **$0** using Ollama + SQLite.
> Azure deployment uses free-tier/trial-credit components.

---

## Architecture

```
POST /research                    GET /dashboard
     │                                 │
     ▼                                 ▼
┌─────────────────────────────────────────────────┐
│              FastAPI HTTP Trigger                │
│  (guardrails: prompt injection + schema check)  │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│         LangGraph StateGraph Orchestration       │
│                                                  │
│  Planner → Gatherer → Extractor → Comparator     │
│                                        │         │
│                                        ▼         │
│                                     Writer ──────│──→ Finalize
│                                        │         │
│                                   if conf < 0.7  │
│                                        └─────────│──→ Comparator (reflection loop)
│                                                  │
│  Error Handler → Dead-Letter Queue               │
└────────────────────┬────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   SQLite/Azure   Tavily/Mock   Ollama/OpenAI
   (persistence)  (web search)  (LLM provider)
```

Five specialized agents, each using LLM-driven decision making:

| Agent | Role | LLM Decision |
|-------|------|-------------|
| **Planner** | Creates outline + search queries | Decides report structure, sections, query strategy |
| **Gatherer** | Retrieves data via tool selection | **LLM selects which tools** to invoke per query |
| **Extractor** | Extracts facts with confidence | Scores fact reliability, categorizes claims |
| **Comparator** | Finds agreement/conflict | Identifies cross-source agreement, gaps |
| **Writer** | Synthesizes final report | Determines section content, confidence drives routing |

---

## Quick Start

### Option A: Zero-Cost Local Stack (Ollama + SQLite)

**Total cost: $0.00** — No cloud accounts needed.

```bash
# 1. Install Ollama (https://ollama.com)
# Then pull a model:
ollama pull llama3.1

# 2. Install Python dependencies (minimal set)
pip install -r requirements-local.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — uncomment the "OPTION B" section:
#   OPENAI_API_BASE=http://localhost:11434/v1
#   OPENAI_API_KEY=ollama
#   OPENAI_MODEL_PLANNING=llama3.1
#   OPENAI_MODEL_EXTRACTION=llama3.1
#   OPENAI_MODEL_WRITING=llama3.1

# 4. Run a research query (CLI)
python main.py --prompt "Analyze AI developer tools market in 2026"

# 5. Or start the API server
python main.py --serve
# Dashboard: http://localhost:8000/dashboard
# API docs:  http://localhost:8000/docs
```

### Option B: Cloud Stack (Azure / OpenAI)

**Estimated cost: ~$0.10/run** (within Azure $200 trial credit).

```bash
# 1. Install all dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys:
#   OPENAI_API_KEY=sk-...
#   TAVILY_API_KEY=tvly-...
#   AZURE_STORAGE_CONNECTION_STRING=... (or leave empty for SQLite)

# 3. Run
python main.py --prompt "Analyze AI developer tools market in 2026"
```

---

## Technology Stack Mapping

Every architectural requirement is satisfied with both Azure and open-source equivalents:

| Component | Azure Stack | Local Stack (Zero-Cost) |
|-----------|------------|------------------------|
| **HTTP Trigger** | Azure Functions / FastAPI | FastAPI (`uvicorn`) |
| **LLM Provider** | Azure OpenAI (GPT-4o) | Ollama (Llama 3.1) / LM Studio |
| **State Persistence** | Azure Table Storage | SQLite (`data/workflow_state.db`) |
| **Dead-Letter Queue** | Azure Queue Storage | SQLite (`data/dead_letter.db`) |
| **Web Search** | Tavily API (1000 free/month) | Mock results (built-in) |
| **Checkpointing** | Azure Cosmos DB | In-memory (`MemorySaver`) |
| **Vector Store** | Azure AI Search | Local document loader |
| **Monitoring** | Application Insights | Built-in HTML dashboard (`/dashboard`) |

### Automatic Fallback Logic

The system **auto-detects** available services and falls back gracefully:

```python
# config.py — LLMConfig auto-detects provider:
if OPENAI_API_BASE contains "localhost" → provider = "ollama"
if OPENAI_API_BASE contains "azure"    → provider = "azure_openai"
if OPENAI_API_BASE is empty            → provider = "openai"

# persistence/state_store.py — auto-detects storage:
if AZURE_STORAGE_CONNECTION_STRING set → Azure Table Storage
else                                  → SQLite (./data/workflow_state.db)

# persistence/dead_letter.py — auto-detects queue:
if AZURE_STORAGE_CONNECTION_STRING set → Azure Queue Storage
else                                  → SQLite (./data/dead_letter.db)

# tools/web_search.py — auto-detects search:
if TAVILY_API_KEY set → Tavily Search API
else                  → Mock results (built-in)
```

---

## API Endpoints

Start the server: `python main.py --serve`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/research` | Submit research workflow (async) |
| `GET` | `/research/{id}` | Poll workflow status |
| `GET` | `/research/{id}/report` | Get completed report |
| `GET` | `/research/{id}/history` | Stage transition audit trail |
| `GET` | `/workflows` | List recent workflows |
| `GET` | `/dead-letter` | List dead-lettered workflows |
| `POST` | `/dead-letter/{id}/replay` | Replay a failed workflow |
| `GET` | `/dashboard` | Monitoring dashboard (HTML) |
| `GET` | `/dashboard/metrics` | Dashboard metrics (JSON) |
| `POST` | `/validate` | Pre-flight guardrail check |
| `GET` | `/health` | Health check |

---

## Running Tests

```bash
python -m pytest tests/ -v
# 55 tests: guardrails, evaluation, persistence, workflow, planner, gatherer
```

---

## Project Structure

```
Multi-Agent For MGT/
├── main.py                    # Entry point: CLI + API server
├── config.py                  # Typed config with Ollama/Azure detection
├── requirements.txt           # Full dependencies (Azure + cloud)
├── requirements-local.txt     # Minimal dependencies (zero-cost)
├── .env.example               # Dual-stack env template
│
├── agents/                    # 5 LLM-powered agents
│   ├── planner.py             # Outline + query generation
│   ├── gatherer.py            # LLM-driven tool selection
│   ├── extractor.py           # Fact extraction + guardrails
│   ├── comparator.py          # Cross-source comparison
│   └── writer.py              # Report synthesis
│
├── orchestration/             # LangGraph workflow engine
│   ├── graph.py               # StateGraph with tracking wrappers
│   ├── state.py               # TypedDict with reducers
│   ├── routing.py             # Confidence branching + backoff
│   └── correlation.py         # Correlation ID + WorkflowTracker
│
├── api/
│   └── server.py              # FastAPI (15 routes)
│
├── persistence/               # Durable state (Azure / SQLite)
│   ├── state_store.py         # Azure Table Storage / SQLite
│   ├── dead_letter.py         # DLQ with replay capability
│   ├── checkpointer.py        # Cosmos DB checkpointer
│   └── vector_store.py        # Azure AI Search
│
├── guardrails/                # Input/output safety
│   └── __init__.py            # Injection + schema + refusal
│
├── monitoring/                # Observability
│   └── dashboard.py           # Live HTML dashboard
│
├── evaluation/                # Quality assurance
│   └── __init__.py            # Fixtures + scoring harness
│
├── tools/                     # External tool integrations
│   ├── web_search.py          # Tavily / mock fallback
│   ├── document_loader.py     # Document retrieval
│   └── data_parser.py         # Structured data parsing
│
├── models/                    # Pydantic schemas
│   ├── report.py              # Report + Markdown renderer
│   └── source.py              # Facts, citations, comparisons
│
├── docs/                      # Documentation
│   ├── ARCHITECTURE.md        # System architecture
│   ├── AGENT_DETAILS.md       # Agent step-by-step
│   ├── BEST_PRACTICES.md      # Design references
│   ├── LLM_INTEGRATION.md     # Prompts, sample I/O, confidence
│   └── DEPLOYMENT.md          # Deployment guide
│
├── sample_output/             # Example outputs
│   ├── sample_report.json     # Full JSON report
│   └── sample_report.md       # Formatted Markdown report
│
└── tests/                     # 55 tests
    ├── test_evaluation.py     # Fixtures + scoring (15)
    ├── test_guardrails.py     # Injection + schema (16)
    ├── test_persistence.py    # State + DLQ (7)
    ├── test_workflow.py       # State management (6)
    ├── test_planner.py        # Outline validation (3)
    └── test_gatherer.py       # Source retrieval (2)
```

---

## Documentation

| Document | Contents |
|----------|----------|
| [LLM_INTEGRATION.md](docs/LLM_INTEGRATION.md) | All prompt templates, sample LLM I/O, confidence flow, token costs |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture and design decisions |
| [AGENT_DETAILS.md](docs/AGENT_DETAILS.md) | Step-by-step agent behavior |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Azure Functions + Docker deployment |
| [BEST_PRACTICES.md](docs/BEST_PRACTICES.md) | LangGraph patterns and references |

## License

MIT

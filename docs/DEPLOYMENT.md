# Deployment Guide

## Option 1: Zero-Cost Local Deployment (Ollama + SQLite)

**Total cost: $0.00** — No cloud accounts, no API keys, fully offline.

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com/) installed locally

### Steps

```bash
# 1. Pull an LLM model (one-time download, ~4GB)
ollama pull llama3.1
# Alternative smaller models:
# ollama pull mistral        (~4GB, good quality)
# ollama pull phi3            (~2GB, fastest)

# 2. Verify Ollama is running
curl http://localhost:11434/v1/models
# Should return a list of available models

# 3. Install minimal Python dependencies
pip install -r requirements-local.txt

# 4. Create .env from template
cp .env.example .env

# 5. Edit .env — set these values:
# OPENAI_API_BASE=http://localhost:11434/v1
# OPENAI_API_KEY=ollama
# OPENAI_MODEL_PLANNING=llama3.1
# OPENAI_MODEL_EXTRACTION=llama3.1
# OPENAI_MODEL_WRITING=llama3.1
# (Leave all AZURE_* and TAVILY_* variables empty)

# 6. Run tests
python -m pytest tests/ -v
# Expected: 55 passed

# 7. Run a research workflow
python main.py --prompt "Compare cloud computing providers in 2026"

# 8. Or start the API server
python main.py --serve
# Dashboard: http://localhost:8000/dashboard
# API docs:  http://localhost:8000/docs
```

### What Happens Without API Keys

| Service | Behavior |
|---------|----------|
| `OPENAI_API_KEY` empty + `OPENAI_API_BASE` empty | LLM calls fail; use Ollama instead |
| `OPENAI_API_BASE=http://localhost:11434/v1` | Routes to local Ollama — **$0 cost** |
| `TAVILY_API_KEY` empty | Web search returns built-in mock results |
| `AZURE_STORAGE_CONNECTION_STRING` empty | State persists to SQLite (`data/workflow_state.db`) |
| `AZURE_COSMOS_ENDPOINT` empty | Checkpointing uses in-memory `MemorySaver` |

### Component Mapping

```
┌──────────────────────────────────────────────────┐
│              LOCAL STACK ($0)                     │
│                                                   │
│  Trigger:      FastAPI + uvicorn                 │
│  LLM:          Ollama (llama3.1 / mistral)       │
│  Persistence:  SQLite  (data/workflow_state.db)  │
│  Dead-Letter:  SQLite  (data/dead_letter.db)     │
│  Checkpoint:   In-memory (MemorySaver)           │
│  Web Search:   Mock results (built-in)           │
│  Dashboard:    Built-in HTML (/dashboard)        │
│  Monitoring:   Console logs                      │
└──────────────────────────────────────────────────┘
```

---

## Option 2: Azure Deployment (Free Tier / Trial Credits)

**Estimated cost: ~$0.10/run** — within Azure $200 trial credit.

### Azure Services Used

| Service | Tier | Monthly Cost |
|---------|------|-------------|
| Azure Functions (Consumption) | Free grant: 1M exec/month | **$0** |
| Azure Table Storage | Free: 1GB included | **$0** |
| Azure Queue Storage | Free: 10K ops included | **$0** |
| Azure OpenAI (GPT-4o) | Pay-per-token | ~$0.10/run |
| Azure Cosmos DB (optional) | Free tier: 1000 RU/s | **$0** |
| Azure AI Search (optional) | Free tier: 50MB | **$0** |

**Total for ~100 runs/month: ~$10** (well within $200 trial credit).

### Steps

```bash
# 1. Install full dependencies
pip install -r requirements.txt

# 2. Create Azure resources (one-time setup)
az login
az group create --name research-agent-rg --location eastus

# Storage Account (Table Storage + Queue)
az storage account create \
    --name researchagentstore \
    --resource-group research-agent-rg \
    --sku Standard_LRS

# Get connection string
az storage account show-connection-string \
    --name researchagentstore \
    --query connectionString -o tsv

# 3. Configure .env
# OPENAI_API_KEY=sk-...
# AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
# TAVILY_API_KEY=tvly-... (free: 1000 searches/month)

# 4. Run
python main.py --serve
```

### Azure Functions Deployment

```bash
# Install Azure Functions Core Tools
npm install -g azure-functions-core-tools@4

# Create function app
az functionapp create \
    --name research-agent-func \
    --resource-group research-agent-rg \
    --storage-account researchagentstore \
    --consumption-plan-location eastus \
    --runtime python --runtime-version 3.11

# Deploy
func azure functionapp publish research-agent-func
```

### Docker Deployment

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t research-agent .
docker run -p 8000:8000 --env-file .env research-agent
```

---

## Cost Optimization Tips

1. **Use GPT-4o-mini** for Gatherer tool selection and Extractor (3x cheaper)
2. **Truncate sources** to 8000 chars max (already implemented)
3. **Cache Tavily results** for development (mock fallback built-in)
4. **Use Ollama locally** for development/testing ($0)
5. **Set `MAX_REVISION_LOOPS=1`** to reduce Writer re-runs
6. **Azure Functions Consumption plan** includes 1M free executions/month

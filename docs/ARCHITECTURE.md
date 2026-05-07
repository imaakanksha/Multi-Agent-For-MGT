# 🏗️ Architecture Documentation

## System Architecture Overview

This multi-agent research workflow follows a **Supervisor with Reflection Loop** architecture pattern, built on top of LangGraph's `StateGraph` for stateful, cyclic orchestration.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER / TRIGGER LAYER                         │
│  CLI (main.py) │ API Endpoint │ Scheduled Job │ Azure Function      │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ research_prompt
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     ORCHESTRATION LAYER (LangGraph)                  │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌───────────┐    ┌────────────┐   │
│  │ PLANNER  │───▶│ GATHERER │───▶│ EXTRACTOR │───▶│ COMPARATOR │   │
│  │  Agent   │    │  Agent   │    │   Agent   │    │   Agent    │   │
│  └──────────┘    └──────────┘    └───────────┘    └─────┬──────┘   │
│       │               │                                  │          │
│       │ retry         │ retry                            ▼          │
│       ▲               ▲                           ┌──────────┐     │
│       │               │              ◄─ reflect ──│  WRITER  │     │
│       └───────────────┘──── error ──▶│ ERROR     ││  Agent   │     │
│                              handler ││ HANDLER  │└────┬─────┘     │
│                                      │└──────────┘     │           │
│                                      │                 ▼           │
│                                      │          ┌──────────┐       │
│                                      └─────────▶│ FINALIZE │       │
│                                                 └────┬─────┘       │
│                                                      │              │
│  ┌───────────────── SHARED STATE (TypedDict) ────────┼──────────┐  │
│  │ research_prompt │ outline │ search_queries │       │          │  │
│  │ raw_sources │ extracted_facts │ comparisons │      │          │  │
│  │ open_questions │ final_report │ error_log   │      │          │  │
│  └────────────────────────────────────────────────────┘          │  │
└───────────────────────────────────────┬─────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
           ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
           │  Azure       │   │  Azure AI    │   │  LangSmith   │
           │  Cosmos DB   │   │  Search      │   │  Tracing     │
           │  (State)     │   │  (Vectors)   │   │  (Observe)   │
           └──────────────┘   └──────────────┘   └──────────────┘
```

---

## Component Details

### 1. Trigger Layer
| Trigger | Description |
|---------|-------------|
| **CLI** | `python main.py --prompt "..."` for interactive use |
| **API Endpoint** | REST/gRPC endpoint for programmatic access |
| **Scheduled Job** | Cron/Azure Timer Trigger for periodic research |
| **Azure Function** | Event-driven invocation from Azure services |

### 2. Orchestration Layer (LangGraph StateGraph)

The orchestration layer is the **core of the system**. It:
- Defines the graph topology (which agent runs after which)
- Manages shared state with typed schemas and reducer functions
- Implements conditional routing for retries and reflection loops
- Provides checkpointing for crash recovery

**Key Design Decisions:**
- **Supervisor Pattern**: A linear pipeline with conditional edges, not a free-form agent network. This provides predictability and debuggability.
- **Reflection Loop**: The Writer → Comparator loop allows iterative quality improvement without human intervention.
- **Graceful Degradation**: Every error path leads to `finalize`, ensuring partial output is always produced.

### 3. Shared State

The `ResearchState` TypedDict serves as a "shared whiteboard" that all agents read from and write to. Key fields:

```python
class ResearchState(TypedDict):
    research_prompt: str           # Input
    outline: ResearchOutline       # Planner output
    search_queries: list[SearchQuery]  # Planner output
    raw_sources: list[RawSourceData]   # Gatherer output
    extracted_facts: list[ExtractedFact]  # Extractor output
    comparisons: list[ComparisonResult]   # Comparator output
    final_report: ResearchReport   # Writer output
    # ... control flow fields
```

**Reducer Functions** prevent data loss when multiple agents update the same list field:
- `merge_lists`: Appends new items (used for facts, sources, errors)
- `replace_value`: Last-write-wins (used for scalar fields like status)

### 4. Persistence Layer

| Store | Purpose | Technology |
|-------|---------|------------|
| **State Checkpoints** | Crash recovery, audit trail | Azure Cosmos DB |
| **Vector Store** | Semantic document retrieval | Azure AI Search |
| **Observability** | Tracing, debugging, monitoring | LangSmith |

### 5. Agent Communication

Agents communicate **exclusively through the shared state**. There is no direct agent-to-agent messaging. This design:
- Eliminates coupling between agents
- Makes each agent independently testable
- Enables adding/removing agents without changing others
- Provides a complete audit trail in the state

---

## Data Flow

```
1. User submits prompt
   │
2. Planner Agent
   ├── Reads: research_prompt
   └── Writes: outline, search_queries
   │
3. Gatherer Agent
   ├── Reads: search_queries
   └── Writes: raw_sources
   │
4. Extractor Agent
   ├── Reads: raw_sources, outline.sections
   └── Writes: extracted_facts
   │
5. Comparator Agent
   ├── Reads: extracted_facts
   └── Writes: comparisons, open_questions
   │
6. Writer Agent
   ├── Reads: outline, extracted_facts, comparisons, open_questions
   └── Writes: final_report
   │
7. [If confidence < threshold] → Back to step 5
   │
8. Finalize → Output report (JSON + Markdown)
```

---

## Model Strategy

| Agent | Model | Rationale |
|-------|-------|-----------|
| Planner | GPT-4o | Complex reasoning for outline generation |
| Gatherer | N/A (tool-based) | No LLM needed — uses search APIs directly |
| Extractor | GPT-4o-mini | High-volume, focused task — cost optimization |
| Comparator | GPT-4o | Nuanced reasoning for conflict detection |
| Writer | GPT-4o | High-quality synthesis and writing |

This **hybrid model strategy** reduces costs by 40-60% compared to using a frontier model for all stages, while maintaining output quality where it matters most.

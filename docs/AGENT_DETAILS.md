# 🤖 Agent Details — Step-by-Step Explanations

This document explains how each agent works in detail, including its inputs, processing logic, outputs, and error handling.

---

## Agent 1: Planner Agent (`agents/planner.py`)

### Purpose
Analyzes the raw research prompt and creates a structured research plan before any data gathering begins.

### Why Planning First?
Without a plan, gatherer agents tend to retrieve too much irrelevant information or miss critical perspectives. The **planning-first pattern** is a best practice from Google DeepMind's agent research, ensuring that downstream agents have clear, focused objectives.

### Step-by-Step Process

```
┌──────────────────────────────────────────────────┐
│  INPUT: research_prompt (string)                 │
└──────────────────────┬───────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  1. Initialize GPT-4o     │
         │     (temperature=0.3)     │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  2. Send system prompt +  │
         │     research prompt       │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  3. Parse JSON response   │
         │     into typed models     │
         └─────────────┬─────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  OUTPUT:                                         │
│  - ResearchOutline (title, sections, questions)  │
│  - list[SearchQuery] (4+ queries, 2+ types)      │
└──────────────────────────────────────────────────┘
```

### Key Design Choices
- **Low temperature (0.3)**: Planning needs consistency, not creativity
- **JSON mode**: Forces structured output from the LLM
- **Multiple query types**: Ensures diversity in source types (web, documents, data)
- **Priority ranking**: Allows gatherer to focus on most important queries first

### Error Handling
- JSON parse failures → increment `retry_count`, try again
- LLM API failures → increment `retry_count`, try again
- Max retries exceeded → route to `error_handler`

---

## Agent 2: Gatherer Agent (`agents/gatherer.py`)

### Purpose
Executes search queries across multiple source types and collects raw material for extraction.

### Step-by-Step Process

```
┌──────────────────────────────────────────────────┐
│  INPUT: list[SearchQuery]                        │
└──────────────────────┬───────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  1. Sort queries by       │
         │     priority (1=highest)  │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  2. Dispatch to source    │
         │     type handler:         │
         │     web_api → Tavily      │
         │     document → PDF/loader │
         │     provided → parser     │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  3. Wrap results in       │
         │     RawSourceData objects  │
         │     with status tracking  │
         └─────────────┬─────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  OUTPUT: list[RawSourceData]                     │
│  (each with retrieval_status: success|failed)    │
└──────────────────────────────────────────────────┘
```

### Key Design Choices
- **Dispatch table pattern**: Clean separation of source-type logic
- **Priority sorting**: Most important queries execute first
- **Fault tolerance**: Each source retrieval is independently wrapped in try/except
- **Status tracking**: Failed retrievals are logged but don't halt the pipeline

### Error Handling
- Individual source failures → logged, marked as `failed`, pipeline continues
- ALL sources fail → route to `error_handler` or retry
- Partial results → proceed with available data (graceful degradation)

---

## Agent 3: Extractor Agent (`agents/extractor.py`)

### Purpose
Processes raw source content and extracts discrete, structured facts with confidence scoring.

### Step-by-Step Process

```
┌──────────────────────────────────────────────────┐
│  INPUT: list[RawSourceData] + outline sections   │
└──────────────────────┬───────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  1. Initialize GPT-4o-mini│
         │     (temperature=0.1)     │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  2. For EACH source:      │
         │     - Truncate to 8K chars│
         │     - Send to LLM with    │
         │       extraction prompt   │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  3. Parse facts, attach   │
         │     Citation objects      │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  4. Filter: remove facts  │
         │     with confidence < 0.3 │
         └─────────────┬─────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  OUTPUT: list[ExtractedFact]                     │
│  (each with claim, category, confidence, cite)   │
└──────────────────────────────────────────────────┘
```

### Key Design Choices
- **GPT-4o-mini**: Cost optimization — extraction is a focused, repetitive task
- **Very low temperature (0.1)**: Factual accuracy over creativity
- **Content truncation**: Prevents token limit overflow
- **Confidence threshold**: Filters noise from low-quality extractions
- **Category mapping**: Each fact is categorized to match outline sections

---

## Agent 4: Comparator Agent (`agents/comparator.py`)

### Purpose
Cross-references facts from multiple sources to identify where they agree, conflict, partially overlap, or are unique.

### Step-by-Step Process

```
┌──────────────────────────────────────────────────┐
│  INPUT: list[ExtractedFact]                      │
└──────────────────────┬───────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  1. Group facts by        │
         │     category              │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  2. For EACH category:    │
         │     - Format all facts    │
         │     - Send to GPT-4o for  │
         │       comparison          │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  3. Parse comparison       │
         │     results with status:  │
         │     agree|conflict|       │
         │     partial|unique        │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  4. Identify open         │
         │     questions (gaps)      │
         └─────────────┬─────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  OUTPUT:                                         │
│  - list[ComparisonResult] (agreements/conflicts) │
│  - list[OpenQuestion] (identified gaps)          │
└──────────────────────────────────────────────────┘
```

### Key Design Choices
- **GPT-4o**: Nuanced reasoning needed to detect subtle conflicts
- **Category grouping**: Only compare facts within the same topic area
- **Fact ID linking**: Comparisons reference specific facts by ID for traceability
- **Open question detection**: Actively identifies what the research couldn't answer

---

## Agent 5: Writer Agent (`agents/writer.py`)

### Purpose
Synthesizes all findings into a polished, structured research report with sections, citations, and metadata.

### Step-by-Step Process

```
┌──────────────────────────────────────────────────┐
│  INPUT: outline + facts + comparisons + questions│
└──────────────────────┬───────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  1. Build comprehensive   │
         │     context string        │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  2. Send to GPT-4o for    │
         │     report synthesis      │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  3. Parse into typed      │
         │     report model          │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  4. Calculate metadata:   │
         │     - Agreement summary   │
         │     - Overall confidence  │
         │     - Citation index      │
         └─────────────┬─────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  5. Quality check:        │
         │     confidence >= 0.7?    │
         │     YES → finalize        │
         │     NO → reflection loop  │
         └─────────────┬─────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  OUTPUT: ResearchReport                          │
│  (sections, citations, conflicts, questions)     │
└──────────────────────────────────────────────────┘
```

### The Reflection Loop
If the overall confidence score falls below the configured threshold (default: 0.7), the workflow routes back to the Comparator for re-analysis, then to the Writer for a revision. This cycle can repeat up to `MAX_REVISION_LOOPS` (default: 2) times, implementing the **Critic/Reflection pattern** from LangGraph best practices.

```
Writer (conf < 0.7) → Comparator → Writer (revision) → ... → Finalize
```

---

## Inter-Agent Communication Summary

| From | To | Data Passed (via State) |
|------|----|------------------------|
| User | Planner | `research_prompt` |
| Planner | Gatherer | `outline`, `search_queries` |
| Gatherer | Extractor | `raw_sources` |
| Extractor | Comparator | `extracted_facts` |
| Comparator | Writer | `comparisons`, `open_questions` |
| Writer | Output | `final_report` |
| Writer | Comparator | *(reflection loop if confidence low)* |

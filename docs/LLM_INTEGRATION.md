# AI / LLM Integration — Prompts, Sample I/O, and Confidence Logic

> This document satisfies the three mandatory AI documentation requirements:
> 1. **All prompt templates** used across the workflow
> 2. **Example model input/output** for at least 1 full run
> 3. **Where confidence is computed** and how it changes flow behavior

---

## Table of Contents

- [LLM Provider Configuration](#llm-provider-configuration)
- [Prompt Templates (All 5 Agents)](#prompt-templates)
- [Sample Run Trace — Full LLM I/O](#sample-run-trace)
- [Confidence Computation and Flow Impact](#confidence-computation-and-flow-impact)
- [Estimated Token Spend](#estimated-token-spend)

---

## LLM Provider Configuration

Configured in [`config.py`](../config.py) via environment variables:

```python
@dataclass
class LLMConfig:
    api_key: str         # OPENAI_API_KEY
    model_planning: str  # "gpt-4o" — high-capability for structured planning
    model_extraction: str # "gpt-4o-mini" — cost-efficient for bulk extraction
    model_writing: str   # "gpt-4o" — high-capability for final synthesis
```

**Supported providers:**
- Azure OpenAI (set `OPENAI_API_BASE` + deployment name)
- OpenAI API directly
- Local/open-source via Ollama (`OPENAI_API_BASE=http://localhost:11434/v1`)
- LM Studio local API server

**Cost strategy:** Planner and Writer use GPT-4o (higher quality); Gatherer tool-selection and Extractor use GPT-4o-mini (3x cheaper per token).

---

## Prompt Templates

### 1. Planner Agent — `PLANNER_SYSTEM_PROMPT`

> **File:** [`agents/planner.py`](../agents/planner.py) | **Model:** `gpt-4o` | **Temp:** 0.3

```text
You are a Research Planner Agent. Your job is to analyze a research prompt
and create a structured research plan.

Given a research prompt, you must produce a JSON response with the following structure:

{
    "title": "A concise, descriptive title for the research report",
    "objective": "A clear 1-2 sentence statement of what this research aims to discover",
    "sections": ["Section 1 Title", "Section 2 Title", ...],
    "key_questions": ["Question 1...", "Question 2..."],
    "search_strategy": "Brief description of the search approach",
    "search_queries": [
        {
            "query_text": "Specific search query optimized for web search",
            "target_source": "web_api",
            "priority": 1,
            "rationale": "Why this query is important"
        }
    ]
}

RULES:
- Generate at least 4 search queries targeting at least 2 different source types
- Each section should represent a distinct aspect of the research topic
- Prioritize queries (1=most important, 5=least important)
- ONLY output valid JSON.
```

**LLM Decision:** The model decides report structure, which sections to create, and which search queries to generate — directly determining the entire downstream workflow path.

---

### 2. Gatherer Agent — `TOOL_SELECTOR_PROMPT` (LLM-driven tool selection)

> **File:** [`agents/gatherer.py`](../agents/gatherer.py) | **Model:** `gpt-4o-mini` | **Temp:** 0.1

```text
You are a Tool Selection Agent. Given a research query, decide which retrieval
tool(s) to use and how to optimize the query for each.

Available tools:
1. "web_search" — Best for: recent events, market data, company news, trends
2. "document_search" — Best for: academic papers, whitepapers, technical docs
3. "data_parse" — Best for: numerical analysis, data tables, provided datasets

Return JSON:
{
    "tool_decisions": [
        {
            "tool_name": "web_search",
            "optimized_query": "Refined query optimized for this tool",
            "reasoning": "Why this tool is best for this query",
            "priority": 1,
            "expected_value": "high"
        }
    ]
}

Rules:
- Choose 1-3 tools per query based on what would yield the BEST results
- Rephrase queries to match each tool's strengths
- "expected_value" is "high", "medium", or "low" — skip "low" value tools
- ONLY output valid JSON.
```

**LLM Decision:** The model selects which tools to invoke and rephrases queries for each tool — this is **tool selection based on context**, not just text generation.

---

### 3. Extractor Agent — `EXTRACTOR_SYSTEM_PROMPT`

> **File:** [`agents/extractor.py`](../agents/extractor.py) | **Model:** `gpt-4o-mini` | **Temp:** 0.1

```text
You are a Fact Extraction Agent. Extract discrete factual claims from source material.

Return JSON:
{
    "facts": [
        {
            "claim": "A specific, verifiable factual statement",
            "category": "Category matching the research outline section",
            "confidence": 0.85,
            "is_quantitative": true,
            "raw_value": "$4.2B"
        }
    ]
}

Rules:
- Extract 3-10 facts per source
- Only include verifiable factual claims, not opinions
- Confidence 0.0-1.0 based on source reliability and specificity
- Mark claims with numbers/percentages as is_quantitative=true
- ONLY output valid JSON.
```

**LLM Decision:** The model decides which statements are factual, assigns confidence scores, and categorizes claims — these confidence values directly flow into the Writer's overall confidence and the routing decision.

---

### 4. Comparator Agent — `COMPARATOR_SYSTEM_PROMPT`

> **File:** [`agents/comparator.py`](../agents/comparator.py) | **Model:** `gpt-4o` | **Temp:** 0.2

```text
You are a Source Comparison Agent. Compare facts from multiple sources to find
agreements and conflicts.

Given facts grouped by category, return JSON:
{
    "comparisons": [
        {
            "topic": "The claim being compared",
            "agreement_status": "agree|conflict|partial|unique",
            "supporting_fact_ids": ["id1", "id2"],
            "conflicting_fact_ids": ["id3"],
            "explanation": "Why sources agree or conflict",
            "confidence": 0.8
        }
    ],
    "open_questions": [
        {
            "question": "What remains unanswered?",
            "context": "Why this is unresolved",
            "priority": "high|medium|low"
        }
    ]
}
```

**LLM Decision:** The model identifies cross-source agreement/conflict, assigns comparison confidence, and flags research gaps.

---

### 5. Writer Agent — `WRITER_SYSTEM_PROMPT`

> **File:** [`agents/writer.py`](../agents/writer.py) | **Model:** `gpt-4o` | **Temp:** 0.4

```text
You are a Research Report Writer Agent. Synthesize research findings into a
structured report.

Given an outline, extracted facts, and source comparisons, produce JSON:
{
    "executive_summary": "2-3 paragraph summary of key findings",
    "sections": [
        {
            "title": "Section Title",
            "summary": "Brief section summary",
            "bullet_points": [
                {"text": "Key finding with data", "citation_sources": ["Source Name"]}
            ]
        }
    ]
}

Rules:
- Every bullet point should cite its source
- Highlight where sources agree or conflict
- Be specific with numbers and data
- ONLY output valid JSON
```

**LLM Decision:** The model synthesizes all upstream data into the final report. The computed confidence score determines whether the workflow finalizes or loops back for revision.

---

## Sample Run Trace

Full input/output for one research workflow execution with prompt:
**"Analyze the current market trend for AI-powered developer tools in 2026"**

### Stage 1: Planner

**Model Input (User message):**
```
Research Prompt: Analyze the current market trend for AI-powered developer tools in 2026
```

**Model Output (JSON):**
```json
{
    "title": "AI Developer Tools Market Analysis 2026",
    "objective": "Analyze market size, competitive landscape, productivity impact, and future trends in AI-powered developer tools",
    "sections": [
        "Market Size & Growth",
        "Competitive Landscape",
        "Productivity Impact & ROI",
        "Emerging Trends & Future Outlook"
    ],
    "key_questions": [
        "What is the total addressable market for AI dev tools in 2026?",
        "Who are the top 3 players by market share?",
        "What productivity gains do enterprises report from AI coding tools?",
        "What emerging trends will shape the market in 2027-2030?"
    ],
    "search_strategy": "Multi-source: combine analyst reports with developer surveys and company announcements",
    "search_queries": [
        {
            "query_text": "AI developer tools market size 2026 growth rate",
            "target_source": "web_api",
            "priority": 1,
            "rationale": "Core market data from analyst reports"
        },
        {
            "query_text": "GitHub Copilot Cursor CodeWhisperer market share comparison 2026",
            "target_source": "web_api",
            "priority": 1,
            "rationale": "Competitive landscape data"
        },
        {
            "query_text": "AI coding assistant productivity impact enterprise ROI study",
            "target_source": "document",
            "priority": 2,
            "rationale": "Academic/research evidence for productivity claims"
        },
        {
            "query_text": "agentic coding AI developer tools trends 2026 2027",
            "target_source": "web_api",
            "priority": 2,
            "rationale": "Forward-looking trend analysis"
        },
        {
            "query_text": "developer survey AI tools adoption rate 2026",
            "target_source": "web_api",
            "priority": 3,
            "rationale": "Developer sentiment and adoption data"
        }
    ]
}
```

**Routing decision:** Outline is not None and search_queries is not empty => **route to gatherer**.

---

### Stage 2: Gatherer (LLM Tool Selection)

For query #1 ("AI developer tools market size 2026 growth rate"):

**Model Input:**
```
Query: AI developer tools market size 2026 growth rate
Target source type hint: web_api
Priority: 1
Rationale: Core market data from analyst reports
```

**Model Output (JSON):**
```json
{
    "tool_decisions": [
        {
            "tool_name": "web_search",
            "optimized_query": "AI developer tools market size revenue 2026 Gartner IDC forecast",
            "reasoning": "Market size data requires current analyst reports best found via web search. Added specific analyst firm names for higher relevance.",
            "priority": 1,
            "expected_value": "high"
        },
        {
            "tool_name": "document_search",
            "optimized_query": "global AI software development tools market analysis growth",
            "reasoning": "Internal document store may have cached industry reports with granular market data.",
            "priority": 2,
            "expected_value": "medium"
        }
    ]
}
```

**Tool execution:** The agent invokes `web_search` with the optimized query, then `document_search`. Both tools return `RawSourceData` objects.

For query #3 ("AI coding assistant productivity impact enterprise ROI study"):

**Model Output (JSON):**
```json
{
    "tool_decisions": [
        {
            "tool_name": "document_search",
            "optimized_query": "AI code assistant productivity controlled study enterprise ROI measurement",
            "reasoning": "Productivity studies are typically published as research papers or whitepapers, best found in document stores.",
            "priority": 1,
            "expected_value": "high"
        },
        {
            "tool_name": "web_search",
            "optimized_query": "Microsoft GitHub Copilot productivity study 2025 2026 results",
            "reasoning": "Major tech companies publish productivity studies on their blogs that web search can find.",
            "priority": 2,
            "expected_value": "high"
        }
    ]
}
```

**Routing decision:** 8 successful sources retrieved => **route to extractor**.

---

### Stage 3: Extractor

For the Gartner source:

**Model Input:**
```
Source: Gartner AI Dev Tools Report 2026
Source Type: web_api
Research Sections: Market Size & Growth, Competitive Landscape, Productivity Impact & ROI, Emerging Trends & Future Outlook

Content:
The global AI developer tools market reached $15.2 billion in 2026, growing 35%
year-over-year. GitHub Copilot leads with approximately 40% market share and
over 15 million subscribers. Enterprise adoption hit 67% for organizations with
500+ developers. The compound annual growth rate is projected at 32.8% through
2030. Agentic coding features are now offered by 60% of vendors...
```

**Model Output (JSON):**
```json
{
    "facts": [
        {
            "claim": "AI developer tools market reached $15.2 billion in 2026 with 35% YoY growth",
            "category": "Market Size & Growth",
            "confidence": 0.88,
            "is_quantitative": true,
            "raw_value": "$15.2B"
        },
        {
            "claim": "GitHub Copilot leads with approximately 40% market share and 15M+ subscribers",
            "category": "Competitive Landscape",
            "confidence": 0.90,
            "is_quantitative": true,
            "raw_value": "40%"
        },
        {
            "claim": "Enterprise adoption reached 67% for organizations with 500+ developers",
            "category": "Market Size & Growth",
            "confidence": 0.85,
            "is_quantitative": true,
            "raw_value": "67%"
        },
        {
            "claim": "CAGR projected at 32.8% through 2030",
            "category": "Emerging Trends & Future Outlook",
            "confidence": 0.78,
            "is_quantitative": true,
            "raw_value": "32.8%"
        },
        {
            "claim": "60% of vendors now offer agentic coding features in 2026",
            "category": "Emerging Trends & Future Outlook",
            "confidence": 0.82,
            "is_quantitative": true,
            "raw_value": "60%"
        }
    ]
}
```

**Guardrails applied:** Schema validated (has "facts" key), no refusal detected, all confidence values clamped to [0,1].

**Routing decision:** 34 facts extracted (> 0) => **route to comparator**.

---

### Stage 4: Comparator

**Model Input (for "Market Size & Growth" category):**
```
Category: Market Size & Growth

Facts:
- [a1b2c3d4] (source: Gartner AI Dev Tools Report 2026) AI developer tools market
  reached $15.2 billion in 2026 with 35% YoY growth
- [e5f6g7h8] (source: IDC Worldwide AI Software Forecast) AI developer tools market
  estimated at $18.7 billion in 2026 with 42% growth
- [i9j0k1l2] (source: Stack Overflow Developer Survey 2026) Enterprise adoption
  reached 67% for organizations with 500+ developers
```

**Model Output (JSON):**
```json
{
    "comparisons": [
        {
            "topic": "Market size valuation in 2026",
            "agreement_status": "partial",
            "supporting_fact_ids": ["a1b2c3d4", "e5f6g7h8"],
            "conflicting_fact_ids": [],
            "explanation": "Gartner ($15.2B) and IDC ($18.7B) agree on strong growth but differ by ~23% on total market size. The discrepancy likely stems from different scope definitions.",
            "confidence": 0.80
        },
        {
            "topic": "Enterprise adoption rate",
            "agreement_status": "unique",
            "supporting_fact_ids": ["i9j0k1l2"],
            "conflicting_fact_ids": [],
            "explanation": "Only one source provides enterprise adoption data. Cannot cross-validate.",
            "confidence": 0.65
        }
    ],
    "open_questions": [
        {
            "question": "What is the long-term impact of AI code generation on developer skill development?",
            "context": "No longitudinal studies beyond 18 months exist yet",
            "priority": "high"
        }
    ]
}
```

**Routing decision:** Always proceeds to **writer**.

---

### Stage 5: Writer (First Pass)

**Model Input (abbreviated):**
```
Research Prompt: Analyze the current market trend for AI-powered developer tools in 2026

Outline:
Title: AI Developer Tools Market Analysis 2026
Sections: Market Size & Growth, Competitive Landscape, Productivity Impact & ROI, Emerging Trends

Extracted Facts:
- [Market Size & Growth] AI developer tools market reached $15.2B (confidence: 0.88)
- [Market Size & Growth] AI developer tools market estimated at $18.7B (confidence: 0.85)
- [Competitive Landscape] GitHub Copilot leads with ~40% share (confidence: 0.90)
... (34 facts total)

Source Comparisons:
- [partial] Market size valuation: Gartner and IDC differ by ~23%
- [agree] GitHub Copilot dominance: All sources agree on ~40% share
- [conflict] Code quality impact: Conflicting findings between studies
... (12 comparisons total)
```

**Model Output (JSON):**
```json
{
    "executive_summary": "The AI-powered developer tools market is experiencing explosive growth in 2026, with market size estimates ranging from $15.2 billion (Gartner) to $18.7 billion (IDC)...",
    "sections": [
        {
            "title": "Market Size & Growth",
            "summary": "The AI developer tools market has grown significantly...",
            "bullet_points": [
                {
                    "text": "Global market size estimated at $15.2-18.7 billion in 2026",
                    "citation_sources": ["Gartner AI Dev Tools Report 2026", "IDC Worldwide AI Software Forecast"]
                }
            ]
        }
    ]
}
```

**Confidence computation (in `writer_node()`):**
```python
fact_conf = sum(f.confidence for f in facts) / len(facts)    # = 0.83
comp_conf = sum(c.confidence for c in comparisons) / len(comparisons)  # = 0.76
overall_conf = (fact_conf + comp_conf) / 2                   # = 0.795
```

**Routing decision:** `0.795 >= 0.7` (threshold) => **route to finalize** (no revision needed).

---

### Alternative Path: Reflection Loop (When Confidence < 0.7)

If the Writer had produced confidence = 0.55:

```
[res-a1b2c3d4] Confidence 0.55 < 0.70 threshold — revision #1 (reflection loop)
```

The workflow would route **back to comparator** for re-analysis with accumulated context, then back to Writer for revision #2. After 2 revision loops (`max_revision_loops=2`), the report finalizes regardless of confidence, with a logged warning.

---

## Confidence Computation and Flow Impact

### Where Confidence Is Computed

Confidence originates from **two LLM-generated sources** and is computed in **three locations**:

#### Source 1: Extractor (per-fact confidence)
```
File: agents/extractor.py
The LLM assigns a 0.0-1.0 confidence to each extracted fact.
```
```python
# LLM produces:
{"claim": "Market size is $15.2B", "confidence": 0.88, ...}
```

#### Source 2: Comparator (per-comparison confidence)
```
File: agents/comparator.py
The LLM assigns confidence to each cross-source comparison.
```
```python
# LLM produces:
{"topic": "Market size valuation", "agreement_status": "partial", "confidence": 0.80}
```

#### Aggregation: Writer (overall confidence)
```
File: agents/writer.py, lines 142-144
```
```python
fact_conf = sum(f.confidence for f in facts) / max(len(facts), 1)
comp_conf = sum(c.confidence for c in comparisons) / max(len(comparisons), 1)
overall_conf = (fact_conf + comp_conf) / 2
```

### How Confidence Changes Flow Behavior

```
File: orchestration/routing.py — route_after_writing()

                    ┌──────────────────────────────────────────┐
                    │       Writer produces report              │
                    │       overall_confidence = X              │
                    └────────────────┬─────────────────────────┘
                                     │
                         ┌───────────┴──────────┐
                         │                      │
                    X >= 0.70              X < 0.70
                         │                      │
                    ┌────┴────┐          ┌──────┴──────┐
                    │ FINALIZE│          │revision < 2?│
                    └─────────┘          └──────┬──────┘
                                           YES  │  NO
                                         ┌──────┴──────┐
                                         │             │
                                    COMPARATOR    FINALIZE
                                    (re-analyze)  (with warning)
                                         │
                                         v
                                      WRITER
                                    (revision +1)
```

```python
# routing.py — the actual decision code:
def route_after_writing(state: dict) -> str:
    confidence = report.metadata.overall_confidence
    threshold = config.workflow.confidence_threshold  # default: 0.7

    if confidence < threshold and revision_count < config.workflow.max_revision_loops:
        return "comparator"  # REFLECTION LOOP
    return "finalize"
```

### Confidence Thresholds (Configurable)

| Parameter | Default | Env Variable | Effect |
|-----------|---------|-------------|--------|
| `confidence_threshold` | 0.7 | `CONFIDENCE_THRESHOLD` | Below this triggers reflection |
| `max_revision_loops` | 2 | `MAX_REVISION_LOOPS` | Max reflection iterations |
| `max_retries` | 3 | `MAX_RETRIES` | Per-stage retry budget |

---

## Estimated Token Spend

For one full workflow run with the sample prompt:

| Stage | Model | Input Tokens | Output Tokens | Cost (OpenAI) |
|-------|-------|-------------|--------------|---------------|
| Planner | gpt-4o | ~400 | ~500 | ~$0.007 |
| Gatherer (5 queries x tool selection) | gpt-4o-mini | ~1,500 | ~800 | ~$0.001 |
| Extractor (8 sources) | gpt-4o-mini | ~12,000 | ~3,000 | ~$0.008 |
| Comparator (4 categories) | gpt-4o | ~3,000 | ~1,500 | ~$0.034 |
| Writer | gpt-4o | ~4,000 | ~2,000 | ~$0.045 |
| **Total** | | **~20,900** | **~7,800** | **~$0.095** |

**Per-run cost: ~$0.10** (under Azure Functions Consumption free tier for compute).

With 1 reflection loop: add ~$0.08 for Comparator + Writer rerun = **~$0.18 per run**.

**Cost optimization strategies:**
- Use GPT-4o-mini for tool selection and extraction (3x cheaper)
- Truncate source content to 8,000 chars max
- Cache Tavily results for repeated queries
- Use local Ollama models for development/testing ($0.00)

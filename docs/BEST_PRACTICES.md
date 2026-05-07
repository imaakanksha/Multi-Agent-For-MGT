# 📚 Best Practices & References

## Best Practices Applied in This Architecture

### 1. Planning Before Execution
**Practice**: Always decompose a research task into a structured plan before retrieving data.

**Why**: Without a plan, agents retrieve too much irrelevant information, waste tokens, and produce unfocused reports. The Planner Agent creates a roadmap that constrains and focuses all downstream work.

**Reference**: Google DeepMind, "Plan-and-Solve Prompting" (2023) — demonstrated that LLMs produce significantly better outputs when given a structured plan before execution.

---

### 2. Typed State with Reducer Functions
**Practice**: Define shared state using `TypedDict` with `Annotated` reducer functions.

**Why**: Without reducers, parallel agent updates cause data loss (last-write-wins). Reducer functions (e.g., `merge_lists`) ensure that concurrent state updates are safely merged.

**Reference**: LangGraph Documentation — [State Management](https://langchain-ai.github.io/langgraph/concepts/low_level/#state)

---

### 3. Hybrid Model Strategy
**Practice**: Use expensive frontier models (GPT-4o) for complex reasoning tasks and cheaper models (GPT-4o-mini) for routine extraction.

**Why**: Reduces costs by 40-60% without sacrificing output quality. Extraction is a focused, repetitive task that doesn't need frontier-level reasoning.

**Reference**: LangChain Blog, "Optimizing Multi-Agent Costs" (2025) — recommends tiered model selection based on task complexity.

---

### 4. Reflection Loop (Critic Pattern)
**Practice**: Implement a feedback loop where the Writer's output is evaluated and sent back for revision if quality thresholds aren't met.

**Why**: LLMs benefit from iterative refinement. A single-pass generation is often lower quality than a generate-then-critique-then-revise cycle.

**Reference**: Madaan et al., "Self-Refine: Iterative Refinement with Self-Feedback" (NeurIPS 2023) — showed 5-20% improvement in output quality with self-refinement loops.

---

### 5. Graceful Degradation
**Practice**: Every error path should produce partial output rather than failing silently. Individual agent failures should not halt the entire pipeline.

**Why**: In production, external APIs fail, LLMs return malformed output, and documents are unreadable. A resilient system always produces the best possible output given available data.

**Reference**: AWS Well-Architected Framework — Reliability Pillar, "Design for failure" principle.

---

### 6. Source-Aware Extraction
**Practice**: Track provenance (which source said what) through every transformation in the pipeline.

**Why**: Without citation tracking, the final report cannot be verified, audited, or trusted. Every fact in the output should be traceable back to its source.

**Reference**: Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" (NeurIPS 2020) — established the importance of grounding LLM outputs in retrieved evidence.

---

### 7. Explicit Conflict Detection
**Practice**: Actively compare facts from different sources and classify them as agree/conflict/partial/unique.

**Why**: A research report that only presents one perspective is misleading. Highlighting conflicts and gaps signals intellectual honesty and helps the reader make informed decisions.

**Reference**: Multi-source verification is a core principle of investigative journalism and systematic literature reviews (Cochrane Methodology).

---

### 8. Observability as First-Class Concern
**Practice**: Integrate tracing (LangSmith) from day one, not as an afterthought.

**Why**: Multi-agent workflows are non-deterministic — you cannot debug them by reading code alone. Tracing captures the actual execution path, state transitions, and agent decisions.

**Reference**: LangSmith Documentation — [Tracing](https://docs.smith.langchain.com/tracing)

---

### 9. Checkpointing for Durability
**Practice**: Persist workflow state to a durable store (Cosmos DB) at every stage transition.

**Why**: Research workflows can take minutes to complete. Without checkpointing, a crash at the writing stage means re-running the entire pipeline from scratch.

**Reference**: LangGraph Documentation — [Persistence](https://langchain-ai.github.io/langgraph/concepts/persistence/)

---

### 10. Separation of Concerns
**Practice**: Each agent has a single responsibility and communicates only through the shared state.

**Why**: This makes agents independently testable, replaceable, and parallelizable. Adding a new agent (e.g., a "Fact Checker") only requires adding a node and edges — no changes to existing agents.

**Reference**: Martin Fowler, "Microservices Architecture" — applied to agent design. Also, the Actor Model (Hewitt, 1973) — agents as isolated units communicating through messages.

---

## Key References

### Framework Documentation
| Resource | URL |
|----------|-----|
| LangGraph Docs | https://langchain-ai.github.io/langgraph/ |
| LangChain Docs | https://python.langchain.com/ |
| LangSmith Docs | https://docs.smith.langchain.com/ |
| Azure Cosmos DB | https://learn.microsoft.com/azure/cosmos-db/ |
| Azure AI Search | https://learn.microsoft.com/azure/search/ |

### Academic Papers
| Paper | Year | Key Contribution |
|-------|------|-------------------|
| Self-Refine (Madaan et al.) | 2023 | Iterative refinement with self-feedback |
| RAG (Lewis et al.) | 2020 | Grounding LLM outputs in retrieved evidence |
| Plan-and-Solve (Wang et al.) | 2023 | Planning-first approach for complex tasks |
| ReAct (Yao et al.) | 2023 | Reasoning + Acting paradigm for agents |
| AutoGen (Wu et al.) | 2023 | Multi-agent conversation framework |

### Industry Reports
| Report | Source |
|--------|--------|
| Multi-Agent Design Patterns | LangChain Blog, 2025 |
| Agentic AI Best Practices | Google DeepMind, 2025 |
| Enterprise AI Agent Deployment | McKinsey Digital, 2025 |
| State of AI Agents | Sequoia Capital, 2025 |

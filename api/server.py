"""
FastAPI HTTP Trigger — REST endpoint for the Multi-Agent Research Workflow.

This provides the HTTP trigger required for production deployment.
Supports both synchronous (wait-for-result) and asynchronous
(submit-and-poll) execution modes.

Endpoints:
  POST /research          → Submit a new research workflow (async)
  GET  /research/{id}     → Poll workflow status by correlation ID
  GET  /research/{id}/report → Get the completed report
  GET  /research/{id}/history → Get full stage transition history
  GET  /workflows         → List recent workflows
  GET  /dead-letter       → Inspect dead-lettered workflows
  GET  /health            → Health check

Deployment options:
  - Local:           uvicorn api.server:app --reload
  - Azure Functions: Wrap with azure.functions adapter
  - Docker:          Include in container with gunicorn
"""

from __future__ import annotations
import json
import logging
import time
import threading
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from orchestration.state import create_initial_state
from orchestration.graph import build_research_graph
from orchestration.correlation import generate_correlation_id, WorkflowTracker
from persistence.state_store import get_state_store
from persistence.dead_letter import get_dead_letter_queue

logger = logging.getLogger(__name__)

# ── FastAPI App ────────────────────────────────────────────────────
app = FastAPI(
    title="Multi-Agent Research Report Generator",
    description="REST API for submitting research prompts and retrieving AI-generated reports.",
    version="1.0.0",
)

# ── In-memory cache for completed reports (production: use Redis) ──
_report_cache: dict[str, dict] = {}

# ── Compile graph once at startup ──────────────────────────────────
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_research_graph(use_memory_checkpoint=True)
    return _graph


# ── Request / Response Models ──────────────────────────────────────

class ResearchRequest(BaseModel):
    """HTTP request body for submitting a research workflow."""
    prompt: str = Field(
        ..., min_length=10, max_length=2000,
        description="The research question or topic to investigate",
        examples=["Analyze the current market trend for AI-powered developer tools in 2026"],
    )


class ResearchSubmitResponse(BaseModel):
    """Response after submitting an async research workflow."""
    correlation_id: str
    status: str
    message: str
    poll_url: str
    submitted_at: str


class WorkflowStatusResponse(BaseModel):
    """Response for workflow status polling."""
    correlation_id: str
    current_stage: str
    status: str
    total_transitions: int
    last_updated: str
    confidence: float


class WorkflowListItem(BaseModel):
    """Summary of a workflow for listing."""
    correlation_id: str
    stage: str
    status: str
    created_at: str


# ── Background Worker ─────────────────────────────────────────────

def _run_workflow_async(correlation_id: str, prompt: str):
    """
    Execute the research workflow in a background thread.

    The result is cached in-memory and the status can be polled
    via the /research/{id} endpoint.
    """
    try:
        graph = _get_graph()
        initial_state = create_initial_state(prompt, correlation_id=correlation_id)

        # Record workflow start
        tracker = WorkflowTracker(correlation_id)
        tracker.workflow_started(prompt)

        start_time = time.time()
        config = {"configurable": {"thread_id": correlation_id}}

        logger.info("[%s] Async workflow started for prompt: %s",
                    correlation_id[:12], prompt[:80])

        final_state = graph.invoke(initial_state, config=config)
        elapsed = time.time() - start_time

        # Cache the result
        report = final_state.get("final_report")
        _report_cache[correlation_id] = {
            "status": final_state.get("workflow_status", "unknown"),
            "report_json": report.model_dump(mode="json") if report else None,
            "report_markdown": report.to_markdown() if report else None,
            "elapsed_seconds": elapsed,
            "error_log": final_state.get("error_log", []),
            "correlation_id": correlation_id,
        }

        logger.info("[%s] Async workflow completed in %.1fs — status: %s",
                    correlation_id[:12], elapsed,
                    final_state.get("workflow_status", "unknown"))

    except Exception as e:
        logger.error("[%s] Async workflow crashed: %s", correlation_id[:12], e)
        _report_cache[correlation_id] = {
            "status": "failed",
            "report_json": None,
            "report_markdown": None,
            "error_log": [str(e)],
            "correlation_id": correlation_id,
        }


# ── Endpoints ──────────────────────────────────────────────────────

@app.post("/research", response_model=ResearchSubmitResponse, status_code=202)
async def submit_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    """
    Submit a new research workflow (asynchronous).

    Returns a correlation_id immediately. The workflow runs in the
    background. Poll GET /research/{correlation_id} for status.
    """
    correlation_id = generate_correlation_id()

    # Launch workflow in background
    background_tasks.add_task(_run_workflow_async, correlation_id, request.prompt)

    return ResearchSubmitResponse(
        correlation_id=correlation_id,
        status="pending",
        message="Research workflow submitted. Poll the status URL for progress.",
        poll_url=f"/research/{correlation_id}",
        submitted_at=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/research/{correlation_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(correlation_id: str):
    """
    Poll the status of a running or completed workflow.

    Returns the current stage, overall status, and confidence score.
    """
    store = get_state_store()
    status = store.get_workflow_status(correlation_id)

    if not status:
        # Check in-memory cache as fallback
        if correlation_id in _report_cache:
            cached = _report_cache[correlation_id]
            return WorkflowStatusResponse(
                correlation_id=correlation_id,
                current_stage="finalized",
                status=cached["status"],
                total_transitions=0,
                last_updated=datetime.now(timezone.utc).isoformat(),
                confidence=0.0,
            )
        raise HTTPException(status_code=404, detail=f"Workflow {correlation_id} not found")

    return WorkflowStatusResponse(**status)


@app.get("/research/{correlation_id}/report")
async def get_workflow_report(correlation_id: str):
    """
    Get the completed research report (JSON + Markdown).

    Returns 404 if the workflow hasn't completed yet.
    """
    if correlation_id not in _report_cache:
        raise HTTPException(
            status_code=404,
            detail=f"Report for {correlation_id} not found. "
                   f"The workflow may still be running — poll /research/{correlation_id} for status.",
        )

    cached = _report_cache[correlation_id]
    if cached["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Workflow failed",
                "errors": cached.get("error_log", []),
                "correlation_id": correlation_id,
            },
        )

    return {
        "correlation_id": correlation_id,
        "status": cached["status"],
        "report": cached.get("report_json"),
        "report_markdown": cached.get("report_markdown"),
        "elapsed_seconds": cached.get("elapsed_seconds"),
    }


@app.get("/research/{correlation_id}/history")
async def get_workflow_history(correlation_id: str):
    """
    Get the full stage transition history for a workflow.

    Returns every recorded state transition with timestamps,
    enabling full observability of the workflow execution path.
    """
    store = get_state_store()
    history = store.get_workflow_history(correlation_id)

    if not history:
        raise HTTPException(status_code=404, detail=f"No history for {correlation_id}")

    return {
        "correlation_id": correlation_id,
        "total_transitions": len(history),
        "transitions": history,
    }


@app.get("/workflows")
async def list_workflows(status: str | None = None, limit: int = 50):
    """
    List recent workflows, optionally filtered by status.

    Query params:
      ?status=completed|failed|running|dead_lettered
      ?limit=50
    """
    store = get_state_store()
    workflows = store.list_workflows(status_filter=status, limit=limit)
    return {"workflows": workflows, "count": len(workflows)}


@app.get("/dead-letter")
async def list_dead_letters(limit: int = 50):
    """
    Inspect dead-lettered (terminally failed) workflows.

    These workflows exhausted all retry attempts and need manual
    inspection or replay.
    """
    dlq = get_dead_letter_queue()
    entries = dlq.list_entries(limit=limit)
    return {"dead_letters": entries, "count": len(entries)}


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
    }

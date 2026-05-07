"""
Multi-Agent Research Report Generator — Entry Point.

Supports three execution modes:
  1. CLI:      python main.py --prompt "Your research question"
  2. HTTP API: python main.py --serve (launches FastAPI server)
  3. Library:  from main import run_research; run_research("prompt")
"""

from __future__ import annotations
import argparse
import json
import logging
import sys
import time

from orchestration.state import create_initial_state
from orchestration.graph import build_research_graph
from orchestration.correlation import generate_correlation_id, WorkflowTracker
from persistence.state_store import get_state_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def run_research(prompt: str, output_path: str | None = None) -> dict:
    """
    Execute the full multi-agent research workflow.

    Args:
        prompt: The research question or topic.
        output_path: Optional file path to save the JSON report.

    Returns:
        The final state dictionary containing the report.
    """
    # ── Generate correlation ID ────────────────────────────────────
    correlation_id = generate_correlation_id()

    logger.info("=" * 60)
    logger.info("MULTI-AGENT RESEARCH WORKFLOW")
    logger.info("Correlation ID: %s", correlation_id)
    logger.info("Prompt: %s", prompt)
    logger.info("=" * 60)

    # ── Record workflow start ──────────────────────────────────────
    tracker = WorkflowTracker(correlation_id)
    tracker.workflow_started(prompt)

    # 1. Build the graph
    graph = build_research_graph(use_memory_checkpoint=True)

    # 2. Create initial state with correlation ID
    initial_state = create_initial_state(prompt, correlation_id=correlation_id)

    # 3. Execute the workflow
    start = time.time()
    config = {"configurable": {"thread_id": correlation_id}}

    logger.info("[%s] Starting workflow execution...", correlation_id[:12])
    final_state = graph.invoke(initial_state, config=config)
    elapsed = time.time() - start

    logger.info("[%s] Workflow completed in %.1f seconds", correlation_id[:12], elapsed)
    logger.info("[%s] Status: %s", correlation_id[:12],
                final_state.get("workflow_status", "unknown"))

    # ── Log status transitions ─────────────────────────────────────
    transitions = final_state.get("status_transitions", [])
    if transitions:
        logger.info("[%s] Stage transitions (%d total):", correlation_id[:12], len(transitions))
        for t in transitions:
            logger.info("  → %s: %s (confidence=%.2f)",
                        t.get("stage", "?"), t.get("status", "?"),
                        t.get("confidence", 0.0))

    # 4. Output the report
    report = final_state.get("final_report")
    if report:
        # JSON output
        report_json = report.model_dump(mode="json")

        # Inject correlation_id into report metadata
        report_json["metadata"]["correlation_id"] = correlation_id

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report_json, f, indent=2, default=str)
            logger.info("[%s] JSON report saved to: %s", correlation_id[:12], output_path)

        # Markdown output
        md_path = (output_path or "report").replace(".json", ".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())
        logger.info("[%s] Markdown report saved to: %s", correlation_id[:12], md_path)

        print("\n" + "=" * 60)
        print(report.to_markdown())
    else:
        logger.error("[%s] No report generated. Check error_log.", correlation_id[:12])
        for err in final_state.get("error_log", []):
            logger.error("  → %s", err)

    # ── Summary ────────────────────────────────────────────────────
    store = get_state_store()
    history = store.get_workflow_history(correlation_id)
    logger.info("[%s] Persisted %d state transitions to store",
                correlation_id[:12], len(history))

    return final_state


def main():
    parser = argparse.ArgumentParser(
        description="Multi-Agent Research Report Generator"
    )
    parser.add_argument("--prompt", "-p", help="Research prompt (CLI mode)")
    parser.add_argument("--output", "-o", default="report.json", help="Output file path")
    parser.add_argument("--serve", action="store_true",
                        help="Launch FastAPI HTTP server")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    args = parser.parse_args()

    if args.serve:
        # ── HTTP API Mode ──────────────────────────────────────────
        import uvicorn
        logger.info("Starting HTTP server on %s:%d", args.host, args.port)
        uvicorn.run("api.server:app", host=args.host, port=args.port, reload=True)

    elif args.prompt:
        # ── CLI Mode ───────────────────────────────────────────────
        run_research(args.prompt, args.output)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

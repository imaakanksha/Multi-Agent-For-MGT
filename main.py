"""
Multi-Agent Research Report Generator — Entry Point.

Usage:
    python main.py --prompt "Your research question here"
    python main.py --prompt "Compare top 3 cloud providers" --output report.json
"""

from __future__ import annotations
import argparse
import json
import logging
import sys
import time

from orchestration.state import create_initial_state
from orchestration.graph import build_research_graph

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
    logger.info("=" * 60)
    logger.info("MULTI-AGENT RESEARCH WORKFLOW")
    logger.info("Prompt: %s", prompt)
    logger.info("=" * 60)

    # 1. Build the graph
    graph = build_research_graph(use_memory_checkpoint=True)

    # 2. Create initial state
    initial_state = create_initial_state(prompt)

    # 3. Execute the workflow
    start = time.time()
    config = {"configurable": {"thread_id": f"research_{int(time.time())}"}}

    logger.info("Starting workflow execution...")
    final_state = graph.invoke(initial_state, config=config)
    elapsed = time.time() - start

    logger.info("Workflow completed in %.1f seconds", elapsed)
    logger.info("Status: %s", final_state.get("workflow_status", "unknown"))

    # 4. Output the report
    report = final_state.get("final_report")
    if report:
        # JSON output
        report_json = report.model_dump(mode="json")
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report_json, f, indent=2, default=str)
            logger.info("JSON report saved to: %s", output_path)

        # Markdown output
        md_path = (output_path or "report").replace(".json", ".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())
        logger.info("Markdown report saved to: %s", md_path)

        print("\n" + "=" * 60)
        print(report.to_markdown())
    else:
        logger.error("No report generated. Check error_log in state.")
        for err in final_state.get("error_log", []):
            logger.error("  → %s", err)

    return final_state


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Research Report Generator")
    parser.add_argument("--prompt", "-p", required=True, help="Research prompt")
    parser.add_argument("--output", "-o", default="report.json", help="Output file path")
    args = parser.parse_args()

    run_research(args.prompt, args.output)


if __name__ == "__main__":
    main()

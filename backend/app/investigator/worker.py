"""Background worker that runs the DLQ Investigator on an interval.

Two ways to run:

  * **In-process** — :func:`start_background_investigator` launches an asyncio
    task from the FastAPI lifespan when ``INVESTIGATOR_ENABLED=true``. The sync
    Neo4j work runs in a thread so it never blocks the event loop.
  * **Standalone** — ``python -m app.investigator.worker`` (``--once`` for a
    single pass, ``--interval`` seconds for a loop), handy for a cron/sidecar
    or a demo.

Each pass also reports the depth of the literal validation Dead-Letter Queue
(the quarantined-payload JSONL), so operators see both kinds of data-quality
debt — malformed payloads *and* contradicted claims — from one worker.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from app.ingestion.dlq import dlq_path
from app.investigator.investigator import DEFAULT_VARIANCE_THRESHOLD, DLQInvestigator

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 300.0


def _dlq_depth() -> int:
    """Count quarantined payloads in the validation DLQ file (0 if none)."""
    path: Path = dlq_path()
    try:
        if not path.exists():
            return 0
        with path.open("r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        logger.warning("Could not read DLQ file at %s.", path, exc_info=True)
        return 0


def run_pass(
    variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
    flag: bool = True,
    use_llm: bool = True,
) -> dict:
    """Run one investigation pass synchronously; return its summary dict."""
    investigator = DLQInvestigator(
        variance_threshold=variance_threshold, use_llm=use_llm
    )
    report = investigator.investigate_once(flag=flag)
    summary = report.to_dict()
    summary["dlq_depth"] = _dlq_depth()
    logger.info(
        "Investigator pass: %d conflict(s) flagged, %d payload(s) in validation DLQ.",
        summary["total_conflicts"], summary["dlq_depth"],
    )
    return summary


async def run_forever(
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
    flag: bool = True,
    use_llm: bool = True,
) -> None:
    """Run investigation passes forever, ``interval_seconds`` apart."""
    logger.info("DLQ Investigator worker started (every %.0fs).", interval_seconds)
    while True:
        try:
            await asyncio.to_thread(run_pass, variance_threshold, flag, use_llm)
        except asyncio.CancelledError:
            logger.info("DLQ Investigator worker cancelled; stopping.")
            raise
        except Exception:  # noqa: BLE001 - one bad pass must not kill the worker.
            logger.exception("Investigation pass failed; will retry next interval.")
        await asyncio.sleep(interval_seconds)


def start_background_investigator(app) -> "asyncio.Task | None":
    """Start the worker as a FastAPI background task when enabled via env.

    Gated on ``INVESTIGATOR_ENABLED=true`` so the default boot is unaffected.
    Reads ``INVESTIGATOR_INTERVAL_SECONDS`` and ``INVESTIGATOR_VARIANCE_THRESHOLD``.
    Returns the created task (so the caller can cancel it on shutdown), or None.
    """
    if os.environ.get("INVESTIGATOR_ENABLED", "false").lower() != "true":
        logger.info("DLQ Investigator disabled (set INVESTIGATOR_ENABLED=true to enable).")
        return None

    interval = float(os.environ.get("INVESTIGATOR_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS))
    threshold = float(
        os.environ.get("INVESTIGATOR_VARIANCE_THRESHOLD", DEFAULT_VARIANCE_THRESHOLD)
    )
    task = asyncio.create_task(run_forever(interval, threshold))
    logger.info("DLQ Investigator background task scheduled.")
    return task


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Autonomous DLQ Investigator.")
    parser.add_argument("--once", action="store_true", help="Run a single pass and exit.")
    parser.add_argument(
        "--interval", type=float, default=DEFAULT_INTERVAL_SECONDS,
        help="Seconds between passes in loop mode.",
    )
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_VARIANCE_THRESHOLD,
        help="Relative variance threshold (0.20 == 20%%).",
    )
    parser.add_argument("--no-flag", action="store_true", help="Investigate but do not write flags.")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM narration of rationales.")
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    if args.once:
        summary = run_pass(args.threshold, flag=not args.no_flag, use_llm=not args.no_llm)
        import json

        print(json.dumps(summary, indent=2))
    else:
        asyncio.run(
            run_forever(args.interval, args.threshold, flag=not args.no_flag, use_llm=not args.no_llm)
        )


if __name__ == "__main__":
    _main()

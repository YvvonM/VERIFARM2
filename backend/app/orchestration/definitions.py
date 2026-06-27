"""Dagster definitions for VERIFARMS ingestion.

Load with:  dagster dev -m app.orchestration.definitions

Defines a job that runs the cooperative CDC sync, a schedule that fires it every
15 minutes, and a run-failure sensor that routes failures to the same alerting
used inside the pipeline. The op is a one-line wrapper around the already-tested
``sync_once`` — no orchestration logic leaks into the business code.
"""

from __future__ import annotations

import asyncio

from dagster import (
    Definitions,
    OpExecutionContext,
    RetryPolicy,
    RunFailureSensorContext,
    ScheduleDefinition,
    job,
    op,
    run_failure_sensor,
)

from app.ingestion import observability
from app.ingestion.connectors.cooperative_sync import sync_once

# Cooperative pulls are I/O bound and occasionally hit a flaky external DB —
# retry a couple of times with backoff before failing the run (and alerting).
_RETRY = RetryPolicy(max_retries=2, delay=30)


@op(retry_policy=_RETRY)
def cooperative_registry_sync_op(context: OpExecutionContext) -> dict:
    """Run one CDC sync pass for the cooperative registry."""
    summary = asyncio.run(sync_once(source_id="tegemeo"))
    context.log.info(f"Sync summary: {summary}")
    if summary.get("rejected"):
        context.log.warning(f"{summary['rejected']} row(s) rejected by schema mapping.")
    return summary


@job
def cooperative_registry_sync_job():
    cooperative_registry_sync_op()


# Every 15 minutes. CDC keeps each run cheap regardless of registry size.
cooperative_sync_schedule = ScheduleDefinition(
    name="cooperative_sync_every_15m",
    job=cooperative_registry_sync_job,
    cron_schedule="*/15 * * * *",
)


@run_failure_sensor
def alert_on_run_failure(context: RunFailureSensorContext) -> None:
    """Route any failed run to the pipeline's alerting (webhook + log)."""
    observability.notify(
        subject=f"Dagster run failed: {context.dagster_run.job_name}",
        message=context.failure_event.message or "run failed",
        level="error",
        category="orchestration",
        context={"run_id": context.dagster_run.run_id},
    )


defs = Definitions(
    jobs=[cooperative_registry_sync_job],
    schedules=[cooperative_sync_schedule],
    sensors=[alert_on_run_failure],
)

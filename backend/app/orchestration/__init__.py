"""Orchestration layer — schedules the ingestion connectors.

Dagster is a thin trigger here: the sync logic, CDC state and alerting live in
plain, tested Python (``app.ingestion.*``). Dagster only provides the schedule,
run history, retries and failure routing. See ``definitions.py``.
"""

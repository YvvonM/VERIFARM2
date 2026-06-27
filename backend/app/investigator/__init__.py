"""Autonomous DLQ Investigator — the background data-quality agent.

Monitors the platform for conflicting claims (e.g. self-reported vs. satellite
land size), investigates each discrepancy against the attesting institution's
reputation and history, and flags the offending Claim nodes with a calculated
recommendation — keeping the gold layer pristine without a human data steward
checking every record by hand.
"""

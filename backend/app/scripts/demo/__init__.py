"""Demo data-source seeders.

Phase 0 of the "several demo databases" plan: a *single* canonical farmer roster
(:mod:`app.scripts.demo.roster`) that every external demo source seeds against, so
their records share one farmer-id space (``F-0001 … F-NNNN``) with the reified
trust layer. That shared id space is what makes cross-source verification visible
— e.g. a cooperative Postgres row whose land size disagrees with the satellite
ground truth surfaces as a flagged conflict in the DLQ Investigator.

Per-source seeders live alongside this package (e.g.
:mod:`app.scripts.demo.seed_cooperative_pg` for the Phase 1 cooperative Postgres).
"""

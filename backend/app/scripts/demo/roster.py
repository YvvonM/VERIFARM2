"""Canonical demo farmer roster — the shared id space for every demo source.

This is Phase 0 of the demo-databases plan. Every external demo source (the
cooperative Postgres in Phase 1, telemetry/S3 later) seeds against *this* roster
so all of them speak the same farmer ids as the reified trust layer
(``app.scripts.seed_reified``):

  * ``member_uuid`` / farmer id  = ``F-0001 … F-{n:04d}``      (matches the seed)
  * ``country``                  = Kenya for odd i, Nigeria for even i  (matches)
  * ``true_land_ha``             ≈ the satellite ground-truth land size the seed
                                   plants, ``1.0 + (i % 10) * 0.4`` ha.

``true_land_ha`` intentionally drops the seed's tiny ±0.1 ha random jitter: we
only need to land *near* the ground truth so an honest cooperative row reads as
agreement (well inside the Investigator's 20% relative-variance threshold), and a
deliberately inflated one reads as a conflict. Reproducing the seed's exact RNG
draw order here would couple the two modules for no demo benefit.

Nothing here is fabricated *verification* — it is synthetic *demo seed* data, the
same role the data generator plays, kept deliberately outside ``app.verification``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Reuse the one true conversion factor the ingestion adapter uses, so an
# "agreement" row converts back to ~the same hectares the connector computes.
from app.ingestion.adapters import ACRES_TO_HECTARES  # 1 acre = 0.404686 ha

# Default population. Matches the reified-seed default (``--farmers 60``) so the
# two seeders cover exactly the same farmers out of the box.
DEFAULT_FARMERS = 60

# Investigator flags a non-authoritative claim when its relative variance from
# ground truth exceeds this (see investigator.DEFAULT_VARIANCE_THRESHOLD = 0.20).
VARIANCE_THRESHOLD = 0.20

# Inflate the conflict rows well past the threshold so the flag is unambiguous.
_CONFLICT_MULTIPLIER = 2.6

# Every Kth roster farmer reports an inflated land size from the cooperative,
# producing a conflict the Investigator will flag. Deliberately a different
# stride (5) from the seed's own coop conflicts (every 7th) so the *live Postgres
# pull* introduces its own, attributable conflicts on top of the static seed.
DEFAULT_CONFLICT_EVERY = 5


@dataclass(frozen=True)
class DemoFarmer:
    """One farmer in the shared demo roster."""

    index: int           # 1-based position; drives id, country, ground truth.
    member_uuid: str     # "F-0001" — the farmer id used across every source.
    country: str         # "Kenya" | "Nigeria"
    true_land_ha: float  # ~satellite ground-truth land size for this farmer.


def demo_roster(n: int = DEFAULT_FARMERS) -> list[DemoFarmer]:
    """Return the canonical ``F-0001 … F-{n:04d}`` roster.

    Deterministic and pure: same ``n`` always yields the same roster, so any
    source seeded from it lines up with the reified seed and with every other
    source.
    """
    roster: list[DemoFarmer] = []
    for i in range(1, n + 1):
        roster.append(
            DemoFarmer(
                index=i,
                member_uuid=f"F-{i:04d}",
                country="Kenya" if i % 2 else "Nigeria",
                true_land_ha=round(1.0 + (i % 10) * 0.4, 2),
            )
        )
    return roster


def is_conflict(index: int, conflict_every: int = DEFAULT_CONFLICT_EVERY) -> bool:
    """Whether the farmer at ``index`` should report a conflicting land size."""
    return conflict_every > 0 and index % conflict_every == 0


def cooperative_member_row(
    farmer: DemoFarmer,
    *,
    updated_at,
    conflict_every: int = DEFAULT_CONFLICT_EVERY,
) -> dict:
    """Shape one farmer into a ``cooperative_members`` row for the Postgres source.

    ``farm_acres`` is derived from the farmer's ground-truth hectares:

      * honest rows convert back to ~the same hectares (a small deterministic
        wobble, kept under the 20% threshold) → reads as agreement;
      * conflict rows (every ``conflict_every`` th farmer) are inflated by
        :data:`_CONFLICT_MULTIPLIER` → reads as a conflict in the Investigator.

    ``harvest_delivered_kg`` is a plausible yield scaled off the true land size.
    The connector converts acres → hectares itself, so we hand it *acres* here.
    """
    honest_acres = farmer.true_land_ha / ACRES_TO_HECTARES
    # Deterministic ±5% wobble so honest rows are not all identical, but stay
    # comfortably inside the 20% variance threshold.
    wobble = 0.95 + (farmer.index % 11) / 100.0  # 0.95 .. 1.05
    acres = honest_acres * wobble
    if is_conflict(farmer.index, conflict_every):
        acres *= _CONFLICT_MULTIPLIER

    return {
        "member_uuid": farmer.member_uuid,
        "farm_acres": round(acres, 2),
        "harvest_delivered_kg": round(farmer.true_land_ha * 1800),
        "updated_at": updated_at,
    }

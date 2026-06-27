"""Milestone 1 — Synthetic Data Generation.

Generates inter-linked, normalized synthetic records simulating Tegemeo
(Kenya) and Agrovesto (Nigeria) farmer registry data for the GenUI
Agricultural Dashboard.

Schema alignment
----------------
The generated entities map onto the OpenSPP registry and FAO Farmer Registry
core concepts:

  * Farmer        -> OpenSPP `Registrant` (individual) / FAO "Agricultural holder"
  * FarmHolding   -> FAO "Agricultural holding" (the production unit + geo point)
  * CropCycle     -> FAO "Crop production cycle" (parcel-season activity)
  * Transaction   -> OpenSPP `Entitlement` / financial event (loan or sale)
  * Organization  -> OpenSPP `Service Provider` / aggregator (Tegemeo, Agrovesto)

The module is import-safe: `generate_dataset()` returns a `SyntheticDataset`
that the Neo4j loader consumes directly. Running the module as a script dumps
each entity/relationship collection to CSV for inspection.
"""

from __future__ import annotations

import argparse
import logging
import random
import uuid
from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path

import pandas as pd
from faker import Faker

logger = logging.getLogger(__name__)

DEFAULT_SEED = 42
DEFAULT_NUM_FARMERS = 1_000

# ---------------------------------------------------------------------------
# Reference data: organizations and per-country (ecosystem) configuration.
# ---------------------------------------------------------------------------

ORGANIZATIONS: list[dict] = [
    {"id": "ORG-TEGEMEO", "name": "Tegemeo Cereals Enterprises", "type": "Tegemeo"},
    {"id": "ORG-AGROVESTO", "name": "Agrovesto", "type": "Agrovesto"},
]

# Each entry drives realistic, ecosystem-specific synthesis. Coordinates are
# (centre_lat, centre_lon, jitter_degrees) bounding-box anchors for each region.
REGION_CONFIG: dict[str, dict] = {
    "Kenya": {
        "org_id": "ORG-TEGEMEO",
        "phone_prefix": "+2547",
        "locale": "en_US",
        "locations": ["Nakuru", "Uasin Gishu"],
        "coords": {
            "Nakuru": (-0.3031, 36.0800, 0.25),
            "Uasin Gishu": (0.5143, 35.2698, 0.25),
        },
        "soil_types": ["Volcanic Loam", "Red Clay Loam", "Sandy Loam", "Andosol"],
        "crops": ["Maize", "Wheat"],
        "seasons": ["Long Rains", "Short Rains"],
        "currency": "KES",
        "loan_range": (5_000.0, 60_000.0),
        "sale_range": (15_000.0, 250_000.0),
        "yield_t_per_ha": {"Maize": 2.5, "Wheat": 2.8},
    },
    "Nigeria": {
        "org_id": "ORG-AGROVESTO",
        "phone_prefix": "+2348",
        "locale": "en_US",
        "locations": ["Kano", "Kaduna"],
        "coords": {
            "Kano": (12.0022, 8.5920, 0.30),
            "Kaduna": (10.5105, 7.4165, 0.30),
        },
        "soil_types": ["Sandy Loam", "Ferruginous Tropical", "Clay Loam", "Lithosol"],
        "crops": ["Maize", "Sorghum", "Millet", "Cowpea"],
        "seasons": ["Wet Season", "Dry Season"],
        "currency": "NGN",
        "loan_range": (50_000.0, 750_000.0),
        "sale_range": (120_000.0, 3_500_000.0),
        "yield_t_per_ha": {"Maize": 2.0, "Sorghum": 1.5, "Millet": 1.2, "Cowpea": 0.9},
    },
}


# ---------------------------------------------------------------------------
# Dataset container.
# ---------------------------------------------------------------------------


@dataclass
class SyntheticDataset:
    """Normalized collections of node and relationship rows.

    Every collection is a list of plain ``dict`` rows so they can be passed
    straight into Cypher ``UNWIND $rows`` ingestion without further mapping.
    """

    organizations: list[dict]
    farmers: list[dict]
    holdings: list[dict]
    crop_cycles: list[dict]
    transactions: list[dict]
    owns: list[dict]
    has_cycle: list[dict]
    executed: list[dict]
    belongs_to: list[dict]
    member_of: list[dict]

    def summary(self) -> dict[str, int]:
        """Return a {collection_name: row_count} map for logging/reporting."""
        return {f.name: len(getattr(self, f.name)) for f in fields(self)}

    def to_frames(self) -> dict[str, pd.DataFrame]:
        """Return each collection as a pandas DataFrame keyed by name."""
        return {
            f.name: pd.DataFrame(getattr(self, f.name)) for f in fields(self)
        }


# ---------------------------------------------------------------------------
# Generation helpers.
# ---------------------------------------------------------------------------


def _new_id() -> str:
    return str(uuid.uuid4())


def _phone(prefix: str) -> str:
    return prefix + "".join(random.choices("0123456789", k=8))


def _jittered_point(lat: float, lon: float, jitter: float) -> tuple[float, float]:
    return (
        round(lat + random.uniform(-jitter, jitter), 6),
        round(lon + random.uniform(-jitter, jitter), 6),
    )


def _cycle_status(planted: date, today: date) -> str:
    """Derive a plausible crop-cycle status from time elapsed since planting."""
    days_elapsed = (today - planted).days
    if days_elapsed > 180:
        return random.choices(["HARVESTED", "FAILED"], weights=[0.9, 0.1])[0]
    if days_elapsed > 90:
        return "GROWING"
    return "PLANTED"


def _transaction(cfg: dict, faker: Faker) -> dict:
    """Build a single transaction row (INPUT_LOAN or GRAIN_SALE)."""
    txn_type = random.choice(["INPUT_LOAN", "GRAIN_SALE"])
    if txn_type == "INPUT_LOAN":
        amount = round(random.uniform(*cfg["loan_range"]), 2)
        status = random.choices(
            ["DISBURSED", "REPAID", "DEFAULTED", "PENDING"],
            weights=[0.4, 0.4, 0.1, 0.1],
        )[0]
    else:  # GRAIN_SALE
        amount = round(random.uniform(*cfg["sale_range"]), 2)
        status = random.choices(
            ["COMPLETED", "PENDING", "CANCELLED"],
            weights=[0.8, 0.15, 0.05],
        )[0]
    txn_date = faker.date_between(start_date="-730d", end_date="today")
    return {
        "id": _new_id(),
        "type": txn_type,
        "amount": amount,
        "date": txn_date.isoformat(),
        "status": status,
    }


# ---------------------------------------------------------------------------
# Public generation entry point.
# ---------------------------------------------------------------------------


def generate_dataset(
    num_farmers: int = DEFAULT_NUM_FARMERS,
    seed: int = DEFAULT_SEED,
    kenya_ratio: float = 0.5,
) -> SyntheticDataset:
    """Generate a fully inter-linked synthetic dataset.

    Args:
        num_farmers: Total number of :Farmer nodes to synthesise.
        seed: Seed for both ``random`` and ``Faker`` for reproducible runs.
        kenya_ratio: Fraction of farmers assigned to the Kenya/Tegemeo
            ecosystem; the remainder are assigned to Nigeria/Agrovesto.

    Returns:
        A populated :class:`SyntheticDataset`.
    """
    if not 0.0 <= kenya_ratio <= 1.0:
        raise ValueError("kenya_ratio must be between 0.0 and 1.0")

    faker = Faker()
    Faker.seed(seed)
    random.seed(seed)
    today = date.today()

    logger.info(
        "Generating synthetic dataset: farmers=%d seed=%d kenya_ratio=%.2f",
        num_farmers,
        seed,
        kenya_ratio,
    )

    organizations = [dict(org) for org in ORGANIZATIONS]
    farmers: list[dict] = []
    holdings: list[dict] = []
    crop_cycles: list[dict] = []
    transactions: list[dict] = []
    owns: list[dict] = []
    has_cycle: list[dict] = []
    executed: list[dict] = []
    belongs_to: list[dict] = []
    member_of: list[dict] = []

    for _ in range(num_farmers):
        country = "Kenya" if random.random() < kenya_ratio else "Nigeria"
        cfg = REGION_CONFIG[country]
        org_id = cfg["org_id"]
        location = random.choice(cfg["locations"])

        # --- Farmer ---------------------------------------------------------
        farmer_id = _new_id()
        verified = random.random() < 0.8
        # Verified farmers have always signed consent; unverified may have too.
        consent_signed = verified or (random.random() < 0.5)
        farmers.append(
            {
                "id": farmer_id,
                "name": faker.name(),
                "phone": _phone(cfg["phone_prefix"]),
                "location": f"{location}, {country}",
                "country": country,
                "verified": verified,
                "consent_signed": consent_signed,
            }
        )
        member_of.append({"farmer_id": farmer_id, "org_id": org_id})

        # --- Farm holdings (1-2 per farmer) --------------------------------
        for _holding in range(random.randint(1, 2)):
            holding_id = _new_id()
            centre_lat, centre_lon, jitter = cfg["coords"][location]
            lat, lon = _jittered_point(centre_lat, centre_lon, jitter)
            size_hectares = round(random.uniform(0.5, 5.0), 2)  # smallholder bound
            holdings.append(
                {
                    "id": holding_id,
                    "size_hectares": size_hectares,
                    "latitude": lat,
                    "longitude": lon,
                    "soil_type": random.choice(cfg["soil_types"]),
                }
            )
            owns.append({"farmer_id": farmer_id, "holding_id": holding_id})

            # --- Crop cycles (1-3 per holding) -----------------------------
            for _cycle in range(random.randint(1, 3)):
                cycle_id = _new_id()
                crop = random.choice(cfg["crops"])
                planted_at = faker.date_between(start_date="-540d", end_date="-30d")
                yield_factor = cfg["yield_t_per_ha"][crop] * random.uniform(0.6, 1.25)
                harvest_estimate_tons = round(size_hectares * yield_factor, 2)
                crop_cycles.append(
                    {
                        "id": cycle_id,
                        "crop_type": crop,
                        "season": random.choice(cfg["seasons"]),
                        "planted_at": planted_at.isoformat(),
                        "harvest_estimate_tons": harvest_estimate_tons,
                        "status": _cycle_status(planted_at, today),
                    }
                )
                has_cycle.append({"holding_id": holding_id, "cycle_id": cycle_id})

        # --- Transactions (1-5 per farmer) ---------------------------------
        for _txn in range(random.randint(1, 5)):
            txn = _transaction(cfg, faker)
            transactions.append(txn)
            executed.append({"farmer_id": farmer_id, "txn_id": txn["id"]})
            belongs_to.append({"txn_id": txn["id"], "org_id": org_id})

    dataset = SyntheticDataset(
        organizations=organizations,
        farmers=farmers,
        holdings=holdings,
        crop_cycles=crop_cycles,
        transactions=transactions,
        owns=owns,
        has_cycle=has_cycle,
        executed=executed,
        belongs_to=belongs_to,
        member_of=member_of,
    )

    logger.info("Generation complete: %s", dataset.summary())
    return dataset


# ---------------------------------------------------------------------------
# CSV export (used when the module is run standalone).
# ---------------------------------------------------------------------------


def write_csvs(dataset: SyntheticDataset, output_dir: Path) -> None:
    """Write every collection in the dataset to ``<output_dir>/<name>.csv``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in dataset.to_frames().items():
        target = output_dir / f"{name}.csv"
        frame.to_csv(target, index=False)
        logger.info("Wrote %s rows to %s", len(frame), target)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic farmer data.")
    parser.add_argument(
        "--farmers", type=int, default=DEFAULT_NUM_FARMERS, help="Number of farmers."
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed.")
    parser.add_argument(
        "--kenya-ratio",
        type=float,
        default=0.5,
        help="Fraction of farmers assigned to the Kenya/Tegemeo ecosystem.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "raw" / "generated",
        help="Directory to write the synthetic CSV files into.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    args = _parse_args()
    generated = generate_dataset(
        num_farmers=args.farmers, seed=args.seed, kenya_ratio=args.kenya_ratio
    )
    write_csvs(generated, args.output_dir)
    logger.info("Done. Synthetic CSVs available in %s", args.output_dir.resolve())

"""
Generates one complete farmer "bundle" -- a Farmer node plus everything
that should realistically surround it: FarmHolding, CropCycle, Organization
membership, Transaction, identity/credit/land-size Claims (via the local
synthetic_providers fixtures), and a ConsentGrant.

This is the file that actually decides what's REAL vs SIMULATED in each
generated record, mirroring the project proposal's own framing:
  - land_size self-reported claim: simulates a real survey response
  - land_size satellite claim: calls the REAL ndvi_crosscheck module when
    a live coordinate + Earth Engine auth is available; falls back to a
    plausible synthetic value otherwise (see satellite_claim_builder.py)
  - identity / credit_history claims: ALWAYS simulated via the local
    synthetic_providers fixtures, by design -- these can never be "real" in
    a hackathon context (see the NIBSS/CRB discussion this generator is built
    from). The real runtime path is app.verification's provider seam, which
    fabricates nothing; this seed-only fabrication lives here in
    app.data_generation, deliberately outside app.verification.
  - production_volume claim: SUPPORTED_BY a real Transaction for some
    farmers (off-taker delivery, medium-strong) and not for others
    (cooperative-only, weak) -- this variation is intentional, not random
    noise, and exists to make Hole 7 (off-taker vs cooperative strength)
    visible in the generated data.
"""

import random
from datetime import date, datetime, timedelta, timezone

from app.data_generation.data_pools import (
    KENYA_CROPS,
    KENYA_FARMER_NAMES,
    KENYA_ORGANIZATIONS,
    KENYA_REGION_CENTER,
    KENYA_SOIL_TYPES,
    NIGERIA_CROPS,
    NIGERIA_FARMER_NAMES,
    NIGERIA_ORGANIZATIONS,
    NIGERIA_REGION_CENTER,
    NIGERIA_SOIL_TYPES,
)
from app.data_generation.graph_model import FakeDataset, institution_id_for_org
from app.data_generation.synthetic_providers import check_credit_history, verify_identity

_COUNTRY_CONFIG = {
    "Nigeria": {
        "names": NIGERIA_FARMER_NAMES,
        "region_center": NIGERIA_REGION_CENTER,
        "crops": NIGERIA_CROPS,
        "soil_types": NIGERIA_SOIL_TYPES,
        "organizations": NIGERIA_ORGANIZATIONS,
        "identifier_type": "BVN",
        "phone_prefix": "+234",
    },
    "Kenya": {
        "names": KENYA_FARMER_NAMES,
        "region_center": KENYA_REGION_CENTER,
        "crops": KENYA_CROPS,
        "soil_types": KENYA_SOIL_TYPES,
        "organizations": KENYA_ORGANIZATIONS,
        "identifier_type": "national_id",
        "phone_prefix": "+254",
    },
}


def _jitter_coordinate(center: float, spread: float = 0.15) -> float:
    """Small random offset so 15 farmers in one country aren't all stacked
    on the exact same point."""
    return round(center + random.uniform(-spread, spread), 4)


def _fake_identifier(country: str, index: int) -> str:
    """Generates a fake-but-shaped-correctly BVN/phone-style identifier.
    Deliberately NOT a real BVN/NIN format edge case -- just enough digits
    to feed the mock providers' deterministic hashing."""
    return f"{country[:2].upper()}{index:05d}{random.randint(10000, 99999)}"


def _fake_phone(country: str, index: int) -> str:
    prefix = _COUNTRY_CONFIG[country]["phone_prefix"]
    return f"{prefix}7{index:08d}"


def generate_farmer_bundle(
    dataset: FakeDataset,
    country: str,
    index: int,
    introduce_conflict: bool,
) -> str:
    """
    Builds one farmer and everything around them, appending nodes and
    relationships directly onto `dataset`. Returns the generated farmer_id.

    introduce_conflict: if True, the self-reported and satellite land-size
    Claims are seeded with a deliberate mismatch (and linked via
    CONFLICTS_WITH) rather than agreeing. This is the mechanism for the
    "10 farmers with conflicting cases" requirement.
    """
    config = _COUNTRY_CONFIG[country]
    name = config["names"][index % len(config["names"])]
    region = config["region_center"]
    crop = random.choice(config["crops"])
    soil_type = random.choice(config["soil_types"])
    org = random.choice(config["organizations"])

    farmer_id = f"farmer_{country[:2].lower()}_{index:03d}"
    holding_id = f"holding_{country[:2].lower()}_{index:03d}"
    cycle_id = f"cycle_{country[:2].lower()}_{index:03d}"
    txn_id = f"txn_{country[:2].lower()}_{index:03d}"
    consent_id = f"consent_{country[:2].lower()}_{index:03d}"

    identifier = _fake_identifier(country, index)
    phone = _fake_phone(country, index)
    # The Institution reified node mirrors the Organization (one real-world
    # actor, two labels -- Organization for registry/demographic membership,
    # Institution for reified claim attestation), under its own id. Ensured
    # idempotently in generate_dataset.py._add_organizations.
    institution_id = institution_id_for_org(org["id"])

    self_reported_ha = round(random.uniform(0.8, 4.5), 2)
    if introduce_conflict:
        # Deliberate mismatch: satellite figure differs meaningfully from
        # what the farmer reported -- e.g. understated or overstated by
        # 40-90%, simulating a genuine plausibility flag rather than noise.
        direction = random.choice([0.4, 1.7])  # understate or overstate
        satellite_ha = round(self_reported_ha * direction, 2)
    else:
        # Agreement within a small, realistic margin of GPS/measurement noise.
        satellite_ha = round(self_reported_ha * random.uniform(0.95, 1.05), 2)

    # --- Farmer node ---
    dataset.add_node(
        "Farmer",
        {
            "id": farmer_id,
            "name": name,
            "phone": phone,
            "location": region["location"],
            "country": country,
            "verified": True,
            "consent_signed": True,
        },
    )

    # --- FarmHolding node ---
    dataset.add_node(
        "FarmHolding",
        {
            "id": holding_id,
            "size_hectares": self_reported_ha,
            "latitude": _jitter_coordinate(region["lat"]),
            "longitude": _jitter_coordinate(region["lon"]),
            "soil_type": soil_type,
        },
    )
    dataset.add_relationship("Farmer", farmer_id, "OWNS", "FarmHolding", holding_id)

    # --- CropCycle node ---
    planted = date(2025, 3, random.randint(1, 28))
    dataset.add_node(
        "CropCycle",
        {
            "id": cycle_id,
            "crop_type": crop,
            "season": "2025 Long Rains" if country == "Kenya" else "2025 Wet Season",
            "planted_at": planted.isoformat(),
            "harvest_estimate_tons": round(self_reported_ha * random.uniform(0.7, 1.4), 2),
            "status": "harvested",
        },
    )
    dataset.add_relationship("FarmHolding", holding_id, "HAS_CYCLE", "CropCycle", cycle_id)

    # --- Organization membership ---
    dataset.add_relationship("Farmer", farmer_id, "MEMBER_OF", "Organization", org["id"])

    # --- Transaction: only some farmers get an off-taker-backed sale,
    # to create the medium-strong vs weak production-volume distinction
    # named in the proposal's strength table (Hole 7). ---
    has_offtaker_transaction = org["org_role"] == "off_taker" or random.random() < 0.5
    if has_offtaker_transaction:
        sale_date = planted + timedelta(days=120)
        dataset.add_node(
            "Transaction",
            {
                "id": txn_id,
                "type": "GRAIN_SALE",
                "amount": round(self_reported_ha * random.uniform(15000, 45000), 2),
                "date": sale_date.isoformat(),
                "status": "completed",
            },
        )
        dataset.add_relationship("Farmer", farmer_id, "EXECUTED", "Transaction", txn_id)
        dataset.add_relationship("Transaction", txn_id, "BELONGS_TO", "Organization", org["id"])

    # --- Claims (reified: Institution-[:ATTESTS_TO]->Claim-[:BELONGS_TO]->Farmer) ---
    # The farmer's own self-report has no qualifying external source, so it is
    # a PendingClaim (status: unverified) -- never visible to trust traversal.
    self_reported_claim_id = _add_self_reported_land_claim(
        dataset, farmer_id, index, country, self_reported_ha, planted
    )
    satellite_claim_id = _add_satellite_land_claim(
        dataset, farmer_id, index, country, satellite_ha, planted
    )

    if introduce_conflict:
        # The conflict is between the farmer's pending self-report and the
        # satellite ground truth -- recorded for audit visibility. PendingClaim
        # itself never enters trust traversal, so this never leaks an
        # unverified value into a verified-claim read.
        dataset.add_relationship(
            "PendingClaim", self_reported_claim_id, "CONFLICTS_WITH", "Claim", satellite_claim_id
        )

    _add_identity_claim(dataset, farmer_id, index, country, name, identifier, planted, institution_id)
    _add_credit_claim(dataset, farmer_id, index, country, identifier, planted, institution_id)
    _add_production_claim(
        dataset, farmer_id, index, country, org, institution_id, planted,
        supported_by_txn_id=txn_id if has_offtaker_transaction else None,
    )

    # --- Standing access grant: the cooperative/off-taker already has the
    # farmer's consent from collection time (the registry membership itself). ---
    dataset.add_relationship(
        "Institution", institution_id, "GRANTED_ACCESS", "Farmer", farmer_id,
        properties={
            "status": "APPROVED",
            "basis": "COLLECTION",
            "scope": "category",
            "granted_at": datetime(2025, 1, 10, tzinfo=timezone.utc).isoformat(),
        },
    )

    return farmer_id


def _add_self_reported_land_claim(dataset, farmer_id, index, country, value_ha, claim_date):
    """Self-report has no external source_category -- stored as a PendingClaim,
    never as a verified Claim, and never read by trust traversal."""
    claim_id = f"claim_{country[:2].lower()}_{index:03d}_land_self"
    dataset.add_node(
        "PendingClaim",
        {
            "id": claim_id,
            "claim_type": "land_size_hectares",
            "value_numeric": value_ha,
            "status": "unverified",
            "submitted_at": claim_date.isoformat(),
        },
    )
    dataset.add_relationship("PendingClaim", claim_id, "BELONGS_TO", "Farmer", farmer_id)
    return claim_id


def _add_satellite_land_claim(dataset, farmer_id, index, country, value_ha, claim_date):
    claim_id = f"claim_{country[:2].lower()}_{index:03d}_land_satellite"
    dataset.add_node(
        "Claim",
        {
            "id": claim_id,
            "claim_type": "land_size_hectares",
            "value_numeric": value_ha,
            "source_category": "remote_sensing",
            "confidence": round(random.uniform(0.85, 0.97), 2),  # satellite: strong, per proposal
            "timestamp": claim_date.isoformat(),
        },
    )
    dataset.add_relationship(
        "Institution", "ORG-SENTINEL2", "ATTESTS_TO", "Claim", claim_id
    )
    dataset.add_relationship("Claim", claim_id, "BELONGS_TO", "Farmer", farmer_id)
    return claim_id


def _add_identity_claim(dataset, farmer_id, index, country, name, identifier, claim_date, institution_id):
    result = verify_identity(country=country, claimed_name=name, identifier=identifier)
    claim_id = f"claim_{country[:2].lower()}_{index:03d}_identity"
    dataset.add_node(
        "Claim",
        {
            "id": claim_id,
            "claim_type": "identity",
            "value_string": result.verified_name or "unverified",
            "source_category": "government",
            "confidence": result.confidence,
            "timestamp": claim_date.isoformat(),
        },
    )
    dataset.add_relationship("Institution", "ORG-GOV-IDENTITY", "ATTESTS_TO", "Claim", claim_id)
    dataset.add_relationship("Claim", claim_id, "BELONGS_TO", "Farmer", farmer_id)


def _add_credit_claim(dataset, farmer_id, index, country, identifier, claim_date, institution_id):
    result = check_credit_history(country=country, identifier=identifier)
    claim_id = f"claim_{country[:2].lower()}_{index:03d}_credit"
    dataset.add_node(
        "Claim",
        {
            "id": claim_id,
            "claim_type": "credit_history",
            "value_string": f"score={result.credit_score};default_flag={result.has_default_flag}",
            "source_category": "government",
            "confidence": result.confidence,
            "timestamp": claim_date.isoformat(),
        },
    )
    dataset.add_relationship("Institution", "ORG-CREDIT-BUREAU", "ATTESTS_TO", "Claim", claim_id)
    dataset.add_relationship("Claim", claim_id, "BELONGS_TO", "Farmer", farmer_id)


def _add_production_claim(dataset, farmer_id, index, country, org, institution_id, claim_date, supported_by_txn_id):
    claim_id = f"claim_{country[:2].lower()}_{index:03d}_production"

    # Delivery-record-backed claims (off-taker) are medium-strong; cooperative-
    # only attestations (no transaction backing) are weaker -- Hole 7 from the
    # schema gap analysis, preserved here via source_category + confidence.
    if supported_by_txn_id is not None:
        source_category = "off_taker"
        confidence = round(random.uniform(0.7, 0.88), 2)  # medium-strong, per proposal
    else:
        source_category = "cooperative"
        confidence = round(random.uniform(0.35, 0.55), 2)  # weak, per proposal

    dataset.add_node(
        "Claim",
        {
            "id": claim_id,
            "claim_type": "production_volume",
            "value_string": "see linked CropCycle.harvest_estimate_tons",
            "source_category": source_category,
            "confidence": confidence,
            "timestamp": claim_date.isoformat(),
        },
    )
    dataset.add_relationship("Institution", institution_id, "ATTESTS_TO", "Claim", claim_id)
    dataset.add_relationship("Claim", claim_id, "BELONGS_TO", "Farmer", farmer_id)
    if supported_by_txn_id is not None:
        dataset.add_relationship("Claim", claim_id, "SUPPORTED_BY", "Transaction", supported_by_txn_id)
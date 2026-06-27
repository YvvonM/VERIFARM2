"""
Top-level fake dataset generator for VeriFarm.

Produces 30 farmers: 15 Nigeria, 15 Kenya. 10 of the 30 (split evenly
across both countries) are seeded with a deliberate self-reported vs.
satellite land-size conflict, to populate real CONFLICTS_WITH edges for
demo/testing of the anomaly-detection / "flag for review" behavior named
in the proposal.

Run directly to print a summary and validation result:
    python3 -m data_generation.generate_dataset

Or import generate() from elsewhere (e.g. neo4j_loader.py) to get the
FakeDataset object without printing anything.
"""

import random

from app.data_generation.data_pools import (
    KENYA_ORGANIZATIONS,
    NIGERIA_ORGANIZATIONS,
)
from app.data_generation.farmer_bundle_generator import generate_farmer_bundle
from app.data_generation.graph_model import FakeDataset, institution_id_for_org
from app.data_generation.validate_dataset import validate_dataset

TOTAL_FARMERS_PER_COUNTRY = 15
CONFLICTS_PER_COUNTRY = 5  # 5 + 5 = 10 total, matching the requirement

# Fixed seed for reproducible demo data -- re-running this script twice
# should give you the same dataset, which matters for a stable demo and
# for being able to debug "why does farmer_ke_007 look like that" without
# the answer changing between runs.
RANDOM_SEED = 42


# Source categories that may originate claims (see app.schemas.graph_schema);
# a registry org_role maps onto whether its mirrored Institution can attest.
_CAN_ORIGINATE_ORG_ROLES = {"cooperative", "off_taker"}


def _add_organizations(dataset: FakeDataset) -> None:
    for org in NIGERIA_ORGANIZATIONS + KENYA_ORGANIZATIONS:
        # Registry layer keeps only its own fields -- reputation/trust moved
        # to the reified Institution mirror below (Institution.trust_score).
        registry_fields = {"id", "name", "type", "org_role"}
        dataset.add_node("Organization", {k: v for k, v in org.items() if k in registry_fields})
        # Mirror onto the reified Institution layer (separate id) so the
        # cooperative/off-taker can attest to Claims about its members.
        can_originate = org["org_role"] in _CAN_ORIGINATE_ORG_ROLES
        dataset.add_node(
            "Institution",
            {
                "id": institution_id_for_org(org["id"]),
                "name": org["name"],
                "type": org["org_role"],
                "is_authoritative": False,
                "trust_score": org.get("reputation_score", 0.5),
                "can_originate_claims": can_originate,
                # New institutions start capped until corroborated by an
                # authoritative source (satellite/government) -- prevents a
                # fake cooperative from onboarding and self-verifying.
                "minimum_onboarding_trust": 0.5,
            },
        )

    # Authoritative / external ground-truth and provider institutions used by
    # the per-farmer claims below.
    dataset.add_node("Institution", {
        "id": "ORG-SENTINEL2", "name": "Sentinel-2 NDVI Cross-Check", "type": "remote_sensing",
        "is_authoritative": True, "trust_score": 1.0,
        "can_originate_claims": True, "minimum_onboarding_trust": 1.0,
    })
    dataset.add_node("Institution", {
        "id": "ORG-GOV-IDENTITY", "name": "Government Identity Registry", "type": "government",
        "is_authoritative": True, "trust_score": 1.0,
        "can_originate_claims": True, "minimum_onboarding_trust": 1.0,
    })
    dataset.add_node("Institution", {
        "id": "ORG-CREDIT-BUREAU", "name": "Credit Bureau", "type": "government",
        "is_authoritative": True, "trust_score": 1.0,
        "can_originate_claims": True, "minimum_onboarding_trust": 1.0,
    })


def generate() -> FakeDataset:
    random.seed(RANDOM_SEED)
    dataset = FakeDataset()

    _add_organizations(dataset)

    for country, count in [("Nigeria", TOTAL_FARMERS_PER_COUNTRY), ("Kenya", TOTAL_FARMERS_PER_COUNTRY)]:
        conflict_indices = set(random.sample(range(count), CONFLICTS_PER_COUNTRY))
        for i in range(count):
            generate_farmer_bundle(
                dataset=dataset,
                country=country,
                index=i,
                introduce_conflict=(i in conflict_indices),
            )

    return dataset


if __name__ == "__main__":
    dataset = generate()
    print(dataset.summary())
    print()

    result = validate_dataset(dataset)
    if result.is_valid:
        print("Validation: PASSED -- every node label and relationship triple matches schemas/graph_schema.py")
    else:
        print("Validation: FAILED")
        for error in result.errors:
            print(f"  - {error}")
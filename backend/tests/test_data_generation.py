"""
Tests for app/data_generation/ -- the fake VeriFarm dataset generator.

Run with:
    cd backend
    pytest tests/test_data_generation.py -v

These tests do NOT touch Neo4j -- they only exercise generate() (in-memory)
and validate_dataset(), which is exactly why generate() and neo4j_loader()
are kept as separate functions in the first place. No DB connection or
.env file is required to run this suite.
"""

import pytest

from app.data_generation.generate_dataset import (
    CONFLICTS_PER_COUNTRY,
    TOTAL_FARMERS_PER_COUNTRY,
    generate,
)
from app.data_generation.validate_dataset import validate_dataset
from app.schemas.graph_schema import NODE_SCHEMA, RELATIONSHIP_SCHEMA


@pytest.fixture(scope="module")
def dataset():
    """Generate once and reuse across tests in this file -- generation is
    deterministic (fixed RANDOM_SEED), so sharing is safe and avoids
    regenerating 30 farmers once per test."""
    return generate()


# ---------------------------------------------------------------------------
# Schema validity -- the most important property: every label and
# relationship triple actually exists in the agreed schema.
# ---------------------------------------------------------------------------

def test_dataset_passes_schema_validation(dataset):
    result = validate_dataset(dataset)
    assert result.is_valid, f"Schema validation failed: {result.errors}"


def test_no_unknown_node_labels(dataset):
    known_labels = set(NODE_SCHEMA.keys())
    used_labels = {node.label for node in dataset.nodes}
    assert used_labels <= known_labels


def test_no_unknown_relationship_triples(dataset):
    known_triples = set(RELATIONSHIP_SCHEMA)
    used_triples = {
        (rel.start_label, rel.rel_type, rel.end_label) for rel in dataset.relationships
    }
    assert used_triples <= known_triples


# ---------------------------------------------------------------------------
# Counts -- catches accidental regressions in farmer count, country split,
# or conflict count if the generator is edited later.
# ---------------------------------------------------------------------------

def test_total_farmer_count(dataset):
    farmers = [n for n in dataset.nodes if n.label == "Farmer"]
    assert len(farmers) == TOTAL_FARMERS_PER_COUNTRY * 2


def test_country_split_is_even(dataset):
    farmers = [n for n in dataset.nodes if n.label == "Farmer"]
    nigeria_count = sum(1 for f in farmers if f.properties["country"] == "Nigeria")
    kenya_count = sum(1 for f in farmers if f.properties["country"] == "Kenya")
    assert nigeria_count == TOTAL_FARMERS_PER_COUNTRY
    assert kenya_count == TOTAL_FARMERS_PER_COUNTRY


def test_conflict_count_matches_requirement(dataset):
    conflicts = [r for r in dataset.relationships if r.rel_type == "CONFLICTS_WITH"]
    assert len(conflicts) == CONFLICTS_PER_COUNTRY * 2


def test_every_farmer_has_exactly_one_holding(dataset):
    owns_rels = [r for r in dataset.relationships if r.rel_type == "OWNS"]
    farmer_ids_with_holding = {r.start_id for r in owns_rels}
    farmer_ids = {n.properties["id"] for n in dataset.nodes if n.label == "Farmer"}
    assert farmer_ids_with_holding == farmer_ids


def test_every_farmer_has_identity_and_credit_claims(dataset):
    claims = [n for n in dataset.nodes if n.label == "Claim"]
    identity_claims = [c for c in claims if c.properties["claim_type"] == "identity"]
    credit_claims = [c for c in claims if c.properties["claim_type"] == "credit_history"]
    farmer_count = TOTAL_FARMERS_PER_COUNTRY * 2
    assert len(identity_claims) == farmer_count
    assert len(credit_claims) == farmer_count


def test_no_self_reported_source_category(dataset):
    """self_reported must never appear as a Claim source_category -- an
    unsourced figure is a PendingClaim, not a verified Claim."""
    claims = [n for n in dataset.nodes if n.label == "Claim"]
    for claim in claims:
        assert claim.properties.get("source_category") != "self_reported"
        assert claim.properties.get("source_category") in {
            "cooperative", "off_taker", "government", "remote_sensing", "field_officer",
        }


def test_self_reported_land_size_is_a_pending_claim(dataset):
    """The farmer's own land-size figure has no external source, so it must be
    a PendingClaim (status unverified), never a verified Claim."""
    pending = [n for n in dataset.nodes if n.label == "PendingClaim"]
    assert len(pending) == TOTAL_FARMERS_PER_COUNTRY * 2
    for p in pending:
        assert p.properties["status"] == "unverified"


# ---------------------------------------------------------------------------
# Content correctness -- catches the "structurally valid but semantically
# wrong" failure mode (e.g. the buffer-radius bug from earlier in this
# project, which passed schema validation but was still wrong).
# ---------------------------------------------------------------------------

def test_satellite_claims_have_higher_confidence_than_self_reported(dataset):
    """
    Per the proposal's strength table, satellite checks are "Strong". The
    farmer's self-report carries no confidence at all now (it's an unverified
    PendingClaim) -- so this asserts satellite confidence clears a high bar
    instead of comparing against a self-reported number that no longer exists
    as a Claim.
    """
    claims = [n for n in dataset.nodes if n.label == "Claim" and n.properties["claim_type"] == "land_size_hectares"]
    satellite = [c for c in claims if c.properties["source_category"] == "remote_sensing"]

    avg_satellite_confidence = sum(c.properties["confidence"] for c in satellite) / len(satellite)
    assert avg_satellite_confidence > 0.8


def test_identity_claims_use_country_correct_mock_provider(dataset):
    farmers_by_id = {n.properties["id"]: n.properties for n in dataset.nodes if n.label == "Farmer"}
    identity_claims = [n for n in dataset.nodes if n.label == "Claim" and n.properties["claim_type"] == "identity"]

    belongs_to_rels = {
        r.start_id: r.end_id for r in dataset.relationships
        if r.rel_type == "BELONGS_TO" and r.start_label == "Claim" and r.end_label == "Farmer"
    }

    checked = 0
    for claim in identity_claims:
        farmer_id = belongs_to_rels.get(claim.properties["id"])
        if farmer_id is None:
            continue
        country = farmers_by_id[farmer_id]["country"]
        checked += 1

    assert checked == TOTAL_FARMERS_PER_COUNTRY * 2


def test_no_excluded_scoring_fields_present(dataset):
    """
    Per the proposal's responsible-AI section (and EXCLUDED_FROM_SCORING in
    graph_schema.py), gender/ethnicity must never appear on any generated
    node -- not even as harmless-seeming demo flavor.
    """
    from app.schemas.graph_schema import EXCLUDED_FROM_SCORING

    for node in dataset.nodes:
        for excluded_field in EXCLUDED_FROM_SCORING:
            assert excluded_field not in node.properties, (
                f"{node.label} node {node.properties.get('id')} has excluded field '{excluded_field}'"
            )


def test_production_claims_have_source_category_matching_offtaker_backing(dataset):
    """
    Claims backed by a real off-taker transaction (SUPPORTED_BY) should carry
    source_category='off_taker' (medium-strong); claims with no transaction
    backing should carry source_category='cooperative' (weak) -- this is
    Hole 7 from the schema gap analysis, and this test is what keeps that
    distinction from silently disappearing in a future edit.
    """
    production_claims = [
        n for n in dataset.nodes if n.label == "Claim" and n.properties["claim_type"] == "production_volume"
    ]
    supported_by_rels = {
        r.start_id for r in dataset.relationships if r.rel_type == "SUPPORTED_BY"
    }

    for claim in production_claims:
        claim_id = claim.properties["id"]
        if claim_id in supported_by_rels:
            assert claim.properties["source_category"] == "off_taker"
        else:
            assert claim.properties["source_category"] == "cooperative"


def test_generation_is_reproducible():
    """Same RANDOM_SEED should produce an identical dataset across runs --
    important for stable demo data."""
    d1 = generate()
    d2 = generate()
    ids_1 = sorted(n.properties["id"] for n in d1.nodes)
    ids_2 = sorted(n.properties["id"] for n in d2.nodes)
    assert ids_1 == ids_2
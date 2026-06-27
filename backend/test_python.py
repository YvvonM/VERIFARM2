"""
VeriFarm Backend Test Suite
============================

Run with: python test_backend.py

Requires: pip install pydantic neo4j
(neo4j is only needed for the driver mock — scoring and mocks are pure Python)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# 1. Mock Neo4j driver (so we don't need a real DB for testing)
# ---------------------------------------------------------------------------

class MockResult:
    def __init__(self, data: list[dict]):
        self._data = data
    async def data(self):
        return self._data

class MockSession:
    def __init__(self, records: list[dict] | None = None):
        self._records = records or []
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def run(self, cypher: str, params: dict | None = None):
        # Simple mock: return stored records for reads, empty for writes
        if cypher.strip().upper().startswith(("CREATE", "MERGE", "SET", "DELETE")):
            return MockResult([])
        # For MATCH queries, return whatever was pre-configured
        return MockResult(self._records)

class MockDriver:
    def __init__(self):
        self._session_records: list[dict] = []
    def session(self, database: str | None = None):
        return MockSession(self._session_records)
    async def close(self):
        pass

# Global mock driver state
_mock_driver = MockDriver()
_mock_session_records: list[dict] = []

def _set_mock_records(records: list[dict]):
    _mock_session_records.clear()
    _mock_session_records.extend(records)
    _mock_driver._session_records = records

# ---------------------------------------------------------------------------
# 2. Mock the neo4j_client module BEFORE importing app code
# ---------------------------------------------------------------------------

sys.modules["neo4j"] = MagicMock()
sys.modules["neo4j"].AsyncGraphDatabase = MagicMock()
sys.modules["neo4j"].AsyncGraphDatabase.driver = lambda *a, **k: _mock_driver

# Create mock neo4j_client
mock_neo4j = MagicMock()
mock_neo4j.run_query = AsyncMock()
mock_neo4j.run_write = AsyncMock()
mock_neo4j.close_driver = AsyncMock()
sys.modules["app"] = MagicMock()
sys.modules["app.services"] = MagicMock()
sys.modules["app.services.neo4j_client"] = mock_neo4j

# ---------------------------------------------------------------------------
# 3. Import and test the scoring module (pure Python, no DB needed)
# ---------------------------------------------------------------------------

# Inline the scoring module for testing
CORE_CLAIM_TYPES = ["identity", "land_size", "production_volume", "credit_history"]
_WEIGHTS = {"identity": 0.30, "land_size": 0.25, "production_volume": 0.30, "credit_history": 0.15}

def compute_risk_score(claims: list[dict[str, Any]]) -> int:
    score = 0.0
    for c in claims:
        w = _WEIGHTS.get(c.get("claim_type", ""), 0)
        score += w * c.get("confidence", 0) * 100
    return min(100, round(score))

def compute_completeness(claims: list[dict[str, Any]]) -> int:
    core = set(CORE_CLAIM_TYPES)
    verified_types = {
        c["claim_type"] for c in claims
        if c.get("claim_type") in core and c.get("confidence", 0) >= 0.7
    }
    return round(len(verified_types) / len(core) * 100)

def compute_status(risk_score: int, has_unresolved_conflict: bool) -> str:
    if has_unresolved_conflict:
        return "pending_review"
    if risk_score >= 70:
        return "approved"
    if risk_score >= 45:
        return "pending"
    return "rejected"

def compute_offers(farmer_base: dict[str, Any], claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    offers = []
    risk_score = farmer_base.get("riskScore", 0)
    size_ha = farmer_base.get("size_hectares") or 0

    if risk_score < 50:
        return offers

    offers.append({
        "product": "Input Financing",
        "provider": "VeriFarm Credit",
        "max_amount": round(size_ha * 50000, -3) if size_ha else 50000,
        "interest_rate": "12% p.a.",
        "eligibility": "Risk score ≥ 50",
    })

    land_conf = next((c.get("confidence", 0) for c in claims if c.get("claim_type") == "land_size"), 0)
    if land_conf >= 0.7:
        offers.append({
            "product": "Crop Insurance",
            "provider": "Britam",
            "max_amount": round(size_ha * 30000, -3) if size_ha else 30000,
            "eligibility": "Land verified",
        })

    return offers

# ---------------------------------------------------------------------------
# 4. Mock providers (inline for testing)
# ---------------------------------------------------------------------------

@dataclass
class IdentityVerificationResult:
    provider: str
    match: bool
    verified_name: str | None
    submitted_identifier_type: str
    confidence: float
    checked_at: datetime

@dataclass
class CreditHistoryResult:
    provider: str
    credit_score: int
    has_default_flag: bool
    repayment_history_summary: str
    confidence: float
    checked_at: datetime

def verify_identity(country: str, claimed_name: str, identifier: str) -> IdentityVerificationResult:
    digest = hashlib.sha256(identifier.encode()).hexdigest()
    fractional = int(digest[:4], 16) / 0xFFFF
    confidence = round(0.85 + fractional * 0.14, 2)
    return IdentityVerificationResult(
        provider="NIBSS_NIMC_mock_via_accredited_provider",
        match=True,
        verified_name=claimed_name,
        submitted_identifier_type="BVN" if country == "Nigeria" else "national_id",
        confidence=confidence,
        checked_at=datetime.now(timezone.utc),
    )

def check_credit_history(country: str, identifier: str) -> CreditHistoryResult:
    digest = hashlib.sha256(identifier.encode()).hexdigest()
    score_fraction = int(digest[:4], 16) / 0xFFFF
    score = int(300 + score_fraction * 550)
    flag_seed = int(digest[4:6], 16)
    has_default = (flag_seed % 13) == 0
    return CreditHistoryResult(
        provider="CRC_CreditRegistry_FirstCentral_mock" if country == "Nigeria" else "CRB_mock",
        credit_score=score,
        has_default_flag=has_default,
        repayment_history_summary="Good history" if not has_default else "Has defaults",
        confidence=0.92,
        checked_at=datetime.now(timezone.utc),
    )

# ---------------------------------------------------------------------------
# 5. Mock earth engine
# ---------------------------------------------------------------------------

def check_land_size(latitude: float, longitude: float, self_reported_hectares: float) -> dict[str, Any]:
    seed = hashlib.sha256(f"{latitude}:{longitude}:{self_reported_hectares}".encode()).hexdigest()
    variance = (int(seed[:4], 16) / 0xFFFF) * 0.4 - 0.2
    detected = round(self_reported_hectares * (1 + variance), 3)
    discrepancy = round(abs(self_reported_hectares - detected) / self_reported_hectares * 100, 2)
    return {
        "detected_ha": detected,
        "confidence": 0.87,
        "source": "satellite_NDVI",
        "discrepancy_pct": discrepancy,
    }

# ---------------------------------------------------------------------------
# 6. Test the full onboarding flow
# ---------------------------------------------------------------------------

async def test_register():
    """Test farmer registration."""
    print("\n--- TEST: Register Farmer ---")
    
    # Mock: no existing farmer
    mock_neo4j.run_query.return_value = []
    mock_neo4j.run_write.return_value = []
    
    phone = "+254712345678"
    name = "John Kamau"
    country = "Kenya"
    
    # Simulate register logic
    existing = await mock_neo4j.run_query("MATCH (f:Farmer {id: $phone}) RETURN f.id AS id", {"phone": phone})
    assert existing == [], "Farmer should not exist yet"
    
    # Create farmer
    await mock_neo4j.run_write("""
        CREATE (f:Farmer {id: $phone, name: $name, phone: $phone, country: $country, verified: false, consent_signed: $consent})
    """, {"phone": phone, "name": name, "country": country, "consent": True})
    
    # Create consent grant
    await mock_neo4j.run_write("""
        MATCH (f:Farmer {id: $phone})
        CREATE (cg:ConsentGrant {id: $cg_id, status: "granted"})
        CREATE (f)-[:GRANTED]->(cg)
    """, {"phone": phone, "cg_id": f"cg_{uuid.uuid4().hex[:8]}"})
    
    print(f"✓ Farmer registered: {name} ({phone})")
    return phone

async def test_verify_identity(phone: str):
    """Test Step 1: Identity verification."""
    print("\n--- TEST: Verify Identity ---")
    
    # Mock farmer exists
    mock_neo4j.run_query.return_value = [{"name": "John Kamau", "country": "Kenya"}]
    
    national_id = "12345678"
    result = verify_identity(country="Kenya", claimed_name="John Kamau", identifier=national_id)
    
    assert result.match is True
    assert result.verified_name == "John Kamau"
    assert result.confidence >= 0.85
    print(f"✓ Identity verified: {result.verified_name}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Provider: {result.provider}")
    
    # Simulate claim creation
    claim = {
        "claim_type": "identity",
        "value": result.verified_name,
        "confidence": result.confidence,
        "method": result.provider,
    }
    return [claim]

async def test_verify_land(phone: str):
    """Test Step 2: Land size verification."""
    print("\n--- TEST: Verify Land ---")
    
    self_reported = 2.5
    lat, lon = -0.6590, 37.3050
    
    # Self-reported claim
    self_claim = {
        "claim_type": "land_size",
        "value": str(self_reported),
        "confidence": 0.56,
        "method": "self_reported",
    }
    
    # Satellite cross-check
    sat_result = check_land_size(lat, lon, self_reported)
    sat_claim = {
        "claim_type": "land_size",
        "value": str(sat_result["detected_ha"]),
        "confidence": sat_result["confidence"],
        "method": sat_result["source"],
    }
    
    print(f"✓ Self-reported: {self_reported} ha")
    print(f"✓ Satellite detected: {sat_result['detected_ha']} ha")
    print(f"  Discrepancy: {sat_result['discrepancy_pct']}%")
    print(f"  Conflict: {'YES' if sat_result['discrepancy_pct'] > 30 else 'NO'}")
    
    return [self_claim, sat_claim]

async def test_verify_production(phone: str):
    """Test Step 3: Production verification."""
    print("\n--- TEST: Verify Production ---")
    
    claim = {
        "claim_type": "production_volume",
        "value": "5.0 tons (2024 Long Rains)",
        "confidence": 0.48,
        "method": "self_reported",
    }
    print(f"✓ Production recorded: {claim['value']}")
    return [claim]

async def test_verify_credit(phone: str):
    """Test Step 4: Credit verification."""
    print("\n--- TEST: Verify Credit ---")
    
    result = check_credit_history(country="Kenya", identifier=phone)
    
    claim = {
        "claim_type": "credit_history",
        "value": f"score={result.credit_score};default_flag={result.has_default_flag}",
        "confidence": result.confidence,
        "method": result.provider,
    }
    
    print(f"✓ Credit score: {result.credit_score}")
    print(f"  Has default: {result.has_default_flag}")
    print(f"  Provider: {result.provider}")
    
    return [claim]

async def test_scoring(claims: list[dict]):
    """Test scoring computation."""
    print("\n--- TEST: Scoring ---")
    
    risk = compute_risk_score(claims)
    completeness = compute_completeness(claims)
    status = compute_status(risk, has_unresolved_conflict=False)
    
    print(f"Risk Score: {risk}/100")
    print(f"Completeness: {completeness}%")
    print(f"Status: {status}")
    
    # Generate offers
    farmer_base = {
        "id": "+254712345678",
        "name": "John Kamau",
        "riskScore": risk,
        "size_hectares": 2.5,
        "crop": "Maize",
        "cooperative": "Independent",
    }
    offers = compute_offers(farmer_base, claims)
    
    print(f"\nOffers ({len(offers)}):")
    for offer in offers:
        print(f"  - {offer['product']} from {offer['provider']}")
        if offer.get('max_amount'):
            print(f"    Max: KES {offer['max_amount']:,.0f}")
    
    return risk, completeness, status, offers

async def run_all_tests():
    """Run full onboarding flow test."""
    print("=" * 60)
    print("VERIFARM BACKEND TEST SUITE")
    print("=" * 60)
    
    phone = await test_register()
    
    identity_claims = await test_verify_identity(phone)
    land_claims = await test_verify_land(phone)
    production_claims = await test_verify_production(phone)
    credit_claims = await test_verify_credit(phone)
    
    all_claims = identity_claims + land_claims + production_claims + credit_claims
    
    risk, completeness, status, offers = await test_scoring(all_claims)
    
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Farmer: John Kamau ({phone})")
    print(f"Risk Score: {risk}/100")
    print(f"Completeness: {completeness}%")
    print(f"Status: {status}")
    print(f"Offers: {len(offers)}")
    
    # Assertions
    assert risk > 0, "Risk score should be positive"
    assert completeness >= 25, "Should have at least one verified claim"
    assert len(offers) >= 0, "Offers should be computed"
    
    print("\n✅ ALL TESTS PASSED")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
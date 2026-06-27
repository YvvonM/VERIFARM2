"""
VeriFarm — Scoring & Offers Engine
==================================

Computes risk scores, completeness, and generates contextual loan/insurance
offers for farmers based on their verified profile.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

CORE_CLAIM_TYPES = ["identity", "land_size_hectares", "production_volume", "credit_history"]


def compute_risk_score(claims: list[dict[str, Any]]) -> int:
    """
    Composite risk score (0-100). Higher = lower risk / more fundable.
    """
    if not claims:
        return 0

    scores = []
    for c in claims:
        ct = c.get("claim_type", "")
        conf = c.get("confidence", 0)
        if ct == "identity":
            scores.append(conf * 25)
        elif ct == "land_size_hectares":
            scores.append(conf * 20)
        elif ct == "production_volume":
            scores.append(conf * 20)
        elif ct == "credit_history":
            scores.append(conf * 25)
        elif ct == "cooperative_membership":
            scores.append(conf * 10)

    return min(100, int(sum(scores)))


def compute_completeness(claims: list[dict[str, Any]]) -> int:
    """Percentage of core claim types that are present."""
    present = {c.get("claim_type") for c in claims if c.get("claim_type")}
    core_present = present.intersection(set(CORE_CLAIM_TYPES))
    return int(len(core_present) / len(CORE_CLAIM_TYPES) * 100)


def compute_risk_factors(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Break down risk score into weighted factors for UI display."""
    factors = [
        {"label": "Identity",      "weight": 25, "positive": True},
        {"label": "Land Records",  "weight": 20, "positive": True},
        {"label": "Production",    "weight": 20, "positive": True},
        {"label": "Credit History","weight": 25, "positive": True},
        {"label": "Cooperative",   "weight": 10, "positive": True},
    ]

    claim_map = {c.get("claim_type"): c for c in claims if c.get("claim_type")}

    for f in factors:
        ct = f["label"].lower().replace(" ", "_").replace("land_records", "land_size_hectares").replace("credit_history", "credit_history")
        if ct == "cooperative":
            ct = "cooperative_membership"
        c = claim_map.get(ct)
        if c:
            conf = c.get("confidence", 0)
            f["score"] = int(conf * 100)
            f["conflicted"] = bool(c.get("conflictsWithIds"))
            if f["conflicted"]:
                f["positive"] = False
        else:
            f["score"] = 0
            f["conflicted"] = False
            f["positive"] = False

    return factors


def compute_completeness_reasons(verifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build human-readable reasons for completeness gaps / conflicts."""
    reasons = []
    type_map = {
        "identity": "Identity Verification",
        "land_size_hectares": "Land Size",
        "production_volume": "Production Volume",
        "credit_history": "Credit History",
    }

    for ct, label in type_map.items():
        vs = [v for v in verifications if v.get("claim_type") == ct]
        if not vs:
            reasons.append({
                "type": label,
                "status": "missing",
                "reason": f"No {label.lower()} claim has been submitted yet.",
                "action": f"Complete the {label.lower()} verification step.",
            })
        elif any(v.get("conflictsWithIds") for v in vs):
            conflicting = [v for v in vs if v.get("conflictsWithIds")]
            reasons.append({
                "type": label,
                "status": "conflict",
                "reason": f"Conflicting {label.lower()} claims detected.",
                "action": "A credit officer must review and resolve the conflict.",
                "conflicts": [
                    {
                        "source": v.get("source", "Unknown"),
                        "value": v.get("value", "—"),
                        "confidence": v.get("confidence", 0),
                    }
                    for v in conflicting
                ],
            })
        elif all(v.get("status") == "Verified" for v in vs):
            best = max(vs, key=lambda v: v.get("confidence", 0))
            reasons.append({
                "type": label,
                "status": "verified",
                "reason": f"{label} confirmed with {int(best.get('confidence', 0) * 100)}% confidence via {best.get('source', 'unknown')}.",
            })
        else:
            best = max(vs, key=lambda v: v.get("confidence", 0))
            reasons.append({
                "type": label,
                "status": "pending",
                "reason": f"{label} submitted but confidence is low ({int(best.get('confidence', 0) * 100)}%).",
                "action": "Awaiting additional verification or officer review.",
            })

    return reasons


def compute_status(risk_score: int, has_conflict: bool) -> str:
    if has_conflict:
        return "pending"
    if risk_score >= 70 and not has_conflict:
        return "approved"
    if risk_score >= 40:
        return "pending"
    return "rejected"


def compute_status_reason(status: str, risk_score: int, has_conflict: bool, verifications: list) -> dict[str, Any] | None:
    if has_conflict:
        conflict_types = [v["type"] for v in verifications if v.get("conflictsWithIds")]
        return {
            "severity": "error",
            "title": "Unresolved Data Conflicts",
            "description": f"Conflicting claims detected in: {', '.join(conflict_types)}. A credit officer must review these before a decision can be made.",
        }
    if status == "approved":
        return {
            "severity": "success",
            "title": "Profile Approved",
            "description": f"Risk score of {risk_score}/100 meets the threshold for pre-qualified offers. Your verified data is strong across all categories.",
        }
    if status == "rejected":
        return {
            "severity": "error",
            "title": "Profile Below Threshold",
            "description": f"Risk score of {risk_score}/100 is below the minimum required. Missing verifications or low-confidence data are limiting your eligibility.",
        }
    if risk_score >= 50:
        return {
            "severity": "warning",
            "title": "Under Review",
            "description": f"Risk score of {risk_score}/100 is promising but requires additional verification before approval.",
        }
    return {
        "severity": "info",
        "title": "Incomplete Profile",
        "description": "Complete all verification steps to unlock your risk score and offers.",
    }


# ── OFFERS ENGINE ────────────────────────────────────────────────────────────

_OFFER_TEMPLATES = [
    {
        "product": "Seasonal Input Loan",
        "provider": "KCB Bank",
        "type": "loan",
        "icon": "Banknote",
        "color": "#4ADE80",
        "base_max": 150000,
        "min_risk": 50,
        "max_risk": 100,
        "interest_range": (8, 14),
        "tenor_months": (6, 12),
        "requires": ["identity", "land_size_hectares"],
        "description": "Financing for seeds, fertilizer, and pesticides for the growing season.",
    },
    {
        "product": "Crop Insurance",
        "provider": "Britam Insurance",
        "type": "insurance",
        "icon": "Umbrella",
        "color": "#38BDF8",
        "base_max": 200000,
        "min_risk": 40,
        "max_risk": 100,
        "interest_range": (2, 5),
        "tenor_months": (3, 6),
        "requires": ["identity", "land_size_hectares", "production_volume"],
        "description": "Coverage against drought, floods, and pest damage for your primary crop.",
    },
    {
        "product": "Equipment Lease",
        "provider": "Sidian Bank",
        "type": "lease",
        "icon": "Package",
        "color": "#F4A261",
        "base_max": 500000,
        "min_risk": 60,
        "max_risk": 100,
        "interest_range": (10, 16),
        "tenor_months": (12, 24),
        "requires": ["identity", "land_size_hectares", "credit_history"],
        "description": "Lease-to-own tractors, sprayers, and harvesters for mechanized farming.",
    },
    {
        "product": "Warehouse Receipt Loan",
        "provider": "Equity Bank",
        "type": "loan",
        "icon": "Building2",
        "color": "#A78BFA",
        "base_max": 300000,
        "min_risk": 55,
        "max_risk": 100,
        "interest_range": (9, 13),
        "tenor_months": (3, 6),
        "requires": ["identity", "land_size_hectares", "production_volume", "credit_history"],
        "description": "Borrow against stored harvests in certified warehouses. Low interest, fast disbursement.",
    },
    {
        "product": "Emergency Medical Cover",
        "provider": "NHIF / Britam",
        "type": "insurance",
        "icon": "Shield",
        "color": "#F87171",
        "base_max": 50000,
        "min_risk": 30,
        "max_risk": 100,
        "interest_range": (1, 3),
        "tenor_months": (12, 12),
        "requires": ["identity"],
        "description": "Basic health coverage for you and your household. Premiums deducted from harvest sales.",
    },
    {
        "product": "Cooperative Advance",
        "provider": "SACCO Network",
        "type": "loan",
        "icon": "Building2",
        "color": "#4ADE80",
        "base_max": 100000,
        "min_risk": 45,
        "max_risk": 100,
        "interest_range": (6, 10),
        "tenor_months": (3, 6),
        "requires": ["identity", "land_size_hectares"],
        "description": "Short-term advance against expected cooperative payout. No collateral required.",
    },
]


def compute_offers(farmer_base: dict[str, Any], claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Generate personalized loan/insurance offers based on risk score,
    farm size, crop type, and verified claims.
    """
    risk_score = farmer_base.get("riskScore", 0)
    size_ha = farmer_base.get("size_hectares") or 1.0
    crop = (farmer_base.get("crop") or "Mixed").lower()

    present_claim_types = {c.get("claim_type") for c in claims if c.get("claim_type")}

    offers = []
    for tmpl in _OFFER_TEMPLATES:
        # Check risk score eligibility
        if not (tmpl["min_risk"] <= risk_score <= tmpl["max_risk"]):
            continue

        # Check required claims
        missing = [r for r in tmpl["requires"] if r not in present_claim_types]
        if missing:
            continue

        # Scale max amount by farm size (capped at 3x base)
        size_multiplier = min(3.0, max(0.5, size_ha / 2.0))
        max_amount = int(tmpl["base_max"] * size_multiplier)

        # Better risk score = better rate
        rate_discount = (risk_score - 50) / 100  # 0 to 0.5 discount
        low_rate = tmpl["interest_range"][0]
        high_rate = tmpl["interest_range"][1]
        interest = round(low_rate + (high_rate - low_rate) * (1 - rate_discount), 1)

        # Match score: how well this farmer fits the product
        match = min(100, int(
            40 +  # base
            (risk_score / 100) * 30 +  # risk contribution
            (len(present_claim_types) / 4) * 20 +  # completeness contribution
            (size_multiplier / 3) * 10  # size contribution
        ))

        # Eligibility label
        if match >= 80:
            eligibility = "Pre-qualified"
        elif match >= 60:
            eligibility = "Likely eligible"
        else:
            eligibility = "Conditional"

        offers.append({
            "product": tmpl["product"],
            "provider": tmpl["provider"],
            "product_type": tmpl["type"],
            "Icon": tmpl["icon"],
            "color": tmpl["color"],
            "max_amount": max_amount,
            "interest_rate": f"{interest}% p.a.",
            "tenor": f"{tmpl['tenor_months'][0]}-{tmpl['tenor_months'][1]} months",
            "match": match,
            "eligible": match >= 70,
            "eligibility": eligibility,
            "detail": tmpl["description"],
            "requires": tmpl["requires"],
        })

    # Sort by match score descending
    offers.sort(key=lambda o: o["match"], reverse=True)
    return offers

"""In-memory catalog of financial products for the MATCH engine.

The catalog is the *only* place product definitions live. Each entry is a
declarative :class:`FinancialProduct`; adding an offer for the demo means adding
a dict entry here — the rules engine and the API need no changes.

In production this would be backed by a table / config service; the accessor
functions below are the seam that keeps callers indifferent to that.
"""

from __future__ import annotations

from app.models.products import EligibilityRule, FinancialProduct

# claim_type values must match what ingestion writes onto :Claim nodes
# (see app.verification.claim_bridge): 'land_size_hectares', 'production_volume_kg', ...
PRODUCT_CATALOG: dict[str, FinancialProduct] = {
    "input_financing_basic": FinancialProduct(
        product_id="input_financing_basic",
        lender_name="AgriCredit Microfinance",
        min_trust_score=0.5,
        eligibility_rules={
            "land_size_hectares": EligibilityRule(min=1.0, min_confidence=0.6),
        },
    ),
    "smallholder_crop_loan": FinancialProduct(
        product_id="smallholder_crop_loan",
        lender_name="Tegemeo SACCO",
        min_trust_score=0.7,
        eligibility_rules={
            "land_size_hectares": EligibilityRule(min=1.5, min_confidence=0.8),
            "production_volume_kg": EligibilityRule(min=500.0, min_confidence=0.7),
        },
    ),
    "commercial_offtake_advance": FinancialProduct(
        product_id="commercial_offtake_advance",
        lender_name="Agrovesto Capital",
        min_trust_score=0.8,
        eligibility_rules={
            "land_size_hectares": EligibilityRule(min=3.0, min_confidence=0.85),
            "production_volume_kg": EligibilityRule(min=2000.0, min_confidence=0.8),
        },
    ),
}


def list_products() -> list[FinancialProduct]:
    """Return the full product catalog."""
    return list(PRODUCT_CATALOG.values())


def get_product(product_id: str) -> FinancialProduct:
    """Return one product by id, or raise :class:`KeyError` with the known ids."""
    try:
        return PRODUCT_CATALOG[product_id]
    except KeyError as exc:
        raise KeyError(
            f"Unknown product_id {product_id!r}. Known: {sorted(PRODUCT_CATALOG)}"
        ) from exc

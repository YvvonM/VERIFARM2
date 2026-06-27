"""
Mock credit history provider.

Simulates calling a licensed credit bureau -- CRC Credit Bureau,
CreditRegistry, or FirstCentral in Nigeria; a CRB such as TransUnion Kenya,
Metropol, or Creditinfo in Kenya. No real bureau lookup is performed --
this returns a deterministic, plausible-looking credit report shape for
demo/testing purposes only.

USAGE:
    result = check_credit_history(
        country="Kenya",
        identifier="+254712345678",
    )
"""

import hashlib
from datetime import datetime, timezone

from app.data_generation.synthetic_providers.response_types import CreditHistoryResult

# Naming a specific real bureau per farmer (rather than a generic "CRB_mock")
# would overclaim a relationship with that exact institution. Naming the
# bureau CATEGORY active in that country, with _mock appended, is accurate
# without falsely implying a specific commercial relationship.
_PROVIDER_LABEL_BY_COUNTRY: dict[str, str] = {
    "Nigeria": "CRC_CreditRegistry_FirstCentral_mock",
    "Kenya": "CRB_mock",  # stands in for TransUnion Kenya / Metropol / Creditinfo
}

_DEFAULT_RATE_DENOMINATOR = 13  # ~1-in-13 chance of a seeded default flag


def _deterministic_score_and_flag(identifier: str) -> tuple[int, bool]:
    """
    Derives a stable bureau-style score (300-850 range, matching the scale
    most familiar from bureau reports generally) and a default flag from
    the identifier, so repeated calls are reproducible.
    """
    digest = hashlib.sha256(identifier.encode()).hexdigest()
    score_fraction = int(digest[:4], 16) / 0xFFFF
    score = int(300 + score_fraction * 550)  # 300-850

    flag_seed = int(digest[4:6], 16)
    has_default_flag = (flag_seed % _DEFAULT_RATE_DENOMINATOR) == 0

    return score, has_default_flag


def _summary_for(score: int, has_default_flag: bool) -> str:
    if has_default_flag:
        return "One or more past defaults on record; repayment history mixed."
    if score >= 700:
        return "Consistent on-time repayment history across reported facilities."
    if score >= 500:
        return "Generally timely repayment with occasional late payments."
    return "Limited repayment history available; few reported facilities."


def check_credit_history(country: str, identifier: str) -> CreditHistoryResult:
    """
    Simulate a credit-bureau lookup. Confidence is set high (per the
    proposal's "Strong" rating for this claim type) whenever a record is
    "found" -- this mock does not simulate the no-record-found case;
    construct a CreditHistoryResult directly with lower confidence if you
    need that scenario for testing.
    """
    provider = _PROVIDER_LABEL_BY_COUNTRY.get(country, "CRB_mock")
    score, has_default_flag = _deterministic_score_and_flag(identifier)

    return CreditHistoryResult(
        provider=provider,
        credit_score=score,
        has_default_flag=has_default_flag,
        repayment_history_summary=_summary_for(score, has_default_flag),
        confidence=0.92,
        checked_at=datetime.now(timezone.utc),
    )
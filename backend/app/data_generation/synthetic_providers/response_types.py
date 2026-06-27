"""
Shared response shapes for mock identity and credit-bureau providers.

In a real deployment, VeriFarm would never query NIBSS/NIMC or
CRC/CreditRegistry/FirstCentral (or Kenyan CRBs) directly -- that requires
formal institutional accreditation. Instead, it would hold an API key with
an ACCREDITED INTERMEDIARY (e.g. Smile Identity, Youverify, Prembly/QoreID
for identity; the bureaus themselves typically offer direct lender APIs,
but still via a commercial integration agreement) and call THEIR API.

These mocks exist to simulate that integration shape -- same call pattern,
same response shape a real provider would return -- without performing any
real lookup. The `provider` field on every response names which real
institution/intermediary this is standing in for, so the simulation is
self-documenting wherever it surfaces (in the Claim.method field, in logs,
in any debug output).
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class IdentityVerificationResult:
    """
    Shape modeled on what an accredited KYC intermediary (e.g. Smile
    Identity, Youverify, Prembly/QoreID) returns after performing a real
    NIBSS (BVN) / NIMC (NIN) lookup on a lender's behalf.
    """
    provider: str            # e.g. "NIBSS_mock_via_accredited_provider"
    match: bool
    verified_name: str | None
    submitted_identifier_type: str   # "BVN" | "NIN" | "national_id" | "phone"
    confidence: float        # 0.0-1.0
    checked_at: datetime


@dataclass
class CreditHistoryResult:
    """
    Shape modeled on a credit report returned by a licensed bureau
    (CRC Credit Bureau / CreditRegistry / FirstCentral in Nigeria;
    a CRB such as TransUnion Kenya / Metropol / Creditinfo in Kenya).
    """
    provider: str             # e.g. "CRC_mock"
    credit_score: int         # bureau-style score, arbitrary scale documented per-mock
    has_default_flag: bool
    repayment_history_summary: str
    confidence: float         # 0.0-1.0
    checked_at: datetime
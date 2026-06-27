"""Stub external credit-bureau / KYC API for the demo (Phase 5).

A standalone HTTP service that stands in for a licensed credit bureau and an
accredited identity intermediary. It returns deterministic, plausibly-shaped
responses — but over a real network call, exactly as a production vendor would.

Crucially this lives in ``app.scripts.demo`` and is a *separate service*, NOT in
``app.verification``: the verification layer still ships no fabricated provider
and still raises ``NotConfigured`` on its own. The demo provider
(:mod:`app.scripts.demo.demo_providers`) is a genuine HTTP client that calls THIS
service — so the seam is exercised end-to-end against an external source, the
same way ``coop-postgres`` stands in for an external registry DB.

Run:  uvicorn app.scripts.demo.stub_bureau:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Query

app = FastAPI(title="VERIFARMS demo credit/identity bureau (stub)")

_CREDIT_LABEL = {
    "Nigeria": "CRC Credit Bureau (demo)",
    "Kenya": "TransUnion Kenya (demo)",
}
_IDENTITY_LABEL = {
    "Nigeria": "Smile Identity / NIBSS BVN (demo)",
    "Kenya": "Smile Identity / National ID (demo)",
}
_ID_TYPE = {"Nigeria": "BVN", "Kenya": "national_id"}


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/credit")
def credit(country: str = Query(...), identifier: str = Query(...)) -> dict:
    """Deterministic bureau-style credit report for ``identifier``."""
    d = _digest(country, identifier)
    score = 300 + int(d[:4], 16) % 551          # 300..850
    has_default = int(d[4:6], 16) % 13 == 0     # ~1-in-13
    if has_default:
        summary = "One or more past defaults on record; repayment history mixed."
    elif score >= 700:
        summary = "Consistent on-time repayment across reported facilities."
    elif score >= 500:
        summary = "Generally timely repayment with occasional late payments."
    else:
        summary = "Limited repayment history; few reported facilities."
    return {
        "provider": _CREDIT_LABEL.get(country, "Credit Bureau (demo)"),
        "credit_score": score,
        "has_default_flag": has_default,
        "repayment_history_summary": summary,
        "confidence": 0.92,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/identity")
def identity(
    country: str = Query(...),
    claimed_name: str = Query(...),
    identifier: str = Query(...),
    identifier_type: Optional[str] = Query(default=None),
) -> dict:
    """Deterministic KYC verification. A small, stable slice returns a non-match."""
    d = _digest(country, identifier)
    match = int(d[6:8], 16) % 17 != 0           # ~1-in-17 non-match (realistic)
    confidence = round(0.85 + (int(d[:4], 16) / 0xFFFF) * 0.14, 2) if match else round(0.2 + (int(d[:2], 16) / 0xFF) * 0.3, 2)
    return {
        "provider": _IDENTITY_LABEL.get(country, "Identity Provider (demo)"),
        "match": match,
        "verified_name": claimed_name if match else None,
        "submitted_identifier_type": identifier_type or _ID_TYPE.get(country, "national_id"),
        "confidence": confidence,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

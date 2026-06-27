"""Runtime credit/identity enrichment via the ClaimBridge seam (Phase 5).

This is the wiring that was missing: until now ``ClaimBridge`` and the provider
seam were exercised only by tests, and with no registered provider the system
produced **no** ``credit_history`` / ``identity_verified`` claims at runtime. This
script closes that loop for the demo:

  1. import :mod:`app.scripts.demo.demo_providers` → registers the ``"demo"``
     credit + identity providers (real HTTP clients for the stub bureau);
  2. for each roster farmer, drive :class:`app.verification.claim_bridge.ClaimBridge`
     (providers resolved from the env-driven factory: ``CREDIT_PROVIDER=demo`` etc.)
     to fetch + reify a credit report and an identity verification;
  3. persist the reified bundles through the canonical schema-split guard, so the
     new claims are visible to the Copilot / Investigator / reputation queries.

Requires the seam env (set by the ``enrich-providers`` compose service):
``CREDIT_PROVIDER/CREDIT_API_KEY/CREDIT_BASE_URL`` and ``IDENTITY_*``. Without
them the factory raises ``NotConfigured`` — the system still refuses to invent
data; this script just supplies a real (stub) provider to satisfy it.

    python -m app.scripts.demo.enrich_via_bridge --farmers 60
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os

# Importing this registers the "demo" providers with the factory.
import app.scripts.demo.demo_providers  # noqa: F401
from app.scripts.demo.roster import DEFAULT_FARMERS, DemoFarmer, demo_roster
from app.verification.claim_bridge import ClaimBridge
from app.verification.providers.factory import NotConfigured

logger = logging.getLogger(__name__)

_NAMES = {
    "Kenya": ["Wanjiku Kamau", "Otieno Odhiambo", "Njeri Mwangi", "Kiprono Koech",
              "Achieng Owino", "Mutua Musyoka", "Chebet Rono", "Wafula Barasa"],
    "Nigeria": ["Chinedu Okafor", "Aisha Bello", "Emeka Nwosu", "Ngozi Eze",
                "Ibrahim Sani", "Folake Adeyemi", "Tunde Bakare", "Hauwa Yusuf"],
}
_ID_TYPE = {"Kenya": "national_id", "Nigeria": "BVN"}
_ID_LEN = {"Kenya": 8, "Nigeria": 11}


def _claimed_name(f: DemoFarmer) -> str:
    pool = _NAMES.get(f.country, _NAMES["Kenya"])
    return pool[f.index % len(pool)]


def _identifier(f: DemoFarmer) -> str:
    n = _ID_LEN.get(f.country, 9)
    num = int(hashlib.sha256(f.member_uuid.encode()).hexdigest(), 16)
    return str(num)[:n].rjust(n, "0")


async def enrich(*, farmers: int, driver) -> dict:
    from app.ingestion.reified_guard import publish_reified

    bridge = ClaimBridge()  # providers resolved from the env-driven factory.
    bundles = []
    credit_ok = identity_match = identity_nomatch = 0

    for f in demo_roster(farmers):
        identifier = _identifier(f)
        itype = _ID_TYPE.get(f.country, "national_id")

        credit = await bridge.build_credit_claim(
            farmer_id=f.member_uuid, country=f.country, identifier=identifier
        )
        bundles.append(credit.to_payload_bundle())
        credit_ok += 1

        identity = await bridge.build_identity_claim(
            farmer_id=f.member_uuid, country=f.country,
            claimed_name=_claimed_name(f), identifier=identifier, identifier_type=itype,
        )
        if identity is not None:
            bundles.append(identity.to_payload_bundle())
            identity_match += 1
        else:
            identity_nomatch += 1

    written = await asyncio.to_thread(publish_reified, driver, bundles)
    return {
        "farmers": farmers,
        "credit_claims": credit_ok,
        "identity_matches": identity_match,
        "identity_non_matches": identity_nomatch,
        "reified_claims_written": written,
    }


def _main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    p = argparse.ArgumentParser(description="Enrich farmers with credit/identity via the ClaimBridge seam.")
    p.add_argument("--farmers", type=int, default=DEFAULT_FARMERS)
    args = p.parse_args()

    from app.database.neo4j_client import get_driver

    driver = get_driver()
    try:
        summary = asyncio.run(enrich(farmers=args.farmers, driver=driver))
    except NotConfigured as exc:
        logger.error(
            "Provider seam not configured: %s\nSet CREDIT_PROVIDER=demo, CREDIT_API_KEY, "
            "CREDIT_BASE_URL (and IDENTITY_*) — see the enrich-providers compose service.",
            exc,
        )
        return 2
    finally:
        driver.close()

    import json

    print(json.dumps(summary, indent=2))
    print(
        f"\nWrote {summary['reified_claims_written']} reified claim(s): credit_history + "
        f"credit_default_flag for {summary['credit_claims']} farmers, identity_verified for "
        f"{summary['identity_matches']} (·{summary['identity_non_matches']} non-match). "
        "These now flow to the Copilot/Investigator — 'no credit history' reports shrink."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

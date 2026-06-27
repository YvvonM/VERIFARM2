"""Seed the REIFIED trust layer for demos.

Complements ``data-pipeline/neo4j_loader.py`` (which seeds the base 5-node
*registry* model). This populates the reified layer the agent's *operational*
tools and the DLQ Investigator read:

    (:Institution)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(:Farmer)

What it creates, deterministically:
  * an authoritative satellite institution (ground truth for land size);
  * two non-authoritative cooperatives (Kenya / Nigeria);
  * per farmer: a satellite ``land_size_hectares`` claim and cooperative
    ``land_size_hectares`` + ``production_volume_kg`` (+ ``credit_history`` for
    ~2/3 of them, so "no credit history" queries return the rest);
  * every 7th farmer gets a cooperative land size ~3× the satellite truth — a
    deliberate conflict the DLQ Investigator will flag.

It then recomputes each cooperative's reputation against ground truth, so trust
scores reflect the conflicts. Idempotent: deterministic claim ids + MERGE.

    python -m app.scripts.seed_reified --farmers 60
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import random
from datetime import datetime, timezone

from app.database import trust_graph
from app.database.graph_ingestion import GraphIngestionService
from app.database.neo4j_client import get_driver
from app.models.reified import Claim, Farmer, Institution, PayloadBundle

logger = logging.getLogger(__name__)

# Fixed nonce → deterministic claim ids → re-running the seed is idempotent.
_NONCE = "seed-v1"

# country -> (institution_id, name, seed trust score)
COOPS: dict[str, tuple[str, str, float]] = {
    "Kenya": ("ORG-TEGEMEO", "Tegemeo Cereals Enterprises", 0.62),
    "Nigeria": ("ORG-AGROVESTO", "Agrovesto Cooperative", 0.55),
}
SAT_ID, SAT_NAME = "SAT-SENTINEL2", "Sentinel-2 NDVI Cross-Check"

_TS = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _cid(institution_id: str, farmer_id: str, claim_type: str) -> str:
    raw = "|".join((institution_id, farmer_id, claim_type, _NONCE))
    return "claim_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _claim(inst: str, farmer: str, ctype: str, *, numeric=None, string=None,
           unit=None, conf: float, source_category: str) -> Claim:
    return Claim(
        claim_id=_cid(inst, farmer, ctype),
        claim_type=ctype,
        value_numeric=numeric,
        value_string=string,
        unit=unit,
        source_id=inst.lower(),
        source_category=source_category,
        confidence=conf,
        timestamp=_TS,
    )


_DEFAULT_COUNTRY = "Kenya"

# Read existing registry farmers (loaded by data-pipeline) to attach reified
# claims to the SAME farmer nodes — so one farmer is queryable both by the
# registry (country/location) and the reified trust layer (claims/trust).
FARMERS_FROM_GRAPH_Q = (
    "MATCH (f:Farmer) WHERE f.country IS NOT NULL "
    "RETURN f.id AS id, f.country AS country ORDER BY f.id LIMIT $n"
)


def _build(pairs: list[tuple[str, str]], seed: int = 42, ground_truth_only: bool = False):
    """Build reified bundles for (farmer_id, country) pairs.

    Returns (bundles, conflict_farmer_ids, no_credit_farmer_ids).

    When ``ground_truth_only`` is set, only the authoritative satellite land-size
    claim is seeded per farmer — no cooperative attestations at all. The live
    cooperative connector (``app.ingestion.connectors.cooperative_sync``, fed by
    ``app.scripts.demo.seed_cooperative_pg``) then becomes the *sole* source of
    non-authoritative claims, so every flagged conflict is attributable to the
    live Postgres pull rather than to this static seed. In that mode the returned
    ``conflicts``/``no_credit`` lists are empty (this seed introduces neither).
    """
    rng = random.Random(seed)
    bundles: list[PayloadBundle] = []
    conflicts: list[str] = []
    no_credit: list[str] = []

    for i, (fid, country) in enumerate(pairs, start=1):
        coop_id, coop_name, coop_trust = COOPS.get(country, COOPS[_DEFAULT_COUNTRY])

        true_ha = round(1.0 + (i % 10) * 0.4 + rng.uniform(-0.1, 0.1), 2)

        # Authoritative ground truth (satellite): land size only. Always seeded.
        bundles.append(PayloadBundle(
            institution=Institution(
                institution_id=SAT_ID, name=SAT_NAME, type="Satellite",
                is_authoritative=True, initial_trust_score=1.0,
            ),
            farmer=Farmer(farmer_id=fid),
            claims=[_claim(SAT_ID, fid, "land_size_hectares", numeric=true_ha, unit="ha", conf=1.0,
                           source_category="remote_sensing")],
        ))

        if ground_truth_only:
            # Cooperative claims (and thus conflicts) come from the live connector.
            continue

        is_conflict = (i % 7 == 0)
        coop_ha = round(true_ha * (3.0 if is_conflict else rng.uniform(0.97, 1.05)), 2)
        if is_conflict:
            conflicts.append(fid)
        prod_kg = round(true_ha * 1800 * rng.uniform(0.9, 1.1))
        has_credit = (i % 3 != 0)
        if not has_credit:
            no_credit.append(fid)

        # Non-authoritative cooperative attestations.
        coop_claims = [
            _claim(coop_id, fid, "land_size_hectares", numeric=coop_ha, unit="ha", conf=0.80,
                   source_category="cooperative"),
            _claim(coop_id, fid, "production_volume_kg", numeric=prod_kg, unit="kg", conf=0.75,
                   source_category="cooperative"),
        ]
        if has_credit:
            coop_claims.append(
                _claim(coop_id, fid, "credit_history", numeric=rng.randint(520, 780), conf=0.85,
                       source_category="government")
            )
        bundles.append(PayloadBundle(
            institution=Institution(
                institution_id=coop_id, name=coop_name, type="Cooperative",
                is_authoritative=False, consent_at_source=True, initial_trust_score=coop_trust,
            ),
            farmer=Farmer(farmer_id=fid),
            claims=coop_claims,
        ))

    return bundles, conflicts, no_credit


def build_bundles(num_farmers: int, seed: int = 42, ground_truth_only: bool = False):
    """Synthetic mode: invent F-0001..F-N farmers (no registry needed)."""
    pairs = [(f"F-{i:04d}", "Kenya" if i % 2 else "Nigeria") for i in range(1, num_farmers + 1)]
    return _build(pairs, seed, ground_truth_only)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Seed the reified trust layer for demos.")
    parser.add_argument("--farmers", type=int, default=60, help="How many farmers to seed.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--from-graph", action="store_true",
        help="Attach reified claims to EXISTING registry farmers (unified demo). "
             "Requires the data-pipeline loader to have run first.",
    )
    parser.add_argument(
        "--ground-truth-only", action="store_true",
        help="Seed ONLY the authoritative satellite land-size claim per farmer "
             "(no cooperative claims). Pairs with the live cooperative connector "
             "so it is the sole source of non-authoritative claims and conflicts.",
    )
    args = parser.parse_args()

    driver = get_driver()
    try:
        if args.from_graph:
            with driver.session() as session:
                rows = session.run(FARMERS_FROM_GRAPH_Q, n=args.farmers).data()
            if not rows:
                logger.error("No registry farmers with a country found — run the loader first.")
                return 1
            pairs = [(r["id"], r["country"]) for r in rows]
            bundles, conflicts, no_credit = _build(pairs, args.seed, args.ground_truth_only)
            scope = f"{len(pairs)} existing registry farmers (unified)"
        else:
            bundles, conflicts, no_credit = build_bundles(
                args.farmers, args.seed, args.ground_truth_only
            )
            scope = f"F-0001 .. F-{args.farmers:04d} (synthetic)"

        svc = GraphIngestionService(driver=driver)
        svc.ensure_constraints()
        written = svc.ingest_payload_bundles(bundles)
        logger.info("Ingested %d reified claim(s) across %d bundle(s).", written, len(bundles))

        # Close the trust loop: score each cooperative against ground truth.
        for _country, (coop_id, _name, _seed) in COOPS.items():
            summary = trust_graph.recalculate_reputation(driver, coop_id)
            logger.info("Reputation %s -> %s", coop_id, summary)
    finally:
        driver.close()

    print("\n=== Reified seed complete ===")
    print(f"farmers           : {scope}")
    if args.ground_truth_only:
        print(f"institutions      : {SAT_ID} (authoritative ground truth only)")
        print("cooperative claims: none — supplied by the LIVE connector "
              "(seed_cooperative_pg → cooperative_sync), the sole conflict source.")
        print("\nNext:")
        print("  python -m app.scripts.demo.seed_cooperative_pg --farmers <N>")
        print("  python -m app.ingestion.connectors.cooperative_sync --once")
        print("  GET /api/v1/investigator/run   (flags the connector-introduced conflicts)")
    else:
        print(f"institutions      : {SAT_ID} (authoritative), " + ", ".join(c[0] for c in COOPS.values()))
        print(f"conflict farmers  : {len(conflicts)} (e.g. {', '.join(conflicts[:5]) or '—'})  ← DLQ Investigator will flag")
        print(f"no credit history : {len(no_credit)} (e.g. {', '.join(no_credit[:5]) or '—'})")
        print("\nTry:")
        print("  GET /api/v1/investigator/run   (or the chat: 'investigate land size conflicts')")
        print("  chat: \"What is ORG-TEGEMEO's trust score?\"")
        print(f"  chat: \"Show the verified history for farmer {conflicts[0] if conflicts else 'F-0001'}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

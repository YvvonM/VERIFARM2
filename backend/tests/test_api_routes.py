"""Route-handler tests for the gold/profiles/match APIs + the auth gate.

These exercise the FastAPI layer end-to-end with a TestClient: dependency
overrides swap the Neo4j driver for a sentinel and monkeypatch the query
functions, so we assert the handler's mapping/validation/status-code behaviour
(including the require_api_key + rate_limit dependencies) without a database.

Requires fastapi + httpx (TestClient) + pydantic to be installed; the module is
skipped cleanly when they're absent (e.g. a bare local checkout).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("pydantic")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import gold, match, profiles  # noqa: E402
from app.api import security  # noqa: E402
from app.database.neo4j_client import get_shared_driver  # noqa: E402
from app.ratelimit import RateLimiter  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    """A TestClient over the three routers with the DB driver overridden out.

    Auth is open (no key configured) and the limiter is generous unless a test
    overrides them.
    """
    monkeypatch.delenv("VERIFARMS_API_KEY", raising=False)
    monkeypatch.delenv("EXPORT_API_KEY", raising=False)
    monkeypatch.setattr(security, "export_limiter", RateLimiter(limit=1000))

    app = FastAPI()
    app.include_router(gold.router)
    app.include_router(profiles.router)
    app.include_router(match.router)
    app.dependency_overrides[get_shared_driver] = lambda: object()  # sentinel driver
    return TestClient(app)


# --- handler behaviour -----------------------------------------------------

def test_verified_history_200(client, monkeypatch):
    monkeypatch.setattr(
        profiles, "get_verified_history",
        lambda driver, fid: {"farmer_id": fid, "phone_number": "+254700", "verified_history": {}},
    )
    resp = client.get("/api/v1/profiles/F-1/verified-history")
    assert resp.status_code == 200
    assert resp.json()["farmer_id"] == "F-1"


def test_verified_history_404(client, monkeypatch):
    monkeypatch.setattr(profiles, "get_verified_history", lambda driver, fid: None)
    resp = client.get("/api/v1/profiles/NOPE/verified-history")
    assert resp.status_code == 404


def test_my_data_404(client, monkeypatch):
    monkeypatch.setattr(gold, "get_my_data", lambda driver, fid: None)
    resp = client.get("/api/v1/farmer/NOPE/my-data")
    assert resp.status_code == 404


def test_cooperative_stats_200(client, monkeypatch):
    monkeypatch.setattr(
        gold, "get_cooperative_stats",
        lambda driver, iid: {
            "institution_id": iid,
            "total_members": 12,
            "total_verified_hectares": 34.5,
            "unverified_members": 3,
            "missing_credit_history_count": 2,
        },
    )
    resp = client.get("/api/v1/macro/cooperative/ORG-1/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["institution_id"] == "ORG-1" and body["total_members"] == 12


def test_match_products_catalog_200(client):
    # list_products() reads the static catalog — no DB needed.
    resp = client.get("/match/products")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list) and len(resp.json()) >= 1


def test_match_farmer_404_when_missing(client, monkeypatch):
    monkeypatch.setattr(match.match_engine, "farmer_exists", lambda driver, fid: False)
    resp = client.post("/match/GHOST")
    assert resp.status_code == 404


# --- auth gate (require_api_key) -------------------------------------------

def test_api_key_blocks_without_key(client, monkeypatch):
    monkeypatch.setenv("VERIFARMS_API_KEY", "s3cret")
    monkeypatch.setattr(profiles, "get_verified_history",
                        lambda driver, fid: {"farmer_id": fid, "verified_history": {}})
    assert client.get("/api/v1/profiles/F-1/verified-history").status_code == 401


def test_api_key_accepts_header_and_query(client, monkeypatch):
    monkeypatch.setenv("VERIFARMS_API_KEY", "s3cret")
    monkeypatch.setattr(profiles, "get_verified_history",
                        lambda driver, fid: {"farmer_id": fid, "verified_history": {}})
    assert client.get(
        "/api/v1/profiles/F-1/verified-history", headers={"X-API-Key": "s3cret"}
    ).status_code == 200
    assert client.get(
        "/api/v1/profiles/F-1/verified-history?api_key=s3cret"
    ).status_code == 200


# --- rate limit ------------------------------------------------------------

def test_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setattr(security, "export_limiter", RateLimiter(limit=1))
    # /match/products takes no DB and no key → clean path to exercise the limiter.
    assert client.get("/match/products").status_code == 200
    assert client.get("/match/products").status_code == 429

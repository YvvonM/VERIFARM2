"""Tests for the idempotent registry-lookup cache (in-memory TTL).

Pure stdlib — runnable anywhere. Verifies stable/idempotent keys and TTL expiry.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.clients.cache import TTLCache, cache_key  # noqa: E402


def test_cache_key_is_stable_and_order_independent():
    assert cache_key("land", parcel="P1", country="KE") == cache_key("land", country="KE", parcel="P1")
    assert cache_key("land", parcel="P1") != cache_key("land", parcel="P2")
    assert cache_key("land", parcel="P1") != cache_key("cert", parcel="P1")  # namespace matters


def test_ttl_cache_set_get_and_expiry():
    c = TTLCache()
    asyncio.run(c.set("k", "v", ttl=100))
    assert asyncio.run(c.get("k")) == "v"
    # ttl=0 → expires immediately (now >= expires_at).
    asyncio.run(c.set("k2", "v2", ttl=0))
    assert asyncio.run(c.get("k2")) is None
    assert asyncio.run(c.get("missing")) is None


def test_identical_lookups_hit_same_entry():
    c = TTLCache()
    k = cache_key("land_registry", country="KE", parcel_id="P-1")
    asyncio.run(c.set(k, "result-1"))
    # A second, identically-parameterized lookup resolves to the cached value.
    again = cache_key("land_registry", parcel_id="P-1", country="KE")
    assert asyncio.run(c.get(again)) == "result-1"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {fn.__name__}: {exc}")
            failures.append(fn.__name__)
    print("\n" + ("ALL PASSED" if not failures else f"{len(failures)} FAILURE(S): {failures}"))
    sys.exit(1 if failures else 0)

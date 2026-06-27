"""Pooled async Postgres source — SQLAlchemy 2.0 (asyncpg driver).

The live "connect to another database" layer. A single :class:`AsyncEngine` per
DSN owns a connection **pool**, so many concurrent syncs/requests share a bounded
set of connections instead of opening one per call and exhausting the server.
Key resiliency settings:

  * ``pool_pre_ping=True`` — validate a pooled connection before use, so a
    connection dropped by the DB/firewall is transparently replaced instead of
    raising on the next query.
  * ``pool_recycle`` — proactively retire connections older than N seconds
    (beats idle-timeout disconnects).

Like the provider seam, it **refuses to invent a connection**: with no DSN it
raises :class:`SourceNotConfigured`. ``sqlalchemy``/``asyncpg`` are imported
lazily so the backend boots without them installed.

    COOP_PG_DSN   postgresql://user:pass@host:5432/registry   (asyncpg added automatically)
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)

DEFAULT_POOL_SIZE = 5
DEFAULT_MAX_OVERFLOW = 10
DEFAULT_POOL_RECYCLE = 1800  # seconds
DEFAULT_STREAM_BATCH = 1000

# One pooled engine per normalized DSN, reused across syncs (the whole point of
# pooling — don't rebuild the pool every pass).
_ENGINES: dict[str, Any] = {}


class SourceNotConfigured(RuntimeError):
    """Raised when an external source has no connection configured."""


def _normalize_dsn(dsn: str) -> str:
    """Force the asyncpg driver onto a plain libpq DSN."""
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn
    if dsn.startswith("postgresql://"):
        return "postgresql+asyncpg://" + dsn[len("postgresql://"):]
    if dsn.startswith("postgres://"):
        return "postgresql+asyncpg://" + dsn[len("postgres://"):]
    return dsn


def get_engine(dsn: Optional[str] = None):
    """Return (creating once) the pooled AsyncEngine for ``dsn``.

    Raises:
        SourceNotConfigured: when neither ``dsn`` nor the ``coop_pg_dsn`` secret
            (resolved via the configured secrets backend) is available.
    """
    from app.secrets import get_secret

    # Credentials come from the secrets backend (env / Vault / AWS), not a raw
    # os.environ read — so production can centralize/rotate them.
    raw = dsn or get_secret("coop_pg_dsn")
    if not raw:
        raise SourceNotConfigured(
            "COOP_PG_DSN is not set; no external registry connection configured."
        )

    key = _normalize_dsn(raw)
    if key not in _ENGINES:
        from sqlalchemy.ext.asyncio import create_async_engine

        _ENGINES[key] = create_async_engine(
            key,
            pool_size=int(os.environ.get("COOP_PG_POOL_SIZE", DEFAULT_POOL_SIZE)),
            max_overflow=int(os.environ.get("COOP_PG_MAX_OVERFLOW", DEFAULT_MAX_OVERFLOW)),
            pool_recycle=int(os.environ.get("COOP_PG_POOL_RECYCLE", DEFAULT_POOL_RECYCLE)),
            pool_pre_ping=True,       # survive dropped connections transparently
            pool_timeout=30,
        )
        logger.info("Created pooled async engine for %s.", key.split("@")[-1])
    return _ENGINES[key]


async def stream(
    query: str,
    params: Optional[dict[str, Any]] = None,
    dsn: Optional[str] = None,
    batch: int = DEFAULT_STREAM_BATCH,
) -> AsyncIterator[dict[str, Any]]:
    """Yield rows as dicts from a server-side streaming result (constant memory)."""
    from sqlalchemy import text

    engine = get_engine(dsn)
    async with engine.connect() as conn:
        result = await conn.stream(
            text(query).execution_options(yield_per=batch), params or {}
        )
        async for row in result.mappings():
            yield dict(row)


async def fetch_all(
    query: str,
    params: Optional[dict[str, Any]] = None,
    dsn: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Eagerly collect all rows (convenience over :func:`stream`)."""
    return [row async for row in stream(query, params, dsn)]


async def dispose_engines() -> None:
    """Dispose every pooled engine (call on shutdown / end of a one-off run)."""
    for engine in _ENGINES.values():
        await engine.dispose()
    _ENGINES.clear()

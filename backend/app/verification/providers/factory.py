"""Environment-driven provider factory.

The factory is the only place that decides *which* concrete provider to build,
from environment configuration. Crucially, it ships **no mock and no fabricated
provider**: a real integration registers itself via :func:`register_credit_provider`
/ :func:`register_identity_provider`, and the factory instantiates it only when
the required environment (selector + API key + endpoint) is present. Otherwise it
raises :class:`NotConfigured` immediately — the system refuses to invent data.

Environment contract (per capability):

    CREDIT_PROVIDER   / CREDIT_API_KEY   / CREDIT_BASE_URL
    IDENTITY_PROVIDER / IDENTITY_API_KEY / IDENTITY_BASE_URL

``*_PROVIDER`` selects a registered implementation by name; the key/URL are
passed to it. A registered provider class is expected to accept
``(*, api_key: str, base_url: str)``.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from app.verification.providers.base import CreditBureauProvider, IdentityProvider

logger = logging.getLogger(__name__)


class NotConfigured(RuntimeError):
    """Raised when no real provider is configured. Never falls back to mock data."""


# Concrete providers register here. Empty by design — this codebase ships no
# fabricated providers; a real integration adds itself with the decorators below.
_CREDIT_REGISTRY: dict[str, Callable[..., CreditBureauProvider]] = {}
_IDENTITY_REGISTRY: dict[str, Callable[..., IdentityProvider]] = {}


def register_credit_provider(name: str):
    """Register a concrete :class:`CreditBureauProvider` under ``name``."""
    def _register(cls: Callable[..., CreditBureauProvider]):
        _CREDIT_REGISTRY[name] = cls
        return cls
    return _register


def register_identity_provider(name: str):
    """Register a concrete :class:`IdentityProvider` under ``name``."""
    def _register(cls: Callable[..., IdentityProvider]):
        _IDENTITY_REGISTRY[name] = cls
        return cls
    return _register


def _build(kind: str, registry: dict[str, Callable[..., object]]):
    """Shared resolution: read the env trio, look up the registry, instantiate."""
    name = os.getenv(f"{kind}_PROVIDER")
    api_key = os.getenv(f"{kind}_API_KEY")
    base_url = os.getenv(f"{kind}_BASE_URL")

    if not (name and api_key and base_url):
        raise NotConfigured(
            f"{kind.title()} provider not configured: set {kind}_PROVIDER, "
            f"{kind}_API_KEY and {kind}_BASE_URL. Refusing to fabricate data."
        )

    cls = registry.get(name)
    if cls is None:
        known = sorted(registry) or "[]"
        raise NotConfigured(
            f"No {kind.lower()} provider registered under {name!r}. Known: {known}. "
            f"Register a concrete implementation before selecting it."
        )

    logger.info("Instantiating %s provider %r.", kind.lower(), name)
    return cls(api_key=api_key, base_url=base_url)


def get_credit_provider() -> CreditBureauProvider:
    """Return the configured credit bureau provider, or raise :class:`NotConfigured`."""
    return _build("CREDIT", _CREDIT_REGISTRY)  # type: ignore[return-value]


def get_identity_provider() -> IdentityProvider:
    """Return the configured identity provider, or raise :class:`NotConfigured`."""
    return _build("IDENTITY", _IDENTITY_REGISTRY)  # type: ignore[return-value]


def credit_provider_configured() -> bool:
    """Whether a credit provider can be built (env present + impl registered)."""
    try:
        get_credit_provider()
        return True
    except NotConfigured:
        return False


def identity_provider_configured() -> bool:
    """Whether an identity provider can be built (env present + impl registered)."""
    try:
        get_identity_provider()
        return True
    except NotConfigured:
        return False

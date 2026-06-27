"""Secrets provider interface.

A logical secret name (e.g. ``"coop_pg_dsn"`` or ``"sources/tegemeo/dsn"``) is
resolved to a value by whichever backend is configured — env (dev), HashiCorp
Vault, or AWS Secrets Manager. Callers depend only on this interface, never on a
specific backend, so migrating from `.env` to Vault/AWS is a config change.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


class SecretNotFound(KeyError):
    """Raised by callers that require a secret which the backend cannot resolve."""


@runtime_checkable
class SecretsProvider(Protocol):
    """Resolve a logical secret name to its value, or ``None`` if absent."""

    def get_secret(self, name: str) -> Optional[str]:
        ...

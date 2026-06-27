"""Secrets backend factory — chosen by ``SECRETS_BACKEND`` (env | vault | aws).

Defaults to the env backend so local/dev keeps working, while production flips a
single variable to centralize external-source credentials in Vault or AWS.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from app.secrets.base import SecretsProvider
from app.secrets.env_provider import EnvSecretsProvider

logger = logging.getLogger(__name__)


def get_secrets_provider() -> SecretsProvider:
    """Return the configured secrets provider (constructed fresh each call)."""
    backend = os.environ.get("SECRETS_BACKEND", "env").lower()
    if backend == "env":
        return EnvSecretsProvider()
    if backend == "vault":
        from app.secrets.vault_provider import VaultSecretsProvider
        return VaultSecretsProvider()
    if backend in ("aws", "aws-secrets-manager", "secretsmanager"):
        from app.secrets.aws_provider import AWSSecretsProvider
        return AWSSecretsProvider()
    raise ValueError(
        f"Unknown SECRETS_BACKEND {backend!r}. Use 'env', 'vault' or 'aws'."
    )


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Resolve a logical secret name via the configured backend."""
    value = get_secrets_provider().get_secret(name)
    return value if value is not None else default

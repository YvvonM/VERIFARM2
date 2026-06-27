"""Secrets management seam — resolve external-source credentials via a backend.

    from app.secrets import get_secret
    dsn = get_secret("coop_pg_dsn")     # env / Vault / AWS, per SECRETS_BACKEND

Backends: env (dev/default, deprecated for external sources), HashiCorp Vault,
AWS Secrets Manager. Vault/AWS deps are optional and lazily imported.
"""

from app.secrets.base import SecretNotFound, SecretsProvider
from app.secrets.factory import get_secret, get_secrets_provider

__all__ = ["get_secret", "get_secrets_provider", "SecretsProvider", "SecretNotFound"]

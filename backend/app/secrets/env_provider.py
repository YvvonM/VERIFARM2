"""Environment-variable secrets backend (development / fallback).

DEPRECATED for external-source credentials: ``.env`` is fine locally, but
production should use Vault or AWS Secrets Manager (``SECRETS_BACKEND=vault|aws``)
so per-source credentials are centrally rotated and audited rather than sitting
in a file. This backend maps a logical name to an env var by upper-casing and
replacing non-alphanumerics with ``_`` — so ``"coop_pg_dsn"`` → ``COOP_PG_DSN``.
"""

from __future__ import annotations

import os
import re
from typing import Optional


class EnvSecretsProvider:
    """Resolve secrets from environment variables."""

    @staticmethod
    def _envify(name: str) -> str:
        return re.sub(r"[^A-Z0-9]", "_", name.upper())

    def get_secret(self, name: str) -> Optional[str]:
        return os.environ.get(self._envify(name))

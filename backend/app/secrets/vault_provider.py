"""HashiCorp Vault secrets backend (KV v2).

Reads ``<base_path>/<name>`` from a KV v2 mount and returns the secret's
``value`` key (or the sole key if there's just one). ``hvac`` is imported lazily
so the backend module loads without the dependency; it's only needed when
``SECRETS_BACKEND=vault``.

Config (env):
    VAULT_ADDR           e.g. https://vault.internal:8200
    VAULT_TOKEN          auth token (or use VAULT_ROLE_ID/SECRET_ID in prod)
    VAULT_KV_MOUNT       KV mount point (default 'secret')
    VAULT_SECRETS_PATH   base path under the mount (default 'verifarms')
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class VaultSecretsProvider:
    def __init__(
        self,
        addr: Optional[str] = None,
        token: Optional[str] = None,
        mount: Optional[str] = None,
        base_path: Optional[str] = None,
    ) -> None:
        self.addr = addr or os.environ.get("VAULT_ADDR")
        self.token = token or os.environ.get("VAULT_TOKEN")
        self.mount = mount or os.environ.get("VAULT_KV_MOUNT", "secret")
        self.base_path = base_path or os.environ.get("VAULT_SECRETS_PATH", "verifarms")

    def get_secret(self, name: str) -> Optional[str]:
        if not self.addr:
            logger.warning("VAULT_ADDR not set; cannot resolve %r.", name)
            return None
        try:
            import hvac

            client = hvac.Client(url=self.addr, token=self.token)
            resp = client.secrets.kv.v2.read_secret_version(
                path=f"{self.base_path}/{name}", mount_point=self.mount
            )
            data = resp["data"]["data"]
            if "value" in data:
                return data["value"]
            return data.get(name) or next(iter(data.values()), None)
        except Exception:  # noqa: BLE001 - a missing/unreachable secret resolves to None.
            logger.warning("Vault lookup failed for %r.", name, exc_info=True)
            return None

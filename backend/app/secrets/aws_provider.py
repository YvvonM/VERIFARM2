"""AWS Secrets Manager backend.

Resolves ``<prefix><name>`` via ``GetSecretValue``. A JSON secret returns its
``value`` key (or the sole key); a plain-string secret is returned as-is.
``boto3`` is imported lazily — only needed when ``SECRETS_BACKEND=aws``.

Config (env):
    AWS_SECRETS_PREFIX   id prefix (default 'verifarms/')
    AWS_REGION           region for the Secrets Manager client
    (plus standard AWS credential resolution — role, profile, or keys)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class AWSSecretsProvider:
    def __init__(self, prefix: Optional[str] = None, region: Optional[str] = None) -> None:
        self.prefix = prefix if prefix is not None else os.environ.get("AWS_SECRETS_PREFIX", "verifarms/")
        self.region = region or os.environ.get("AWS_REGION")

    def get_secret(self, name: str) -> Optional[str]:
        try:
            import boto3

            client = boto3.client("secretsmanager", region_name=self.region)
            resp = client.get_secret_value(SecretId=f"{self.prefix}{name}")
        except Exception:  # noqa: BLE001 - missing secret / no creds → None.
            logger.warning("AWS Secrets Manager lookup failed for %r.", name, exc_info=True)
            return None

        raw = resp.get("SecretString")
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw  # plain-string secret
        if isinstance(data, dict):
            return data.get("value") or data.get(name) or next(iter(data.values()), None)
        return str(data)

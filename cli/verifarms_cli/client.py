"""HTTP client layer — a thin, clean synchronous httpx client over the Egress API.

The local config's API token is injected into every request's ``X-API-Key``
header automatically, and the base URL comes from the resolved environment — so
commands never deal with auth or URLs directly.
"""

from __future__ import annotations

import json
from typing import Any, Iterator, Optional

import httpx

from verifarms_cli.config import EnvConfig, load_config


class VerifarmsClient:
    def __init__(self, env: EnvConfig, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=env.base_url,
            timeout=timeout,
            headers=self._auth_headers(env),
        )

    @staticmethod
    def _auth_headers(env: EnvConfig) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if env.api_key:  # token auto-injected from local config
            headers["X-API-Key"] = env.api_key
        return headers

    def __enter__(self) -> "VerifarmsClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get_json(self, path: str, params: Optional[dict] = None) -> Any:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def stream_ndjson(self, path: str, params: Optional[dict] = None) -> Iterator[dict]:
        """Stream a newline-delimited-JSON endpoint, yielding one record at a time."""
        with self._client.stream("GET", path, params=params) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line.strip():
                    yield json.loads(line)


def client_for(env_override: Optional[str]) -> VerifarmsClient:
    """Build a client for the active environment (config + optional --env override)."""
    _name, env = load_config().resolve(env_override)
    return VerifarmsClient(env)

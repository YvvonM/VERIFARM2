"""Configuration state for the verifarms CLI.

Config lives at ``~/.verifarms/config.json`` (override with ``VERIFARMS_CONFIG_DIR``)
and holds one entry per environment (staging/production/…), plus the current
default. It is written with ``0o600`` so the API token is not world-readable.

State management: every command loads the config once, resolves the active
environment (a ``--env`` override beats the saved default), and builds an HTTP
client from it. The CLI is otherwise stateless — no globals beyond what Typer's
context carries for the current invocation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


def config_dir() -> Path:
    return Path(os.environ.get("VERIFARMS_CONFIG_DIR", str(Path.home() / ".verifarms")))


def config_file() -> Path:
    return config_dir() / "config.json"


DEFAULT_BASE_URLS = {
    "staging": "http://localhost:8000",
    "production": "https://api.verifarms.example",
}


class ConfigError(RuntimeError):
    """Raised when the requested environment isn't configured."""


class EnvConfig(BaseModel):
    base_url: str
    api_key: str = ""


class Config(BaseModel):
    current_env: str = "staging"
    environments: dict[str, EnvConfig] = Field(default_factory=dict)

    def resolve(self, env_override: Optional[str] = None) -> tuple[str, EnvConfig]:
        """Return the (name, EnvConfig) to use; ``--env`` overrides the default."""
        env = env_override or self.current_env
        cfg = self.environments.get(env)
        if cfg is None:
            raise ConfigError(
                f"Environment {env!r} is not configured. Run `verifarms auth login`."
            )
        return env, cfg


def load_config() -> Config:
    path = config_file()
    if not path.exists():
        return Config()
    return Config.model_validate_json(path.read_text(encoding="utf-8"))


def save_config(cfg: Config) -> Path:
    """Persist config with owner-only (0o600) permissions."""
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    path = config_file()
    path.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    os.chmod(path, 0o600)  # restrict read access to the owner
    return path

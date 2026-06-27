"""`verifarms auth` — interactive login + status."""

from __future__ import annotations

from typing import Optional

import typer
from rich.table import Table

from verifarms_cli.config import DEFAULT_BASE_URLS, EnvConfig, load_config, save_config
from verifarms_cli.formatting import console

app = typer.Typer(help="Authentication & environment configuration.")


@app.command("login")
def login(
    env: Optional[str] = typer.Option(None, "--env", help="Environment name (else prompted)."),
) -> None:
    """Interactively capture an API key + environment, saved securely (0o600)."""
    env = env or typer.prompt("Environment", default="staging")
    base_url = typer.prompt("API base URL", default=DEFAULT_BASE_URLS.get(env, "http://localhost:8000"))
    api_key = typer.prompt("API key (X-API-Key)", hide_input=True, default="", show_default=False)

    cfg = load_config()
    cfg.environments[env] = EnvConfig(base_url=base_url, api_key=api_key)
    cfg.current_env = env
    path = save_config(cfg)
    console.print(f"[green]✓ Saved[/] environment '{env}' → {base_url}")
    console.print(f"  config: {path} (permissions 0600, current env = {env})")


@app.command("status")
def status() -> None:
    """Show configured environments (API keys masked)."""
    cfg = load_config()
    if not cfg.environments:
        console.print("No environments configured. Run [bold]verifarms auth login[/].")
        return
    table = Table(title="verifarms environments")
    table.add_column("env"); table.add_column("base_url"); table.add_column("api_key"); table.add_column("current")
    for name, e in cfg.environments.items():
        masked = (e.api_key[:4] + "…") if e.api_key else "(none)"
        table.add_row(name, e.base_url, masked, "✓" if name == cfg.current_env else "")
    console.print(table)

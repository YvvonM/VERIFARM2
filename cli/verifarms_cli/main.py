"""verifarms CLI entrypoint — wires sub-apps and the global --env option.

State management: the root callback runs first on every invocation and stashes
the ``--env`` override on the Typer context (``ctx.obj``). Each command then
loads ``~/.verifarms/config.json`` and resolves the active environment from that
override (or the saved default), building an HTTP client on demand. There is no
hidden global state — configuration is read per-invocation and the token is
injected into request headers by the client layer.
"""

from __future__ import annotations

from typing import Optional

import typer

from verifarms_cli.commands import auth, export, get

app = typer.Typer(
    name="verifarms",
    help="VeriFarms CLI — a client for the verified-claims Egress API.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(auth.app, name="auth")
app.add_typer(get.app, name="get")
app.add_typer(export.app, name="export")


@app.callback()
def main(
    ctx: typer.Context,
    env: Optional[str] = typer.Option(
        None, "--env", help="Target environment override (e.g. staging, production)."
    ),
) -> None:
    ctx.obj = {"env_override": env}


if __name__ == "__main__":
    app()

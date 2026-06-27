"""`verifarms get` — fetch a single resource."""

from __future__ import annotations

from enum import Enum

import typer

from verifarms_cli.client import client_for
from verifarms_cli.formatting import output_claim
from verifarms_cli.util import error_boundary

app = typer.Typer(help="Fetch a single resource and print it.")


class OutputFormat(str, Enum):
    json = "json"
    text = "text"
    table = "table"


@app.command("claim")
def get_claim(
    ctx: typer.Context,
    claim_id: str = typer.Argument(..., help="The claim id to fetch."),
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format."),
) -> None:
    """Fetch a specific verified claim and print its reified bundle."""
    with error_boundary():
        with client_for(ctx.obj.get("env_override")) as client:
            data = client.get_json(f"/api/v1/export/claims/{claim_id}")
    output_claim(data, format.value)

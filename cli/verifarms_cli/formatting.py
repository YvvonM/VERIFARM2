"""Rich-based terminal rendering for command output."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()


def output_claim(claim: dict[str, Any], fmt: str) -> None:
    """Render a single claim as json | text | table."""
    if fmt == "json":
        console.print_json(data=claim)
        return
    if fmt == "table":
        table = Table(title=f"Claim · {claim.get('claim_type', '?')}", show_lines=False)
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")
        for key, value in claim.items():
            table.add_row(str(key), "" if value is None else str(value))
        console.print(table)
        return
    # text
    for key, value in claim.items():
        console.print(f"[bold cyan]{key}[/]: {value}")

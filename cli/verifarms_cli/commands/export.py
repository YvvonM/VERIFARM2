"""`verifarms export` — bulk extraction to CSV / JSONL with a progress bar."""

from __future__ import annotations

import csv
import json
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from verifarms_cli.client import client_for
from verifarms_cli.formatting import console
from verifarms_cli.util import error_boundary

app = typer.Typer(help="Bulk export to CSV / JSONL.")

PAGE_SIZE = 200
# Stable column order for streamed claim CSV.
CLAIM_COLUMNS = [
    "claim_id", "farmer_id", "claim_type", "value_numeric", "value_string", "unit",
    "confidence", "timestamp", "attested_by_id", "attested_by", "attested_by_trust",
    "authoritative",
]


class OrgStatus(str, Enum):
    verified = "verified"
    pending = "pending"
    all = "all"


def _format_for(out: Path) -> str:
    return "jsonl" if out.suffix.lower() in (".jsonl", ".ndjson") else "csv"


def _progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TextColumn("· {task.completed} rows"),
        TimeElapsedColumn(),
        console=console,
    )


@app.command("organizations")
def export_organizations(
    ctx: typer.Context,
    status: OrgStatus = typer.Option(OrgStatus.all, "--status", help="Filter by verification status."),
    out: Path = typer.Option(..., "--out", help="Output file (.csv or .jsonl)."),
) -> None:
    """Export organization records to CSV/JSONL (paginated, with a progress bar)."""
    fmt = _format_for(out)
    rows: list[dict] = []
    with error_boundary():
        with client_for(ctx.obj.get("env_override")) as client, _progress() as progress:
            task = progress.add_task("Exporting organizations", total=None)
            offset = 0
            while True:
                page = client.get_json(
                    "/api/v1/export/organizations",
                    params={"status": status.value, "offset": offset, "limit": PAGE_SIZE},
                )
                batch = page.get("organizations", [])
                rows.extend(batch)
                progress.update(task, advance=len(batch))
                nxt = page.get("next_offset")
                if not nxt:
                    break
                offset = nxt

    if fmt == "jsonl":
        with out.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
    else:
        cols = list(rows[0].keys()) if rows else ["institution_id"]
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    console.print(f"[green]✓ Wrote {len(rows)} organizations[/] to {out} ({fmt}).")


@app.command("claims")
def export_claims(
    ctx: typer.Context,
    out: Path = typer.Option(..., "--out", help="Output file (.csv or .jsonl)."),
    claim_type: Optional[str] = typer.Option(None, "--claim-type", help="Filter to one claim_type."),
    min_trust: float = typer.Option(0.0, "--min-trust", help="Minimum attesting-source trust."),
) -> None:
    """Stream a large claim export to CSV/JSONL (chunked download + progress)."""
    fmt = _format_for(out)
    params: dict = {"min_trust_score": min_trust}
    if claim_type:
        params["claim_type"] = claim_type

    count = 0
    with error_boundary():
        with client_for(ctx.obj.get("env_override")) as client, \
                out.open("w", newline="", encoding="utf-8") as fh, _progress() as progress:
            task = progress.add_task("Downloading claims", total=None)
            writer = None
            if fmt == "csv":
                writer = csv.DictWriter(fh, fieldnames=CLAIM_COLUMNS, extrasaction="ignore")
                writer.writeheader()
            for row in client.stream_ndjson("/api/v1/export/claims.ndjson", params=params):
                if writer is not None:
                    writer.writerow(row)
                else:
                    fh.write(json.dumps(row) + "\n")
                count += 1
                progress.update(task, advance=1)
    console.print(f"[green]✓ Wrote {count} claims[/] to {out} ({fmt}).")

"""Shared CLI utilities — a single error boundary for clean exit codes.

Used as a context manager *inside* command bodies (not a decorator) so Typer's
signature introspection on the command functions stays intact.
"""

from __future__ import annotations

from contextlib import contextmanager

import httpx
import typer

from verifarms_cli.config import ConfigError
from verifarms_cli.formatting import console


@contextmanager
def error_boundary():
    """Turn expected failures into a friendly message + non-zero exit."""
    try:
        yield
    except ConfigError as exc:
        console.print(f"[red]Config error:[/] {exc}")
        raise typer.Exit(code=1)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300]
        console.print(f"[red]API error {exc.response.status_code}:[/] {detail}")
        raise typer.Exit(code=1)
    except httpx.RequestError as exc:
        console.print(f"[red]Connection error:[/] {exc}")
        raise typer.Exit(code=1)

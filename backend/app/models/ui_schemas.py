"""Pydantic v2 models for the GenUI streaming contract.

These models define the *wire format* pushed over Server-Sent Events. Every
chunk serialized onto the stream is one of the envelopes below, dumped with
``model_dump_json()`` so the field names exactly match the agreed JSON contract:

  * Status  -> {"type": "status", "message": "..."}
  * Component-> {"type": "component", "componentType": "BarChart", "props": {...}}
  * Error   -> {"type": "error", "message": "..."}

Component ``props`` are validated against component-specific models (e.g.
:class:`BarChartProps`) before being placed on the stream, guaranteeing the
frontend ComponentRegistry always receives a well-formed payload.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Component prop schemas (validated before streaming).
# ---------------------------------------------------------------------------


class BarChartProps(BaseModel):
    """Props for the Recharts-backed BarChart GenUI component."""

    data: list[dict[str, Any]] = Field(
        ..., description="Row records to plot; each row contains xKey and yKey."
    )
    xKey: str = Field(..., description="Key in each row used for the category axis.")
    yKey: str = Field(..., description="Key in each row used for the value axis.")


class TableProps(BaseModel):
    """Props for the generic Table GenUI component.

    The fallback renderer for results that are not a clean (category, value)
    series — multi-column rows, text-heavy attestations, rule breakdowns, etc.
    """

    columns: list[str] = Field(..., description="Ordered column headers.")
    rows: list[list[Any]] = Field(
        ..., description="Row values, each aligned positionally with `columns`."
    )
    caption: str | None = Field(
        default=None, description="Optional human-readable description of the table."
    )


class InsightProps(BaseModel):
    """Props for the Insight component — the copilot's synthesized answer.

    The natural-language, business-readable conclusion the loan officer reads
    first, rendered above any supporting chart/table.
    """

    text: str = Field(..., description="Plain-language answer for the loan officer.")
    title: str | None = Field(default=None, description="Optional heading.")


# ---------------------------------------------------------------------------
# SSE envelope models.
# ---------------------------------------------------------------------------


class StreamStatusResponse(BaseModel):
    """Human-readable progress update emitted between agent steps."""

    type: Literal["status"] = "status"
    message: str


class StreamComponentResponse(BaseModel):
    """A structured UI component for the frontend to render."""

    type: Literal["component"] = "component"
    componentType: str = Field(
        ..., description="Registry key, e.g. 'BarChart', 'PieChart', 'Table'."
    )
    props: dict[str, Any] = Field(
        ..., description="Validated props for the named componentType."
    )


class StreamErrorResponse(BaseModel):
    """Terminal error envelope; lets the client surface a failure gracefully."""

    type: Literal["error"] = "error"
    message: str


# Discriminated union of everything that may legally appear on the stream.
StreamEvent = Annotated[
    Union[StreamStatusResponse, StreamComponentResponse, StreamErrorResponse],
    Field(discriminator="type"),
]

"""Configuration-driven Adapter Pattern for heterogeneous farmer sources.

Each upstream source (a cooperative's CSV export, a field-agent mobile app, ...)
speaks its own dialect: different key names, different units, different framing
of the same underlying fact. Rather than writing a bespoke parser per source,
we describe each source *declaratively* in :data:`SOURCE_ADAPTERS` and let one
generic mapper (:func:`map_raw_record`) translate any raw record into the keys
that :class:`~app.models.claims.StandardFarmerClaim` expects.

Adding a new source is therefore a config change, not a code change: register a
new :class:`SourceAdapter` with its field map and constants.

A field rule may carry a multiplicative ``factor`` to normalize units — e.g.
``farm_size_acres`` is mapped to ``land_size_hectares`` with a factor of
``0.404686`` (1 acre = 0.404686 ha).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 1 acre in hectares — used to normalize imperial land sizes.
ACRES_TO_HECTARES = 0.404686


class MappingError(ValueError):
    """Raised when a raw record cannot be coerced onto the standard schema.

    These are caught by the ingestion endpoint and routed to the Dead-Letter
    Queue alongside Pydantic validation failures.
    """


@dataclass(frozen=True)
class FieldRule:
    """How to derive one standard field from a raw record.

    Attributes:
        source_key: Key to read from the raw record.
        factor: Optional multiplier applied to a numeric value (unit
            conversion). ``None`` means the value is passed through untouched.
        required: When ``True`` (default), a missing source key is left absent
            so the Pydantic model can flag it. When ``False``, a missing key is
            silently skipped (the standard field falls back to its default).
    """

    source_key: str
    factor: float | None = None
    required: bool = True


@dataclass(frozen=True)
class SourceAdapter:
    """Declarative mapping from a single source's dialect to the standard schema.

    Attributes:
        source_id: The ``source_id`` value this adapter handles.
        constants: Standard fields injected verbatim for every record from this
            source (e.g. the verifier identity and graph label).
        field_map: ``standard_field -> FieldRule`` translations.
    """

    source_id: str
    constants: dict[str, Any] = field(default_factory=dict)
    field_map: dict[str, FieldRule] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Source registry. Register a new source here — no other code changes needed.
# ---------------------------------------------------------------------------

SOURCE_ADAPTERS: dict[str, SourceAdapter] = {
    # Tegemeo (Kenya cooperative): CSV-style export, land in acres.
    "tegemeo_cereals": SourceAdapter(
        source_id="tegemeo_cereals",
        constants={
            "country": "Kenya",
            "verifier_id": "ORG-TEGEMEO",
            "verifier_name": "Tegemeo Cereals Enterprises",
            "verifier_type": "Cooperative",
            "source_id": "tegemeo_cereals",
        },
        field_map={
            "farmer_id": FieldRule("reg_no"),
            "farmer_name": FieldRule("farmer"),
            "national_id": FieldRule("id_number", required=False),
            "phone": FieldRule("mobile", required=False),
            "region": FieldRule("county", required=False),
            "crop_type": FieldRule("crop"),
            # acres -> hectares
            "land_size_hectares": FieldRule("farm_size_acres", factor=ACRES_TO_HECTARES),
            "production_volume_kg": FieldRule("harvest_kg"),
            "confidence_score": FieldRule("verification_score"),
        },
    ),
    # Agrovesto (Nigeria off-taker app): JSON/camelCase, land already in hectares.
    "agrovesto_app": SourceAdapter(
        source_id="agrovesto_app",
        constants={
            "country": "Nigeria",
            "verifier_id": "ORG-AGROVESTO",
            "verifier_name": "Agrovesto",
            "verifier_type": "OffTaker",
            "source_id": "agrovesto_app",
        },
        field_map={
            "farmer_id": FieldRule("farmerId"),
            "farmer_name": FieldRule("fullName"),
            "national_id": FieldRule("nin", required=False),
            "phone": FieldRule("phoneNumber", required=False),
            "region": FieldRule("state", required=False),
            "crop_type": FieldRule("primaryCrop"),
            # already metric — no conversion factor
            "land_size_hectares": FieldRule("landSizeHectares"),
            "production_volume_kg": FieldRule("expectedYieldKg"),
            "confidence_score": FieldRule("trustIndex"),
        },
    ),
}


def get_adapter(source_id: str) -> SourceAdapter:
    """Return the adapter for ``source_id`` or raise :class:`KeyError`.

    The endpoint converts the ``KeyError`` into an HTTP 422 listing the known
    sources, so callers always learn which ``source_id`` values are valid.
    """
    try:
        return SOURCE_ADAPTERS[source_id]
    except KeyError as exc:  # re-raise with the supported set for a clear 4xx.
        raise KeyError(
            f"Unknown source_id {source_id!r}. "
            f"Supported: {sorted(SOURCE_ADAPTERS)}"
        ) from exc


def _apply_factor(value: Any, factor: float, std_key: str, source_key: str) -> float:
    """Multiply a numeric ``value`` by ``factor`` for unit conversion."""
    try:
        return float(value) * factor
    except (TypeError, ValueError) as exc:
        raise MappingError(
            f"Cannot convert {source_key!r}={value!r} for field {std_key!r}: "
            f"expected a number to scale by {factor}."
        ) from exc


def map_raw_record(adapter: SourceAdapter, raw: dict[str, Any]) -> dict[str, Any]:
    """Translate one raw record into standard-schema keys.

    Pure transport/units work only — type and constraint checks are deferred to
    :class:`~app.models.claims.StandardFarmerClaim`. Missing *required* source
    keys are intentionally left absent so Pydantic produces a precise
    "field required" error for the DLQ.

    Args:
        adapter: The source adapter to apply.
        raw: A single raw record from the incoming batch.

    Returns:
        A dict keyed by standard field names, ready to feed the Pydantic model.

    Raises:
        MappingError: If a unit conversion cannot be applied to a value.
    """
    if not isinstance(raw, dict):
        raise MappingError(f"Record must be a JSON object, got {type(raw).__name__}.")

    mapped: dict[str, Any] = dict(adapter.constants)
    for std_key, rule in adapter.field_map.items():
        if rule.source_key not in raw:
            if rule.required:
                # Leave it absent → Pydantic reports a precise "required" error.
                continue
            continue

        value = raw[rule.source_key]
        if rule.factor is not None and value is not None:
            value = _apply_factor(value, rule.factor, std_key, rule.source_key)
        mapped[std_key] = value

    return mapped

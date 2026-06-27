"""
Pydantic schemas for Featherless vision model output.
Strict validation: extra fields rejected, types enforced.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class PaperRegisterExtraction(BaseModel):
    """
    Expected JSON output from Featherless vision model.
    All fields optional — the LLM should return null for unreadable fields,
    never omit the key or invent alternatives.
    """
    farmer_name: Optional[str] = Field(
        default=None,
        description="Full name as written on register",
        examples=["Mary Wanjiru", "John Ochieng"]
    )
    phone_number: Optional[str] = Field(
        default=None,
        description="Phone number with or without country code",
        examples=["+254712345678", "0712345678"]
    )
    plot_size: Optional[float] = Field(
        default=None,
        description="Numeric value only, no unit",
        examples=[2.5, 10.0, 0.5]
    )
    unit: Optional[str] = Field(
        default=None,
        description="Must be 'acres' or 'hectares' if present",
        examples=["acres", "hectares"]
    )
    crop_type: Optional[str] = Field(
        default=None,
        description="Crop in English, lowercase",
        examples=["maize", "cassava", "rice"]
    )
    season: Optional[str] = Field(
        default=None,
        description="Season identifier",
        examples=["2025 Long Rains", "Short Rains 2024"]
    )
    cooperative_name: Optional[str] = Field(
        default=None,
        description="Name of cooperative or organization",
        examples=["Kirinyaga Farmers Cooperative"]
    )
    date: Optional[str] = Field(
        default=None,
        description="Date as written, ISO preferred but original accepted",
        examples=["2025-03-15", "15/03/2025"]
    )
    officer_name: Optional[str] = Field(
        default=None,
        description="Field officer who collected the data",
        examples=["Alfred Munga"]
    )

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_lower = v.lower().strip()
        if v_lower in ("acres", "acre", "ac"):
            return "acres"
        if v_lower in ("hectares", "hectare", "ha", "h"):
            return "hectares"
        raise ValueError(f"Unit must be 'acres' or 'hectares', got: {v}")

    @field_validator("crop_type")
    @classmethod
    def normalize_crop(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.lower().strip()

    @field_validator("phone_number")
    @classmethod
    def clean_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        # Strip spaces, dashes, keep digits and leading +
        cleaned = "".join(c for c in v if c.isdigit() or c == "+")
        if len(cleaned) < 10:
            raise ValueError(f"Phone number too short: {v}")
        return cleaned

    @field_validator("plot_size")
    @classmethod
    def positive_size(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if v <= 0:
            raise ValueError(f"Plot size must be positive, got: {v}")
        return v

    class Config:
        # Reject any fields not defined above — prevents LLM hallucinations
        extra = "forbid"
        # Allow population by field name or alias
        populate_by_name = True


class LLMExtractionResult(BaseModel):
    """
    Wrapper for the full LLM response including metadata.
    """
    extraction: PaperRegisterExtraction
    raw_response: str = Field(description="Original LLM output string for audit")
    model_used: str = Field(description="Which Featherless model processed this")
    processed_at: str = Field(description="ISO timestamp of processing")
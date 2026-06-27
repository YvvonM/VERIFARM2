"""
Pure data models. No dependencies.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ExtractedField:
    value: str
    confidence: float
    raw_match: str


@dataclass
class OCRClaim:
    claim_type: str
    value: str
    confidence: float
    method: str
    raw_text: str
    extracted_fields: dict
    document_ref: str
    processed_at: datetime

    def to_neo4j_dict(self) -> dict:
        return {
            "claim_type": self.claim_type,
            "value": self.value,
            "confidence": self.confidence,
            "method": self.method,
            "date": self.processed_at.isoformat(),
        }


@dataclass
class OCRResult:
    """Raw output before claim classification."""
    raw_text: str
    fields: dict[str, ExtractedField]
    image_path: str
    processed_at: datetime
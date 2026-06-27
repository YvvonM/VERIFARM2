"""
Field extraction from OCR text. Regex-based, deterministic.
"""

import re
from typing import Optional

from .config import (
    ACRE_TO_HECTARE,
    CROP_KEYWORDS,
    DATE_PATTERNS,
    HECTARE_PATTERNS,
    NAME_PATTERNS,
)
from .models import ExtractedField


def extract_hectares(text: str) -> Optional[ExtractedField]:
    text_lower = text.lower()
    
    for pattern in HECTARE_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            raw_value = match.group(1)
            unit = match.group(0).split()[-1] if len(match.group(0).split()) > 1 else 'ha'
            
            try:
                num = float(raw_value)
                if 'acre' in unit:
                    hectares = round(num * ACRE_TO_HECTARE, 3)
                    normalized = str(hectares)
                    conf = 0.60
                else:
                    normalized = str(round(num, 3))
                    conf = 0.75
                
                return ExtractedField(
                    value=normalized,
                    confidence=conf,
                    raw_match=match.group(0)
                )
            except ValueError:
                continue
    return None


def extract_crop(text: str) -> Optional[ExtractedField]:
    text_lower = text.lower()
    
    for crop in CROP_KEYWORDS:
        if crop in text_lower:
            idx = text_lower.find(crop)
            start = max(0, idx - 20)
            end = min(len(text), idx + len(crop) + 20)
            return ExtractedField(
                value=crop,
                confidence=0.65,
                raw_match=text[start:end].strip()
            )
    return None


def extract_name(text: str) -> Optional[ExtractedField]:
    for pattern in NAME_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if len(name) > 2:
                return ExtractedField(
                    value=name,
                    confidence=0.60,
                    raw_match=match.group(0)
                )
    return None


def extract_date(text: str) -> Optional[ExtractedField]:
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return ExtractedField(
                value=match.group(1),
                confidence=0.70,
                raw_match=match.group(0)
            )
    return None
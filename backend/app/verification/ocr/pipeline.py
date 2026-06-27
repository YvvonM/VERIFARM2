"""
OCR pipeline: Featherless Qwen 3.6 vision only.
No Tesseract dependency. Works on Vercel, local, anywhere.
"""

import os
from datetime import datetime, timezone
from typing import Optional

from .llm_vision_fallback import llm_extract, llm_to_extracted_fields
from .models import OCRClaim


def process(
    image_path: str,
    document_id: str,
    verifying_org_id: str,
    verifying_org_name: str,
) -> OCRClaim:
    """
    Single-path OCR: Featherless Qwen 3.6 vision model.
    No Tesseract, no system dependencies.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(image_path)
    
    # Direct to LLM vision
    result = llm_extract(image_path)
    fields = llm_to_extracted_fields(result)
    
    # Determine primary claim
    if "land_size_ha" in fields:
        claim_type, value = "land_size", fields["land_size_ha"].value
    elif "crop_type" in fields:
        claim_type, value = "crop_type", fields["crop_type"].value
    elif "farmer_name" in fields:
        claim_type, value = "identity", fields["farmer_name"].value
    else:
        claim_type, value = "unstructured", result.raw_response[:200]
    
    # Compute overall confidence
    confs = [f.confidence for f in fields.values()]
    overall_conf = round(min(confs) * 0.90, 2) if confs else 0.50
    
    return OCRClaim(
        claim_type=claim_type,
        value=value,
        confidence=overall_conf,
        method="paper_register_ocr_llm_vision",
        raw_text=result.raw_response,
        extracted_fields={k: v.__dict__ for k, v in fields.items()},
        document_ref=document_id,
        processed_at=datetime.now(timezone.utc),
    )
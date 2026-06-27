import re
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from PIL import Image
import pytesseract
# Tesseract-based extractor. Shares the ONE canonical claim type and config with
# the vision pipeline (app.verification.ocr) so both converge on the same
# OCRClaim → claim_bridge → reified graph write path.
from app.verification.ocr.config import (
    HECTARE_PATTERNS, ACRE_TO_HECTARE, NAME_PATTERNS, DATE_PATTERNS,
)
from app.verification.ocr.models import ExtractedField, OCRClaim

def _extract_hectares(text: str) -> Optional[ExtractedField]:
    """
    Find land area, normalize to hectares. Tries regex first;
    returns None if no match.
    """
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
                else:
                    normalized = str(round(num, 3))
                
               
                conf = 0.75 if 'ha' in unit or 'hectare' in unit else 0.60
                
                return ExtractedField(
                    value=normalized,
                    confidence=conf,
                    raw_match=match.group(0)
                )
            except ValueError:
                continue
    
    return None


def _extract_crop(text: str) -> Optional[ExtractedField]:
    """Extract crop type — simple regex, could be LLM-enhanced."""
    text_lower = text.lower()
    
    crop_keywords = [
        'maize', 'cassava', 'rice', 'beans', 'sorghum', 
        'millet', 'wheat', 'potato', 'yam', 'cowpea'
    ]
    
    for crop in crop_keywords:
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

def _extract_name(text: str) -> Optional[ExtractedField]:
    """Extract farmer name — regex on common label patterns."""
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

def _extract_date(text: str) -> Optional[ExtractedField]:
    """Extract date from register."""
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return ExtractedField(
                value=match.group(1),
                confidence=0.70,
                raw_match=match.group(0)
            )
    return None


def _compute_overall_confidence(fields: dict) -> float:
    """
    Conservative: overall confidence is the minimum of field confidences,
    then dampened further because OCR itself is noisy.
    """
    if not fields:
        return 0.0
    
    field_confs = [f.confidence for f in fields.values()]
    min_conf = min(field_confs)
    
    ocr_penalty = 0.90
    
    return round(min_conf * ocr_penalty, 2)

def process_paper_register(
    image_path: str,
    document_id: str,
    farmer_id: Optional[str] = None,
) -> OCRClaim:
    """
    Full pipeline: image - OCR text - structured claim - Neo4j-ready object.
    
    Args:
        image_path: Path to paper register photo
        document_id: Unique ID for this document (for Neo4j Document node)
        farmer_id: If known, links claim to specific farmer; else needs manual matching
    
    Returns:
        OCRClaim ready for Neo4j ingestion
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    
     
    image = Image.open(image_path)
    raw_text = pytesseract.image_to_string(image)
    
    
    extracted = {}
    
    hectares = _extract_hectares(raw_text)
    if hectares:
        extracted["land_size_ha"] = hectares
    
    crop = _extract_crop(raw_text)
    if crop:
        extracted["crop_type"] = crop
    
    name = _extract_name(raw_text)
    if name:
        extracted["farmer_name"] = name
    
    date = _extract_date(raw_text)
    if date:
        extracted["register_date"] = date
    
    if "land_size_ha" in extracted:
        primary_claim_type = "land_size"
        primary_value = extracted["land_size_ha"].value
    elif "crop_type" in extracted:
        primary_claim_type = "crop_type"
        primary_value = extracted["crop_type"].value
    else:
        primary_claim_type = "unstructured"
        primary_value = raw_text[:1200] 
    
   
    claim = OCRClaim(
        claim_type=primary_claim_type,
        value=primary_value,
        confidence=_compute_overall_confidence(extracted),
        method="paper_register_ocr",
        raw_text=raw_text,
        extracted_fields={k: v.__dict__ for k, v in extracted.items()},
        document_ref=document_id,
        processed_at=datetime.utcnow(),
    )
    
    return claim

def claim_to_neo4j_cypher(claim: OCRClaim, farmer_id: str) -> str:
    """
    DEPRECATED. Prefer the single reified ingestion path:

        from app.verification.claim_bridge import ocr_claim_to_bundle
        from app.database.graph_ingestion import GraphIngestionService
        bundle = ocr_claim_to_bundle(farmer_id, claim, institution_id, institution_name)
        if bundle:
            with GraphIngestionService() as svc:
                svc.ingest_payload_bundles([bundle])

    That path is fully parameterized and writes the canonical reified shape
    ((:Institution)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(:Farmer)) that the
    reputation/cross-check queries consume.

    This helper builds Cypher by string interpolation (injection-prone) and
    emits the older (:Claim)-[:ABOUT]->(:Farmer) / -[:DERIVED_FROM]->(:Document)
    shape, which the trust layer does not traverse. Kept only for reference.
    """
    import warnings

    warnings.warn(
        "claim_to_neo4j_cypher is deprecated; use claim_bridge.ocr_claim_to_bundle "
        "with graph_ingestion.GraphIngestionService instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    cypher = f"""
    MATCH (f:Farmer {{id: '{farmer_id}'}})
    CREATE (d:Document {{
        id: '{claim.document_ref}',
        document_type: 'paper_register',
        image_ref: '{claim.document_ref}',
        processed_at: '{claim.processed_at.isoformat()}'
    }})
    CREATE (c:Claim {{
        id: 'claim_{claim.document_ref}',
        claim_type: '{claim.claim_type}',
        value: '{claim.value}',
        confidence: {claim.confidence},
        method: '{claim.method}',
        date: '{claim.processed_at.date().isoformat()}'
    }})
    CREATE (c)-[:DERIVED_FROM]->(d)
    CREATE (c)-[:ABOUT]->(f)
    RETURN c.id as claim_id, c.confidence as confidence
    """
    return cypher


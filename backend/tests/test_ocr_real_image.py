"""
Test OCR pipeline with a local image file.
"""

import sys
import os
import argparse

import pytest

# Needs the tesseract binary, sample images and (optionally) live credentials —
# excluded from the default CI run via `-m "not integration"`.
pytestmark = pytest.mark.integration

# Load .env before any imports that need it
load_dotenv = pytest.importorskip("dotenv").load_dotenv
load_dotenv()  # Loads .env from current directory or walks up

# Now imports will see the env vars
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.verification.ocr.pipeline import process
from app.verification.ocr.ingest import ingest_ocr_claim


# Renamed off the `test_` prefix: this is a manual CLI demo (needs a real image +
# live key), not a pytest unit test, so pytest should not try to collect it.
def run_real_image(image_path: str, farmer_id: str = "farmer_ke_001"):
    if not os.path.exists(image_path):
        print(f"❌ File not found: {image_path}")
        sys.exit(1)
    
    print("=" * 70)
    print("VERIFARM OCR — FEATHERLESS VISION TEST")
    print("=" * 70)
    print(f"Image: {image_path}")
    print(f"Size: {os.path.getsize(image_path) / 1024:.1f} KB")
    print("-" * 70)
    
    print("\n▶ STEP 1: OCR Pipeline (Featherless Qwen 3.6)")
    print("-" * 40)
    
    claim = process(
        image_path=image_path,
        document_id=f"doc_{os.path.basename(image_path).replace('.', '_')}",
        verifying_org_id="coop_kirinyaga_001",
        verifying_org_name="Kirinyaga Farmers Cooperative",
    )
    
    print(f"Method used:        {claim.method}")
    print(f"Claim type:         {claim.claim_type}")
    print(f"Value:              {claim.value}")
    print(f"Overall confidence: {claim.confidence}")
    print(f"Processed at:       {claim.processed_at}")
    
    print("\n▶ STEP 2: Extracted Fields")
    print("-" * 40)
    
    if claim.extracted_fields:
        for field_name, data in claim.extracted_fields.items():
            print(f"  {field_name:20s} | value: {data['value']:<20s} | conf: {data['confidence']:.2f}")
    else:
        print("  No fields extracted")
    
    print("\n▶ STEP 3: Raw Text (first 500 chars)")
    print("-" * 40)
    print(claim.raw_text[:500])
    if len(claim.raw_text) > 500:
        print(f"... ({len(claim.raw_text) - 500} more chars)")
    
    print("\n▶ STEP 4: Persist via the reified ingestion path")
    print("-" * 40)

    try:
        written = ingest_ocr_claim(
            farmer_id=farmer_id,
            claim=claim,
            institution_id="coop_kirinyaga_001",
            institution_name="Kirinyaga Farmers Cooperative",
        )
        print(f"Reified claims written to Neo4j: {written}")
    except Exception as exc:  # demo: a missing DB shouldn't crash extraction
        print(f"[skip ingest] {type(exc).__name__}: {exc}")
    
    print("\n▶ STEP 5: Routing Decision")
    print("-" * 40)
    
    if claim.confidence >= 0.70:
        print("✓ AUTO_ACCEPT")
    elif claim.confidence >= 0.50:
        print("⚠ REVIEW_QUEUE")
    else:
        print("✗ REJECT_RESCAN")
    
    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
    
    return claim


def main():
    parser = argparse.ArgumentParser(description="Test VeriFarm OCR on a local image")
    parser.add_argument("image_path", help="Path to the paper register image")
    parser.add_argument("--farmer-id", default="farmer_ke_001", help="Farmer ID")
    
    args = parser.parse_args()
    
    if not os.getenv("FEATHERLESS_API_KEY"):
        print("❌ FEATHERLESS_API_KEY not set")
        sys.exit(1)
    
    print("✓ Featherless API key found\n")
    run_real_image(args.image_path, args.farmer_id)


if __name__ == "__main__":
    main()
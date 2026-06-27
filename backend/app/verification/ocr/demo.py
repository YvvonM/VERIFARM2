"""
CLI demo. Run: python -m app.verification.ocr.demo

Extracts a paper register with the Featherless vision pipeline, then persists it
through the canonical reified path (claim_bridge -> GraphIngestionService), so the
OCR claims are visible to the trust layer, the Copilot, and the DLQ Investigator.
"""

from .pipeline import process
from .ingest import ingest_ocr_claim


def main():
    sample_path = "samples/paper_register_001.jpg"
    doc_id = "doc_register_001"
    farmer_id = "farmer_ke_001"
    org_id = "coop_kirinyaga_001"
    org_name = "Kirinyaga Farmers Cooperative"

    print(f"Processing: {sample_path}\n")

    try:
        claim = process(sample_path, doc_id, org_id, org_name)

        print(f"Claim type: {claim.claim_type}")
        print(f"Value: {claim.value}")
        print(f"Confidence: {claim.confidence}")
        print("Extracted fields:")
        for field, data in claim.extracted_fields.items():
            print(f"  {field}: {data['value']} (conf: {data['confidence']})")

        try:
            written = ingest_ocr_claim(farmer_id, claim, org_id, org_name)
            print(f"\nReified claims written to Neo4j: {written}")
        except Exception as exc:  # noqa: BLE001 - demo: a missing DB shouldn't crash extraction.
            print(f"\n[skip ingest] {type(exc).__name__}: {exc}")

    except FileNotFoundError:
        print(f"Sample not found: {sample_path}")
        print("Place a sample image or update the path.")


if __name__ == "__main__":
    main()

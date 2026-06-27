"""
VeriFarm — Streaming Translation API
=====================================
Streams form string translations key-by-key using Gemma 4 via Featherless.
Uses LangChain for cleaner LLM integration.
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/translate", tags=["translate"])

FEATHERLESS_API_KEY = os.environ.get("FEATHERLESS_API_KEY", "")
MODEL = "google/gemma-4-E4B-it"

SUPPORTED_LANGUAGES = {
    "English": "en",
    "Swahili": "sw",
    "Yoruba": "yo",
    "Hausa": "ha",
    "Igbo": "ig",
}

FORM_STRINGS = {
    "step_register": "Register",
    "step_identity": "Identity",
    "step_land": "Land",
    "step_production": "Production",
    "step_credit": "Credit",
    "register_title": "Create Your Profile",
    "register_subtitle": "Start your VeriFarm verification journey",
    "field_full_name": "Full Name",
    "field_full_name_placeholder": "e.g. John Kamau",
    "field_phone": "Phone Number",
    "field_phone_placeholder": "+254 712 345 678",
    "field_country": "Country",
    "field_country_placeholder": "Kenya",
    "field_location": "Location (Town/Village)",
    "field_location_placeholder": "e.g. Kirinyaga",
    "consent_label": "I consent to share my data with VeriFarm partners",
    "consent_sub": "This includes cooperatives, lenders, and insurers who need verified data to serve you better.",
    "btn_start": "Start Verification",
    "btn_creating": "Creating profile...",
    "identity_title": "Verify Your Identity",
    "identity_subtitle": "We check with the national registry",
    "field_national_id": "National ID / BVN",
    "field_national_id_placeholder": "Enter your ID number",
    "btn_verify_identity": "Verify Identity",
    "btn_verifying": "Verifying...",
    "land_title": "Your Farm Size",
    "land_subtitle": "Self-report + optional satellite cross-check",
    "field_farm_size": "Farm Size (hectares)",
    "field_farm_size_placeholder": "e.g. 2.5",
    "satellite_label": "Cross-check with satellite imagery",
    "satellite_sub": "We use Sentinel-2 data to verify your farm size.",
    "field_latitude": "Latitude",
    "field_longitude": "Longitude",
    "btn_continue": "Continue",
    "btn_checking": "Checking...",
    "production_title": "Production Estimate",
    "production_subtitle": "Expected harvest for this season",
    "field_estimated_tons": "Estimated Production (tons)",
    "field_estimated_tons_placeholder": "e.g. 5.0",
    "field_season": "Growing Season",
    "field_season_placeholder": "e.g. 2024 Long Rains",
    "field_crop": "Primary Crop",
    "field_crop_placeholder": "e.g. Maize",
    "btn_saving": "Saving...",
    "credit_title": "Credit History",
    "credit_subtitle": "Final step — check your credit standing",
    "credit_consent_label": "I consent to a credit bureau check",
    "credit_consent_sub": "This helps lenders offer you better rates. No impact on your score.",
    "btn_complete": "Complete Verification",
    "btn_checking_credit": "Checking...",
    "result_title_complete": "Verification Complete",
    "result_title_submitted": "Verification Submitted",
    "result_subtitle_approved": "Your profile is verified and ready for offers!",
    "result_subtitle_pending": "Your profile is under review. Check back soon.",
    "result_subtitle_conflict": "Some claims need manual review. We'll notify you.",
    "result_risk_score": "Risk Score",
    "result_completeness": "Complete",
    "result_offers_title": "Pre-qualified Offers",
    "btn_go_to_profile": "Go to My Profile",
    "btn_verify_another": "Verify Another Farmer",
    "error_generic": "Something went wrong. Please try again.",
    "error_phone_exists": "This phone number is already registered.",
    "error_not_found": "Farmer not found. Please register first.",
    "error_consent_required": "Consent is required to proceed.",
    "back": "Back",
    "next": "Next",
}


class TranslateRequest(BaseModel):
    language: str


async def _stream_with_langchain(language: str):
    """Stream translations key-by-key using LangChain + Featherless."""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="langchain-openai not installed. Run: pip install langchain-openai"
        )

    llm = ChatOpenAI(
        model=MODEL,
        openai_api_key=FEATHERLESS_API_KEY,
        openai_api_base="https://api.featherless.ai/v1",
        streaming=True,
        temperature=0.1,
        max_tokens=50,  # Short — one value at a time
    )

    for key, english_value in FORM_STRINGS.items():
        prompt = f"""Translate this text into {language}. 
Return ONLY the translated text, nothing else, no quotes, no explanation.
Text: {english_value}"""

        translated = ""
        async for chunk in llm.astream([HumanMessage(content=prompt)]):
            translated += chunk.content

        translated = translated.strip()
        if not translated:
            translated = english_value  # fallback to English

        # Stream each key-value pair as a JSON line
        yield f"data: {json.dumps({'key': key, 'value': translated})}\n\n"

    # Signal completion
    yield f"data: {json.dumps({'done': True})}\n\n"


async def _stream_with_httpx(language: str):
    """Fallback streaming using raw httpx if langchain not available."""
    import httpx

    for key, english_value in FORM_STRINGS.items():
        prompt = f"""Translate this text into {language}.
Return ONLY the translated text, nothing else, no quotes, no explanation.
Text: {english_value}"""

        translated = ""
        async with httpx.AsyncClient(timeout=15.0) as client:
            async with client.stream(
                "POST",
                "https://api.featherless.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {FEATHERLESS_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 50,
                    "temperature": 0.1,
                    "stream": True,
                },
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and "[DONE]" not in line:
                        try:
                            chunk = json.loads(line[6:])
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            translated += delta
                        except Exception:
                            pass

        translated = translated.strip() or english_value
        yield f"data: {json.dumps({'key': key, 'value': translated})}\n\n"

    yield f"data: {json.dumps({'done': True})}\n\n"


@router.post("/stream")
async def stream_translate(req: TranslateRequest) -> StreamingResponse:
    """Stream translations key by key — each SSE event is one translated string."""

    if req.language == "English":
        async def english_stream():
            for key, value in FORM_STRINGS.items():
                yield f"data: {json.dumps({'key': key, 'value': value})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        return StreamingResponse(english_stream(), media_type="text/event-stream")

    if req.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {req.language}")

    if not FEATHERLESS_API_KEY:
        raise HTTPException(status_code=500, detail="Translation service not configured.")

    # Try LangChain first, fall back to httpx
    try:
        from langchain_openai import ChatOpenAI  # noqa: F401
        generator = _stream_with_langchain(req.language)
    except ImportError:
        logger.warning("LangChain not available, falling back to httpx")
        generator = _stream_with_httpx(req.language)

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/languages")
async def get_languages() -> dict:
    """Return supported languages."""
    return {"languages": list(SUPPORTED_LANGUAGES.keys())}

class TranslateTextRequest(BaseModel):
    language: str
    texts: dict[str, str]

@router.post("/text")
async def translate_text(req: TranslateTextRequest) -> dict:
    """Translate a dict of key->value strings in one shot."""
    if req.language == "English":
        return req.texts

    if req.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {req.language}")

    if not FEATHERLESS_API_KEY:
        raise HTTPException(status_code=500, detail="Translation service not configured.")

    import httpx
    results = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for key, value in req.texts.items():
            prompt = f"""Translate this text into {req.language}.
Return ONLY the translated text, nothing else, no quotes, no explanation.
Text: {value}"""
            res = await client.post(
                "https://api.featherless.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {FEATHERLESS_API_KEY}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 80, "temperature": 0.1},
            )
            data = res.json()
            results[key] = data["choices"][0]["message"]["content"].strip() or value

    return results
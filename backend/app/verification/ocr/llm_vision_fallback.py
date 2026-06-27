"""
Featherless vision fallback with Pydantic validation.
"""

import base64
import json
import re
from datetime import datetime
from typing import Optional

from .llm_schemas import PaperRegisterExtraction, LLMExtractionResult


VISION_PROMPT = """Extract fields from this paper register image.
Return ONLY a JSON object with exactly these keys and no others:
{
    "farmer_name": string or null,
    "phone_number": string or null,
    "plot_size": number or null,
    "unit": "acres" or "hectares" or null,
    "crop_type": string or null,
    "season": string or null,
    "cooperative_name": string or null,
    "date": string or null,
    "officer_name": string or null
}

Rules:
- Use null for unreadable fields, never omit keys
- plot_size: number only, no unit text
- unit: only "acres" or "hectares"
- crop_type: lowercase English
- Return valid JSON only, no markdown, no explanation
"""


def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def strip_thinking(raw: str) -> str:
    """
    Remove model 'thinking' content from a raw LLM response.

    Handles three cases seen across Featherless-hosted reasoning models:
    1. Well-formed <think>...</think> pairs.
    2. A dangling </think> with NO opening tag (seen with Qwen 3.6 on
       Featherless -- the opener gets swallowed somewhere in the template/
       streaming layer, but the closer survives in the text).
    3. No thinking tags at all (pass-through, e.g. non-reasoning models).
    """
    if "</think>" in raw:
        # Whatever precedes the LAST </think> is reasoning. Taking
        # everything after it is correct whether or not <think> opened it.
        raw = raw.rsplit("</think>", 1)[-1]
    else:
        # Defensive: handles a well-formed pair if for some reason the
        # closing tag check above didn't fire (shouldn't happen, but cheap).
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)

    return raw.strip()


def extract_json_block(raw: str) -> str:
    """
    After thinking is stripped, pull out the JSON object even if it's
    still wrapped in markdown fences or has stray text around it.
    """
    cleaned = strip_thinking(raw)

    # Strip ```json / ``` fences (as actual fence patterns, not char sets)
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())

    # If there's still leading/trailing junk, grab the outermost {...}
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)

    return cleaned.strip()


def llm_extract(
    image_path: str,
    model: Optional[str] = None,
) -> LLMExtractionResult:
    """
    Send image to the Featherless vision model and validate output with Pydantic.

    Uses the single, shared, env-driven LLM client (``app.agent.qwen_llm`` —
    ``langchain_openai.ChatOpenAI`` pointed at Featherless), so there is no longer
    a separate OCR Featherless client or a hardcoded model id. The model defaults
    to ``FEATHERLESS_VISION_MODEL`` (a Qwen2.5-VL variant).

    Raises ValidationError if the LLM hallucinates fields or returns bad types.
    """
    from langchain_core.messages import HumanMessage

    from app.agent.qwen_llm import get_llm, get_vision_model_name

    model = model or get_vision_model_name()
    b64_image = image_to_base64(image_path)

    message = HumanMessage(content=[
        {"type": "text", "text": VISION_PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
    ])

    response = get_llm(model=model).invoke([message])
    raw = response.content if isinstance(response.content, str) else str(response.content)

    # Strip reasoning ("thinking") content + markdown fences, then isolate
    # the JSON object. This replaces the old `.strip("```json")` approach,
    # which only stripped individual characters and never handled the
    # <think>/</think> reasoning block at all.
    clean = extract_json_block(raw)

    # Parse to dict first
    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON: {e}\n"
            f"Cleaned: {clean[:500]}\n"
            f"Raw: {raw[:500]}"
        )

    # Strict Pydantic validation — catches hallucinated fields, wrong types
    extraction = PaperRegisterExtraction.model_validate(data)

    return LLMExtractionResult(
        extraction=extraction,
        raw_response=raw,
        model_used=model,
        processed_at=datetime.utcnow().isoformat()
    )


def llm_to_extracted_fields(result: LLMExtractionResult) -> dict:
    """
    Convert validated LLM output to ExtractedField objects.
    """
    from .extractors import ExtractedField
    from .config import ACRE_TO_HECTARE

    llm = result.extraction
    fields = {}

    if llm.farmer_name:
        fields["farmer_name"] = ExtractedField(
            value=llm.farmer_name,
            confidence=0.75,
            raw_match="llm_vision_extraction"
        )

    if llm.phone_number:
        fields["phone_number"] = ExtractedField(
            value=llm.phone_number,
            confidence=0.80,
            raw_match="llm_vision_extraction"
        )

    if llm.plot_size is not None and llm.unit:
        if llm.unit == "acres":
            hectares = round(llm.plot_size * ACRE_TO_HECTARE, 3)
            conf = 0.70
        else:
            hectares = round(llm.plot_size, 3)
            conf = 0.85

        fields["land_size_ha"] = ExtractedField(
            value=str(hectares),
            confidence=conf,
            raw_match=f"{llm.plot_size} {llm.unit}"
        )

    if llm.crop_type:
        fields["crop_type"] = ExtractedField(
            value=llm.crop_type,
            confidence=0.75,
            raw_match="llm_vision_extraction"
        )

    if llm.date:
        fields["register_date"] = ExtractedField(
            value=llm.date,
            confidence=0.70,
            raw_match="llm_vision_extraction"
        )

    if llm.cooperative_name:
        fields["cooperative"] = ExtractedField(
            value=llm.cooperative_name,
            confidence=0.65,
            raw_match="llm_vision_extraction"
        )

    if llm.season:
        fields["season"] = ExtractedField(
            value=llm.season,
            confidence=0.65,
            raw_match="llm_vision_extraction"
        )

    if llm.officer_name:
        fields["officer_name"] = ExtractedField(
            value=llm.officer_name,
            confidence=0.60,
            raw_match="llm_vision_extraction"
        )

    return fields
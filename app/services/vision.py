"""
Receipt parsing via Gemini Vision API.

Exposes a single `parse_receipt` function. To swap to a different vision LLM
(GLM-4V, OpenAI GPT-4o, Claude), replace only this file.
"""
import asyncio
import json
import logging
from io import BytesIO
from datetime import date
from decimal import Decimal, InvalidOperation

from google import genai
from google.genai import types
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "gemini-2.5-flash"
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Lazy-initialize the Gemini client to avoid crash on startup if unused."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client

# Categories sent to the model so it picks from the predefined list.
_CATEGORIES = [
    "Food",
    "Transport",
    "Utilities",
    "Rent",
    "Healthcare",
    "Shopping",
    "Entertainment",
    "Others",
]

_SYSTEM_PROMPT = f"""You are a receipt parser. Extract the following fields from the receipt image.
Return ONLY a JSON object — no markdown, no explanation.

Fields:
- date: ISO 8601 date string (YYYY-MM-DD), or null if not found
- amount: total amount as a number (e.g. 45.50), or null if not found
- currency: ISO 4217 currency code (e.g. MYR, USD, SGD), default to MYR if unclear
- vendor: the business or store name, or null if not found
- category: best matching category from this list: {_CATEGORIES}
- raw_text: all text found on the receipt, as a single string

Example output:
{{"date": "2026-04-11", "amount": 45.50, "currency": "MYR", "vendor": "McDonald's", "category": "Food", "raw_text": "McDonald's\\nDate: 11/04/2026\\nTotal: RM 45.50"}}
"""


def _resize_if_needed(image_bytes: bytes, max_bytes: int = 4 * 1024 * 1024) -> tuple[bytes, str]:
    """Reduce image to under max_bytes by halving dimensions iteratively.
    Returns (resized_bytes, original_mime_type).
    """
    mime = _detect_mime(image_bytes)
    if len(image_bytes) <= max_bytes:
        return image_bytes, mime
    img = Image.open(BytesIO(image_bytes))
    fmt = "JPEG" if mime == "image/jpeg" else "PNG"
    while len(image_bytes) > max_bytes:
        w, h = img.size
        img = img.resize((w // 2, h // 2), Image.LANCZOS)
        buf = BytesIO()
        if fmt == "PNG":
            img.save(buf, format="PNG", optimize=True)
        else:
            img.save(buf, format="JPEG", quality=85)
        image_bytes = buf.getvalue()
    return image_bytes, mime


def _detect_mime(image_bytes: bytes) -> str:
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"  # fallback


async def parse_receipt(image_bytes: bytes) -> dict:
    """
    Send receipt image to Gemini Vision and return parsed fields.

    Returns a dict with keys: date, amount, currency, vendor, category, raw_text.
    Any field may be None if not found. Retries once on rate limit (429).
    """
    image_bytes, mime_type = _resize_if_needed(image_bytes)

    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    async def _call() -> str:
        loop = asyncio.get_event_loop()
        client = _get_client()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=_MODEL,
                contents=[_SYSTEM_PROMPT, image_part],
            ),
        )
        return response.text

    try:
        text = await _call()
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
            logger.warning("Gemini rate limit hit, retrying in 5s")
            await asyncio.sleep(5)
            text = await _call()
        else:
            logger.error("Gemini API error: %s", e)
            raise

    # strip accidental markdown fences
    clean = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        logger.warning("Gemini returned non-JSON: %s", text[:200])
        return {
            "date": None,
            "amount": None,
            "currency": "MYR",
            "vendor": None,
            "category": None,
            "raw_text": text,
        }

    parsed_date = None
    if data.get("date"):
        try:
            parsed_date = date.fromisoformat(str(data["date"]))
        except ValueError:
            pass

    parsed_amount = None
    if data.get("amount") is not None:
        try:
            parsed_amount = Decimal(str(data["amount"]))
        except InvalidOperation:
            pass

    return {
        "date": parsed_date,
        "amount": parsed_amount,
        "currency": str(data.get("currency") or "MYR").upper()[:3],
        "vendor": data.get("vendor"),
        "category": data.get("category"),
        "raw_text": data.get("raw_text"),
    }

"""
Receipt parsing via a vision LLM on OpenRouter.

Exposes a single `parse_receipt` function. Models are tried in the order given by
VISION_MODELS (OpenRouter falls back to the next on provider errors), so switching
models is a config change. To leave OpenRouter, replace only this file.
"""
import asyncio
import base64
import json
import logging
from io import BytesIO
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = 60.0

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
- date: ISO 8601 date string (YYYY-MM-DD) of the purchase/payment, or null if not shown.
  Do not use other dates on the receipt (delivery, exam, expiry, travel dates). Mind the country's
  date order: DD/MM/YYYY in SG/MY/VN/ID/EU, YYYY/MM/DD or YYYY年MM月DD日 in CN/JP.
- amount: final total paid, as a plain JSON number in the currency's main unit, or null if not found.
  Normalise number formats — thousands separators vary:
    "150.000 ₫" or "150,000đ" -> 150000;  "Rp 25.500" -> 25500;  "¥1,280" -> 1280;  "12,50 €" -> 12.50;  "1.234,56 €" -> 1234.56
  JPY, VND and IDR have no cents: their amounts are whole numbers.
- currency: ISO 4217 code — ONLY if the receipt shows evidence for it, otherwise null.
  Enough on its own: an explicit code (SGD, MYR, CNY/RMB, JPY, EUR, VND, IDR, USD, THB, ...) or an
  unambiguous symbol: S$ -> SGD, RM -> MYR, 元/人民币 -> CNY, 円 -> JPY, € -> EUR, ₫/đ -> VND, Rp -> IDR, US$ -> USD.
  Ambiguous — need a country clue as well: "$" (SGD, USD, AUD, HKD, ...) and "¥"/"￥" (CNY or JPY).
  Country clues:
    Singapore -> SGD: "Singapore" in address, GST Reg No / 9% GST, Pte Ltd, +65, PayNow, NETS
    Malaysia -> MYR: Sdn Bhd / Bhd, SST, Malaysian state or city, +60, DuitNow, Touch 'n Go, MyKasih
    China -> CNY: simplified Chinese, 发票 / 增值税 / 合计 / 实收, +86, 支付宝 Alipay, 微信支付 WeChat Pay
    Japan -> JPY: hiragana/katakana, 税込 / 消費税 / 合計 / 領収書, 〒 postcode, +81, PayPay, Suica
    Vietnam -> VND: Vietnamese (Tổng cộng, Thành tiền, Hóa đơn), +84, MoMo, ZaloPay, VNPay
    Indonesia -> IDR: Indonesian (Total Bayar, Kembalian, PPN, NPWP), "Jl." street, +62, QRIS, GoPay, OVO, DANA
    Eurozone -> EUR: MwSt/USt, TVA, IVA, BTW, ALV tax lines; EU country addresses
  A postcode's digit count alone is NOT evidence (Singapore and China both use 6 digits).
- currency_evidence: the clue(s) used for currency (e.g. "Sdn Bhd + SST 6%"), or null if none
- vendor: the business or store name, or null if not found
- category: best matching category from this list: {_CATEGORIES}
- raw_text: all text found on the receipt, as a single string

Example output:
{{"date": "2026-04-11", "amount": 45.50, "currency": "MYR", "currency_evidence": "RM symbol", "vendor": "McDonald's", "category": "Food", "raw_text": "McDonald's\\nDate: 11/04/2026\\nTotal: RM 45.50"}}
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
    Send receipt image to the vision model and return parsed fields.

    Returns a dict with keys: date, amount, currency, currency_evidence, vendor, category, raw_text.
    Any field may be None if not found; currency is None unless the receipt shows evidence for it.
    Retries once on rate limit (429) or server error.
    """
    image_bytes, mime_type = _resize_if_needed(image_bytes)
    image_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode()}"
    body = {
        "models": settings.vision_model_list,
        "temperature": 0,
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": _SYSTEM_PROMPT},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]}],
    }

    async def _call() -> str:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _API_URL,
                json=body,
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}", "X-Title": "expense-log"},
            )
        resp.raise_for_status()
        data = resp.json()
        logger.info("Receipt parsed by %s", data.get("model"))
        return data["choices"][0]["message"]["content"]

    try:
        text = await _call()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429 or e.response.status_code >= 500:
            logger.warning("Vision API %s, retrying in 5s", e.response.status_code)
            await asyncio.sleep(5)
            text = await _call()
        else:
            logger.error("Vision API error: %s %s", e.response.status_code, e.response.text[:200])
            raise

    # strip accidental markdown fences
    clean = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        logger.warning("Vision model returned non-JSON: %s", text[:200])
        return {
            "date": None,
            "amount": None,
            "currency": None,
            "currency_evidence": None,
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

    currency = str(data.get("currency") or "").strip().upper()
    if not (len(currency) == 3 and currency.isalpha()):
        currency = None

    return {
        "date": parsed_date,
        "amount": parsed_amount,
        "currency": currency,
        "currency_evidence": data.get("currency_evidence") or None,
        "vendor": data.get("vendor"),
        "category": data.get("category"),
        "raw_text": data.get("raw_text"),
    }

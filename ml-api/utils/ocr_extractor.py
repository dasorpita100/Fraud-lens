# utils/ocr_extractor.py
# OCR (Optical Character Recognition) utilities to extract text from screenshots.
# Used for Email, SMS, and UPI screenshot uploads. Requires Tesseract-OCR installed.
# Install: https://github.com/tesseract-ocr/tesseract
# Windows: typically C:\Program Files\Tesseract-OCR\tesseract.exe

import os
import re
from pathlib import Path

import numpy as np

try:
    import pytesseract
    from PIL import Image
    import PIL.Image
    _OCR_DEPS = True
except ImportError:
    _OCR_DEPS = False
    Image = None
    PIL = None


def _tesseract_available() -> bool:
    """Check if Tesseract is installed and reachable."""
    if not _OCR_DEPS:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def is_ocr_available() -> bool:
    """Public check for health endpoint: True if Tesseract is installed and usable."""
    return _tesseract_available()


def preprocess_image(image_path: str):
    """
    Preprocess image for better OCR accuracy: grayscale, threshold, optional resize.
    Improves readability on phone screenshots and low-contrast images.
    """
    if not _OCR_DEPS or not Image:
        raise RuntimeError("Pillow is required for image preprocessing")
    img = Image.open(image_path).convert("RGB")
    # Convert to grayscale to reduce noise
    img = img.convert("L")
    # Get pixel data for simple threshold (binarize)
    arr = np.array(img)
    # Adaptive: use median as threshold for phone screens (often dark text on light)
    thresh = max(1, int(np.median(arr)) - 20)
    arr = np.where(arr < thresh, 0, 255)
    img = Image.fromarray(arr.astype(np.uint8))
    # Resize if too small (min dimension ~300px for readable text)
    w, h = img.size
    min_side = 300
    if min(w, h) < min_side:
        scale = min_side / min(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return img


def extract_text_from_image(image_path: str) -> str:
    """
    Extract text from an image using Tesseract OCR.
    Uses PSM 6 (uniform block of text). Preprocesses image for better accuracy.
    Returns cleaned text (whitespace normalized, no leading/trailing junk).
    """
    if not _OCR_DEPS:
        raise RuntimeError("pytesseract and Pillow are required for OCR")
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    try:
        img = preprocess_image(image_path)
        # PSM 6 = Assume a single uniform block of text (good for screenshots)
        config = "--psm 6 -c preserve_interword_spaces=1"
        text = pytesseract.image_to_string(img, config=config)
        # Clean: normalize whitespace, remove excessive newlines/special chars
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[^\w\s@.\-:/₹,]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as e:
        raise RuntimeError(f"OCR failed: {e}") from e


def clean_sms_ocr(ocr_text: str) -> str:
    """
    Remove timestamps, contact names, and UI chrome from SMS screenshot OCR.
    Tries to keep only the message bubble content. Heuristic-based for college project.
    """
    if not ocr_text or not isinstance(ocr_text, str):
        return ""
    text = ocr_text.strip()
    # Remove common timestamp patterns: 10:45 AM, 12:30 PM, Yesterday, Today, 3/15/2025
    text = re.sub(r"\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:Yesterday|Today|Tomorrow)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", " ", text)
    # Remove "Message" / "SMS" / carrier labels
    text = re.sub(r"\b(?:Message|SMS|Sent|Delivered|Read)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_upi_fields(ocr_text: str) -> dict:
    """
    Parse UPI-related fields from OCR text (GPay, PhonePe, Paytm, BHIM screenshots).
    Extracts: amount (₹), UPI IDs (xxx@yyy), date/time, status (Success/Pending/Failed).
    Returns dict with parsed fields and confidence hints. Missing fields use safe defaults.
    """
    result = {
        "amount": None,
        "receiver_upi": None,
        "sender_upi": None,
        "status": None,
        "date": None,
        "time": None,
    }
    if not ocr_text or not isinstance(ocr_text, str):
        return result
    text = ocr_text.strip()
    # Amount: ₹ 5,000 or Rs. 5000 or 5000.00
    amount_match = re.search(r"[₹Rs.]?\s*([0-9,]+(?:\.[0-9]{2})?)", text)
    if amount_match:
        try:
            amount_str = amount_match.group(1).replace(",", "")
            result["amount"] = float(amount_str)
        except ValueError:
            pass
    # UPI IDs: word@word (e.g. merchant@ybl, user@okaxis)
    upi_ids = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9.-]+", text)
    if upi_ids:
        result["receiver_upi"] = upi_ids[0]
        if len(upi_ids) > 1:
            result["sender_upi"] = upi_ids[1]
    # Status keywords
    if re.search(r"\bSuccess\b", text, re.IGNORECASE):
        result["status"] = "Success"
    elif re.search(r"\bPending\b", text, re.IGNORECASE):
        result["status"] = "Pending"
    elif re.search(r"\bFailed\b", text, re.IGNORECASE):
        result["status"] = "Failed"
    # Simple date/time patterns
    date_m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", text)
    if date_m:
        result["date"] = f"{date_m.group(1)}/{date_m.group(2)}/{date_m.group(3)}"
    time_m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", text, re.IGNORECASE)
    if time_m:
        result["time"] = f"{time_m.group(1)}:{time_m.group(2)}" + (f" {time_m.group(3)}" if time_m.lastindex >= 3 and time_m.group(3) else "")
    return result


# UPI / payment-app wording — used to avoid classifying random OCR as a transaction
_UPI_CONTEXT_RE = re.compile(
    r"\b(?:"
    r"phonepe|google\s*pay|gpay|paytm|bhim|amazon\s*pay|"
    r"upi\s*(?:reference|ref\.?|id|transaction|payment|lite)|"
    r"paid\b|debited|credited|"
    r"money\s+(?:sent|received|transferred)|"
    r"transaction\s+(?:id|successful|success|completed|pending|failed)|"
    r"\butr\b|virtual\s+payment\s+address|\bvpa\b|"
    r"send\s+money|receive\s+money|transfer\s+to|"
    r"@(?:ybl|okaxis|paytm|okicici|axl|ibl|pnb|sbi|hdfc|yapl|axisbank|icici)"
    r")\b",
    re.IGNORECASE,
)


def is_plausible_upi_content(parsed: dict, raw_text: str) -> bool:
    """
    True if OCR looks like a UPI / payment-app screenshot.
    Random images still produce numbers and text; without a VPA or payment-app cues,
    we should not run the UPI model (defaults like unknown@unknown look like fraud).
    """
    if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
        return False
    if not isinstance(parsed, dict):
        parsed = {}
    has_vpa = bool(parsed.get("receiver_upi") or parsed.get("sender_upi"))
    if has_vpa:
        return True
    tl = raw_text.lower()
    if not _UPI_CONTEXT_RE.search(tl):
        return False
    # Keyword match alone: require something transaction-like to reduce false positives
    amt = parsed.get("amount")
    status = parsed.get("status")
    if amt is not None and float(amt) > 0:
        return True
    if status:
        return True
    return False

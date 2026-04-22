# app.py - Flask ML backend for Email, SMS, and UPI fraud detection.
# Run with: python app.py (server starts on port 5000)
# Install Tesseract for OCR: https://github.com/tesseract-ocr/tesseract
# Windows: set path below if needed:
#   import pytesseract
#   pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

import os
import re
import uuid
from pathlib import Path

# Load .env so GEMINI_API_KEY / GEMINI_API_KEYS are available
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from flask import Flask, request, jsonify
from flask_cors import CORS
import joblib
import numpy as np
from scipy.sparse import hstack
from werkzeug.utils import secure_filename

# Optional: if Tesseract not in PATH (common on Windows), set path before using OCR.
# Auto-set on Windows if Tesseract is in default install location:
try:
    import pytesseract
    _tesseract_exe = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.name == "nt" and os.path.isfile(_tesseract_exe):
        pytesseract.pytesseract.tesseract_cmd = _tesseract_exe
except ImportError:
    pass

MAX_UPLOAD_MB = 5
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024  # 5MB max upload
# Allow React frontend on localhost:3000 to call all routes
CORS(app, origins=["http://localhost:3000"], supports_credentials=True)

# Paths
BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Allowed image types for screenshot upload
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[-1].lower() in ALLOWED_EXTENSIONS


# --- Lazy-loaded models (load on first use) ---
_email_model = None
_email_vectorizer = None
_sms_model = None
_sms_vectorizer = None
_upi_model = None


def _load_email_models():
    global _email_model, _email_vectorizer
    if _email_model is None and (MODELS_DIR / "email_model.pkl").exists():
        _email_model = joblib.load(MODELS_DIR / "email_model.pkl")
        _email_vectorizer = joblib.load(MODELS_DIR / "email_vectorizer.pkl")
    return _email_model, _email_vectorizer


def _load_sms_models():
    global _sms_model, _sms_vectorizer
    if _sms_model is None and (MODELS_DIR / "sms_model.pkl").exists():
        _sms_model = joblib.load(MODELS_DIR / "sms_model.pkl")
        _sms_vectorizer = joblib.load(MODELS_DIR / "sms_vectorizer.pkl")
    return _sms_model, _sms_vectorizer


def _load_upi_model():
    global _upi_model
    if _upi_model is None and (MODELS_DIR / "upi_model.pkl").exists():
        _upi_model = joblib.load(MODELS_DIR / "upi_model.pkl")
    return _upi_model


# --- Feature extraction (must match training pipeline) ---
def _email_reasons(text: str, verdict: str, score: int) -> list:
    """Build human-readable reasons for email prediction."""
    reasons = []
    from utils.feature_extractor import (
        count_urgent_words,
        count_urls,
        sender_domain_mismatch_score,
        has_ip_url,
    )
    from utils import spam_intel as si

    if count_urgent_words(text) > 0:
        reasons.append("Contains urgent or pressure language")
    if count_urls(text) > 0:
        reasons.append("Contains link(s) in message")
    if has_ip_url(text) > 0:
        reasons.append("Contains IP-address link (often used to hide real domain)")
    if sender_domain_mismatch_score(text) > 0:
        reasons.append("Sender domain may not match claimed brand")
    if si.obfuscation_spam_score(text) >= 0.5:
        reasons.append("Defanged or obfuscated URLs detected")
    if si.attachment_phishing_score(text) >= 0.5:
        reasons.append("Risky attachment or invoice-archive pattern")
    if si.crypto_scam_score(text) >= 0.5:
        reasons.append("Crypto or wallet-related scam language")
    if si.impersonation_scam_score(text) >= 0.5:
        reasons.append("Possible BEC / impersonation wording")
    if not reasons:
        reasons.append("No strong phishing indicators detected" if verdict == "Legitimate" else "Text patterns suggest phishing")
    return reasons


def _sms_reasons(text: str, verdict: str, score: int) -> list:
    from utils.feature_extractor import count_sms_scam_keywords, count_urls
    from utils import spam_intel as si

    reasons = []
    if count_sms_scam_keywords(text) > 0:
        reasons.append("Contains common scam/OTP phishing keywords")
    if count_urls(text) > 0:
        reasons.append("Contains clickable URL(s)")
    if si.obfuscation_spam_score(text) >= 0.5:
        reasons.append("Uses defanged or obfuscated links (common in smishing)")
    if si.crypto_scam_score(text) >= 0.5:
        reasons.append("Contains crypto or investment-scam language")
    if si.impersonation_scam_score(text) >= 0.5:
        reasons.append("Possible impersonation (family, boss, or authority)")
    if si.parcel_delivery_scam_score(text) >= 0.5:
        reasons.append("Matches parcel / courier fee scams")
    if si.gift_card_scam_score(text) >= 0.5:
        reasons.append("Requests gift cards or voucher codes (high-risk pattern)")
    if si.mixed_script_risk_score(text) >= 0.5 or si.zero_width_noise_score(text) >= 0.3:
        reasons.append("Unusual characters or hidden symbols (filter evasion)")
    if not reasons:
        reasons.append("No strong scam indicators" if verdict == "Legitimate" else "Message patterns suggest scam")
    return reasons


def _upi_reasons(payload: dict, verdict: str, score: int) -> list:
    from utils.feature_extractor import upi_domain_risk_score
    reasons = []
    amount = payload.get("amount") or 0
    if amount > 50000:
        reasons.append("Large transaction amount")
    if payload.get("is_new_recipient"):
        reasons.append("Payment to new recipient")
    if payload.get("time_of_day") is not None:
        t = int(payload["time_of_day"])
        if t <= 4 or t >= 23:
            reasons.append("Transaction at odd hours")
    if payload.get("device_changed"):
        reasons.append("Device change around transaction")
    ru = str(payload.get("receiver_upi") or "")
    if ru and upi_domain_risk_score(ru) >= 0.5:
        reasons.append("Receiver uses an uncommon or unknown UPI handle domain")
    if not reasons:
        reasons.append("No strong fraud indicators" if verdict == "Legitimate" else "Transaction patterns may be risky")
    return reasons


# Gemini explanation is now in Node.js backend (POST /api/gemini/explain). Frontend calls it after ML result.

def _attach_spam_intel(result: dict, text: str, mode: str) -> None:
    """Augment prediction with URLhaus + StopForumSpam metadata and optional extra reasons."""
    try:
        from utils.spam_intel import collect_spam_intel_report, spam_api_flags_for_reasons

        report = collect_spam_intel_report(text, mode)
        result["spam_intel"] = report
        for r in spam_api_flags_for_reasons(report):
            if r not in result.get("reasons", []):
                result.setdefault("reasons", []).append(r)
    except Exception as e:
        result["spam_intel"] = {"error": str(e)}


def _predict_email(text: str):
    """Run email model on text. Returns (verdict, score, reasons) or None if model missing."""
    clf, vec = _load_email_models()
    if clf is None or vec is None:
        return None
    from utils.feature_extractor import get_email_extra_features
    tfidf = vec.transform([text])
    extra = get_email_extra_features(text)
    X = hstack([tfidf, extra])
    proba = clf.predict_proba(X)[0]
    pred = clf.predict(X)[0]
    # score 0-100: 100 = most phishing
    score = int(round(proba[1] * 100)) if len(proba) > 1 else 50
    verdict = "Phishing" if pred == 1 else "Legitimate"
    reasons = _email_reasons(text, verdict, score)
    return {"verdict": verdict, "score": min(100, max(0, score)), "reasons": reasons}


def _predict_sms(text: str):
    clf, vec = _load_sms_models()
    if clf is None or vec is None:
        return None
    from utils.feature_extractor import get_sms_extra_features
    tfidf = vec.transform([text])
    extra = get_sms_extra_features(text)
    X = hstack([tfidf, extra])
    proba = clf.predict_proba(X)[0]
    pred = clf.predict(X)[0]
    score = int(round(proba[1] * 100)) if len(proba) > 1 else 50
    verdict = "Scam" if pred == 1 else "Legitimate"
    reasons = _sms_reasons(text, verdict, score)
    return {"verdict": verdict, "score": min(100, max(0, score)), "reasons": reasons}


def _build_upi_features(payload: dict):
    """Build feature vector in same order as train_upi.build_features / upi_feature_vector."""
    from utils.feature_extractor import upi_feature_vector
    amount = float(payload.get("amount", 0))
    sender_upi = str(payload.get("sender_upi", ""))
    receiver_upi = str(payload.get("receiver_upi", ""))
    time_of_day = int(payload.get("time_of_day", 12))
    day_of_week = int(payload.get("day_of_week", 0))
    txn_type = str(payload.get("transaction_type", "P2P"))
    is_new = payload.get("is_new_recipient")
    device_changed = payload.get("device_changed")
    return upi_feature_vector(
        amount,
        sender_upi,
        receiver_upi,
        time_of_day,
        day_of_week,
        txn_type,
        1 if is_new else 0,
        1 if device_changed else 0,
    )


def _predict_upi(payload: dict):
    clf = _load_upi_model()
    if clf is None:
        return None
    X = _build_upi_features(payload)
    pred = clf.predict(X)[0]
    proba = clf.predict_proba(X)[0] if hasattr(clf, "predict_proba") else [0.33, 0.33, 0.34]
    # 0=Legitimate, 1=Suspicious, 2=Fraud
    verdict_map = {0: "Legitimate", 1: "Suspicious", 2: "Fraud"}
    verdict = verdict_map.get(int(pred), "Legitimate")
    # Score: map class to 0-100 (Fraud=high score)
    idx = int(pred)
    score = int(round(proba[idx] * 100)) if idx < len(proba) else 50
    if verdict == "Legitimate":
        score = 100 - score
    elif verdict == "Suspicious":
        score = 50
    score = min(100, max(0, score))
    reasons = _upi_reasons(payload, verdict, score)
    return {"verdict": verdict, "score": score, "reasons": reasons}


# --- OCR helpers ---
def _get_text_from_request():
    """Get input text: from JSON 'text' or from uploaded image via OCR."""
    # Option A: JSON body with "text"
    if request.is_json and request.get_json(silent=True):
        data = request.get_json()
        if isinstance(data, dict) and "text" in data and data["text"]:
            return data["text"].strip(), None, None  # text, extracted_text, parsed_fields

    # Option B: multipart file
    if "file" in request.files:
        f = request.files["file"]
        if f.filename and allowed_file(f.filename):
            ext = f.filename.rsplit(".", 1)[-1].lower()
            safe = secure_filename(f"{uuid.uuid4().hex}.{ext}")
            path = UPLOADS_DIR / safe
            try:
                f.save(str(path))
                if path.stat().st_size > app.config["MAX_CONTENT_LENGTH"]:
                    if path.exists():
                        path.unlink()
                    return None, None, "File too large"
                from utils.ocr_extractor import extract_text_from_image, is_ocr_available
                if not is_ocr_available():
                    if path.exists():
                        path.unlink()
                    return None, None, "OCR not available (Tesseract not installed)"
                raw = extract_text_from_image(str(path))
            except Exception as e:
                if path.exists():
                    path.unlink()
                return None, None, str(e)
            finally:
                if path.exists():
                    try:
                        path.unlink()
                    except Exception:
                        pass
            if not raw or not raw.strip():
                return None, None, "Could not extract text from image. Please try a clearer screenshot."
            return raw.strip(), raw.strip(), None  # text, extracted_text, no parsed_fields
        elif f.filename:
            return None, None, "Invalid file type. Allowed: jpg, jpeg, png, webp"

    return None, None, "Missing 'text' in JSON or valid image 'file' in form-data"


def _get_upi_payload_from_request():
    """Get UPI input: from JSON body (payload or raw 'text' from frontend OCR), or from uploaded file."""
    if request.is_json and request.get_json(silent=True):
        data = request.get_json()
        if not isinstance(data, dict):
            return None, None, "Invalid JSON"
        # Full payload from form or API
        if "amount" in data or "sender_upi" in data or "receiver_upi" in data:
            return data, None, None
        # Raw OCR text from frontend (Tesseract.js in browser)
        if "text" in data and data.get("text"):
            raw = (data["text"] or "").strip()
            if not raw:
                return None, None, "Empty text"
            try:
                from utils.ocr_extractor import extract_upi_fields
                parsed = extract_upi_fields(raw)
            except Exception as e:
                return None, None, str(e)
            payload = {
                "amount": parsed.get("amount") or 0,
                "sender_upi": parsed.get("sender_upi") or "unknown@unknown",
                "receiver_upi": parsed.get("receiver_upi") or "unknown@unknown",
                "time_of_day": 12,
                "day_of_week": 0,
                "transaction_type": "P2P",
                "is_new_recipient": False,
                "device_changed": False,
            }
            if parsed.get("time"):
                tm = re.search(r"(\d{1,2}):(\d{2})", str(parsed.get("time", "")))
                if tm:
                    payload["time_of_day"] = int(tm.group(1)) % 24
            parsed_export = {k: v for k, v in parsed.items() if v is not None}
            return payload, raw, parsed_export

    if "file" in request.files:
        f = request.files["file"]
        if f.filename and allowed_file(f.filename):
            ext = f.filename.rsplit(".", 1)[-1].lower()
            safe = secure_filename(f"{uuid.uuid4().hex}.{ext}")
            path = UPLOADS_DIR / safe
            try:
                f.save(str(path))
                if path.stat().st_size > app.config["MAX_CONTENT_LENGTH"]:
                    if path.exists():
                        path.unlink()
                    return None, None, "File too large"
                from utils.ocr_extractor import extract_text_from_image, extract_upi_fields, is_ocr_available
                if not is_ocr_available():
                    if path.exists():
                        path.unlink()
                    return None, None, "OCR not available"
                raw = extract_text_from_image(str(path))
                parsed = extract_upi_fields(raw)
            except Exception as e:
                if path.exists():
                    path.unlink()
                return None, None, str(e)
            finally:
                if path.exists():
                    try:
                        path.unlink()
                    except Exception:
                        pass
            if not raw or not raw.strip():
                return None, None, "Could not extract text from image."
            # Build payload from parsed UPI fields with safe defaults
            payload = {
                "amount": parsed.get("amount") or 0,
                "sender_upi": parsed.get("sender_upi") or "unknown@unknown",
                "receiver_upi": parsed.get("receiver_upi") or "unknown@unknown",
                "time_of_day": 12,
                "day_of_week": 0,
                "transaction_type": "P2P",
                "is_new_recipient": False,
                "device_changed": False,
            }
            # Try to infer time from parsed date/time if present
            if parsed.get("time"):
                # Simple: extract hour if possible
                tm = re.search(r"(\d{1,2}):(\d{2})", str(parsed.get("time", "")))
                if tm:
                    payload["time_of_day"] = int(tm.group(1)) % 24
            parsed_export = {k: v for k, v in parsed.items() if v is not None}
            return payload, raw.strip(), parsed_export
        elif f.filename:
            return None, None, "Invalid file type"

    return None, None, "Missing UPI JSON body or image file"


# --- Routes ---

@app.route("/", methods=["GET"])
def index():
    """Root route: list available ML API endpoints."""
    return jsonify({
        "service": "FraudLens ML API",
        "endpoints": {
            "GET /health": "Health check (status, ocr_available)",
            "POST /predict/email": "Phishing detection (JSON: text, or multipart: file)",
            "POST /predict/sms": "SMS scam detection (JSON: text, or multipart: file)",
            "POST /predict/upi": "UPI fraud detection (JSON: amount, sender_upi, ... or multipart: file)",
            "POST /intel/spam": "Spam intel only: URLhaus + StopForumSpam (JSON: text, mode: sms|email)",
        },
        "health": "/health",
    })


@app.route("/health", methods=["GET"])
def health():
    """Health check. ocr_available is True if Tesseract is installed and usable."""
    try:
        from utils.ocr_extractor import is_ocr_available
        ocr_ok = is_ocr_available()
    except Exception:
        ocr_ok = False
    return jsonify({"status": "ok", "ocr_available": ocr_ok})


@app.route("/predict/email", methods=["POST"])
def predict_email():
    """Accepts JSON { \"text\": \"...\" } OR multipart form-data with file (image)."""
    text, extracted_text, err = _get_text_from_request()
    if err:
        return jsonify({"error": err}), 400
    if not text:
        return jsonify({"error": "No text provided"}), 400

    result = _predict_email(text)
    if result is None:
        result = {
            "verdict": "Legitimate",
            "score": 50,
            "reasons": ["Model not loaded (run train/train_email.py first). This is a mock response."],
        }
    _attach_spam_intel(result, text, "email")
    if extracted_text is not None:
        result["extracted_text"] = extracted_text
    return jsonify(result)


@app.route("/predict/sms", methods=["POST"])
def predict_sms():
    """Accepts JSON { \"text\": \"...\" } OR multipart form-data with file (image)."""
    text, extracted_text, err = _get_text_from_request()
    if err:
        return jsonify({"error": err}), 400
    if not text:
        return jsonify({"error": "No text provided"}), 400

    # For SMS screenshot, optionally clean OCR to focus on message body
    from utils.ocr_extractor import clean_sms_ocr
    text_clean = clean_sms_ocr(text) if text else text
    if not text_clean.strip():
        text_clean = text

    result = _predict_sms(text_clean)
    if result is None:
        result = {
            "verdict": "Legitimate",
            "score": 50,
            "reasons": ["Model not loaded (run train/train_sms.py first). Mock response."],
        }
    _attach_spam_intel(result, text_clean, "sms")
    if extracted_text is not None:
        result["extracted_text"] = extracted_text
    return jsonify(result)


@app.route("/predict/upi", methods=["POST"])
def predict_upi():
    """Accepts JSON with amount, sender_upi, receiver_upi, ... OR multipart file (screenshot)."""
    payload, extracted_text, parsed_or_err = _get_upi_payload_from_request()
    if isinstance(parsed_or_err, str):
        return jsonify({"error": parsed_or_err}), 400
    if not payload:
        return jsonify({"error": "No UPI data provided"}), 400

    # OCR / pasted text: do not run the UPI model on random images (defaults look like fraud).
    if extracted_text is not None:
        from utils.ocr_extractor import extract_upi_fields, is_plausible_upi_content

        parsed_check = extract_upi_fields(extracted_text)
        if not is_plausible_upi_content(parsed_check, extracted_text):
            out = {
                "verdict": "Not a UPI screenshot",
                "score": 5,
                "reasons": [
                    "No UPI ID (e.g. name@okaxis) or clear payment-app text was found in this image.",
                    "Use the UPI tab only for payment screenshots (Google Pay, PhonePe, Paytm, etc.). For other images, use Email or SMS scan.",
                ],
                "extracted_text": extracted_text,
            }
            if isinstance(parsed_or_err, dict):
                out["parsed_fields"] = parsed_or_err
            return jsonify(out)

    result = _predict_upi(payload)
    if result is None:
        result = {
            "verdict": "Legitimate",
            "score": 50,
            "reasons": ["Model not loaded (run train/train_upi.py first). Mock response."],
        }
    if extracted_text is not None:
        result["extracted_text"] = extracted_text
    if isinstance(parsed_or_err, dict):
        result["parsed_fields"] = parsed_or_err
    return jsonify(result)


@app.route("/intel/spam", methods=["POST"])
def spam_intel_only():
    """
    Public spam-intel lookups (no classifier): URLhaus + StopForumSpam.
    JSON body: { "text": "...", "mode": "sms" | "email" }.
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if len(text) < 3:
        return jsonify({"error": "text must be at least 3 characters"}), 400
    mode = (data.get("mode") or "sms").lower()
    if mode not in ("sms", "email"):
        mode = "sms"
    from utils.spam_intel import collect_spam_intel_report

    return jsonify(collect_spam_intel_report(text, mode))


if __name__ == "__main__":
    # Port 5001 so Node auth backend can use 5000. Set REACT_APP_ML_API_URL=http://localhost:5001 in frontend .env
    app.run(host="0.0.0.0", port=5001, debug=True)
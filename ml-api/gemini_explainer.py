# gemini_explainer.py
# All Gemini AI logic lives in the BACKEND here. API keys stay server-side (never sent to frontend).
# Called by app.py after ML prediction to add a detailed "why legit / why fake" explanation.

import os


def _get_api_keys():
    """Collect keys from GEMINI_API_KEY and GEMINI_API_KEYS (comma-separated)."""
    keys = []
    single = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if single:
        keys.append(single)
    for k in (os.environ.get("GEMINI_API_KEYS") or "").split(","):
        k = k.strip()
        if k and k not in keys:
            keys.append(k)
    return keys


def _build_prompt(scan_type: str, content_preview: str, verdict: str, score: int, reasons: list) -> str:
    """Build action-specific prompt for email / SMS / UPI."""
    content = (content_preview or "")[:800]
    reasons_text = ", ".join(reasons) if reasons else "None listed"
    is_risky = verdict in ("Phishing", "Scam", "Fraud", "Suspicious")

    if scan_type.lower() == "email":
        if is_risky:
            return f"""You are an email security expert. A user ran a phishing check on an email. Our AI classified it as **{verdict}** (risk score: {score}/100). Technical signals: {reasons_text}.

Email content (excerpt):
---
{content}
---

Give a clear, detailed explanation in 3–4 sentences:
1) WHY this was marked as suspicious/phishing (e.g. urgent language, suspicious links, sender mismatch, fake branding).
2) What specific red flags in the content support that.
3) What the user should do (e.g. do not click links, verify sender, contact the company directly).

Write in plain language. No bullet points in the final answer—use a short paragraph."""
        else:
            return f"""You are an email security expert. A user ran a phishing check on an email. Our AI classified it as **{verdict}** (risk score: {score}/100). Technical signals: {reasons_text}.

Email content (excerpt):
---
{content}
---

Give a clear, detailed explanation in 2–3 sentences:
1) WHY this was marked as legitimate/safe (e.g. normal tone, no urgent demands, no suspicious links, or expected sender).
2) What in the content suggests it is not a phishing attempt.

Write in plain language. No bullet points—use a short paragraph."""

    if scan_type.lower() == "sms":
        if is_risky:
            return f"""You are an SMS/scam prevention expert. A user ran a scam check on an SMS. Our AI classified it as **{verdict}** (risk score: {score}/100). Technical signals: {reasons_text}.

SMS content:
---
{content}
---

Give a clear, detailed explanation in 3–4 sentences:
1) WHY this was marked as scam/fraudulent (e.g. fake OTP, prize/lottery, urgent action, payment links, impersonation).
2) What specific phrases or patterns in the message are typical of SMS scams.
3) What the user should do (e.g. do not reply, do not share OTP, block the number, report).

Write in plain language. No bullet points—use a short paragraph."""
        else:
            return f"""You are an SMS/scam prevention expert. A user ran a scam check on an SMS. Our AI classified it as **{verdict}** (risk score: {score}/100). Technical signals: {reasons_text}.

SMS content:
---
{content}
---

Give a clear, detailed explanation in 2–3 sentences:
1) WHY this was marked as legitimate/safe (e.g. normal transactional message, known sender, no prize/OTP pressure).
2) What in the message suggests it is not a scam.

Write in plain language. No bullet points—use a short paragraph."""

    # UPI / transaction
    if is_risky:
        return f"""You are a UPI/digital payment fraud expert. A user ran a fraud check on a UPI payment or screenshot. Our AI classified it as **{verdict}** (risk score: {score}/100). Technical signals: {reasons_text}.

Transaction/content (excerpt):
---
{content}
---

Give a clear, detailed explanation in 3–4 sentences:
1) WHY this was marked as fraud/suspicious (e.g. odd time, large amount, new recipient, unknown UPI ID, device change).
2) What specific risk factors support that.
3) What the user should do (e.g. verify recipient, avoid paying until confirmed, contact bank if already paid).

Write in plain language. No bullet points—use a short paragraph."""
    else:
        return f"""You are a UPI/digital payment fraud expert. A user ran a fraud check on a UPI payment or screenshot. Our AI classified it as **{verdict}** (risk score: {score}/100). Technical signals: {reasons_text}.

Transaction/content (excerpt):
---
{content}
---

Give a clear, detailed explanation in 2–3 sentences:
1) WHY this was marked as legitimate/safe (e.g. normal amount, known recipient, typical timing, trusted UPI handle).
2) What in the transaction suggests lower fraud risk.

Write in plain language. No bullet points—use a short paragraph."""


def get_explanation(scan_type: str, content_preview: str, verdict: str, score: int, reasons: list) -> str | None:
    """
    Generate a detailed explanation using Gemini. All logic is in the backend; API key never sent to frontend.
    Tries multiple keys (GEMINI_API_KEY, GEMINI_API_KEYS) if one fails.
    Returns None if no key, content too short, or all keys fail.
    """
    api_keys = _get_api_keys()
    if not api_keys:
        print("Gemini: no API key set. Add GEMINI_API_KEY or GEMINI_API_KEYS to ml-api/.env")
        return None
    if not content_preview or len(content_preview.strip()) < 5:
        return None
    try:
        import google.generativeai as genai
    except ImportError:
        print("Gemini: google-generativeai not installed. Run: pip install google-generativeai")
        return None
    prompt = _build_prompt(scan_type, content_preview, verdict, score, reasons)
    last_err = None
    for api_key in api_keys:
        if not api_key:
            continue
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            last_err = e
            continue
    if last_err:
        print("Gemini: explanation failed:", getattr(last_err, "message", str(last_err)))
    return None

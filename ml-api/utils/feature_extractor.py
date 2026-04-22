# utils/feature_extractor.py
# Shared feature extraction logic for Email, SMS, and UPI fraud detection.
# Used by both training scripts and the Flask prediction pipeline.

import re
import numpy as np

# --- Email phishing features ---

# Words commonly used in phishing emails to create urgency or fear
URGENT_WORDS = [
    "urgent", "verify", "suspended", "click", "login", "account", "confirm",
    "immediately", "action required", "expire", "limited time", "winner",
    "congratulations", "claim", "password", "security", "blocked", "locked",
    "refund", "update payment", "unusual activity", "confirm your identity",
    "wire transfer", "gift card", "re-authenticate", "credential", "malware",
    "unauthorized", "dear customer", "invoice attached", "tax refund", "irs",
    "social security", "aadhaar", "kyc", "otp", "one time password",
]


def count_urgent_words(text: str) -> int:
    """Count how many urgent/phishing-style words appear in the email body."""
    if not text or not isinstance(text, str):
        return 0
    text_lower = text.lower()
    return sum(1 for w in URGENT_WORDS if w in text_lower)


def count_urls(text: str) -> int:
    """Count URLs in text using a simple regex (http/https and common patterns)."""
    if not text or not isinstance(text, str):
        return 0
    # Match http(s) URLs and bare domains like example.com/path
    url_pattern = r'https?://[^\s<>"\']+|(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s<>"\']*)?'
    return len(re.findall(url_pattern, text, re.IGNORECASE))


def extract_sender_domain(text: str) -> str | None:
    """
    Try to extract sender email domain from raw email content.
    Looks for patterns like 'From: user@domain.com' or 'Reply-To: x@y.com'.
    """
    if not text or not isinstance(text, str):
        return None
    from_match = re.search(r'(?:From|Reply-To|Sender):\s*[^\s<>]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text, re.IGNORECASE)
    if from_match:
        return from_match.group(1).lower()
    # Fallback: any email in first 500 chars
    email_match = re.search(r'[a-zA-Z0-9_.+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text[:500])
    return email_match.group(1).lower() if email_match else None


def sender_domain_mismatch_score(text: str) -> float:
    """
    Heuristic: if email body mentions well-known brands (e.g. paypal, bank names)
    but sender domain is not from that brand, return 1.0 (suspicious). Else 0.0.
    """
    if not text or not isinstance(text, str):
        return 0.0
    text_lower = text.lower()
    brand_domains = {
        "paypal": ["paypal.com"],
        "amazon": ["amazon.com", "amazon.in"],
        "microsoft": ["microsoft.com", "live.com", "outlook.com"],
        "apple": ["apple.com", "icloud.com"],
        "google": ["google.com", "gmail.com"],
        "bank": ["hdfcbank.com", "icicibank.com", "sbi.co.in"],
        "netflix": ["netflix.com"],
        "linkedin": ["linkedin.com"],
        "dhl": ["dhl.com"],
        "fedex": ["fedex.com"],
        "whatsapp": ["whatsapp.com", "facebook.com"],
    }
    sender = extract_sender_domain(text)
    if not sender:
        return 0.0
    for brand, domains in brand_domains.items():
        if brand in text_lower and not any(sender.endswith(d) or d in sender for d in domains):
            return 1.0
    return 0.0


def _text_len_norm(text: str, cap: float = 10_000.0) -> float:
    if not text:
        return 0.0
    return min(len(text), cap) / cap


def _digit_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(c.isdigit() for c in text) / max(len(text), 1)


def _uppercase_ratio(text: str) -> float:
    if not text:
        return 0.0
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def has_ip_url(text: str) -> float:
    """1.0 if text contains URL with IPv4 literal (common in phishing)."""
    if not text or not isinstance(text, str):
        return 0.0
    return 1.0 if re.search(r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", text) else 0.0


def get_email_extra_features(text: str) -> np.ndarray:
    """Stacked with TF-IDF: urgency, URLs, domain mismatch, length, digit/upper ratios, IP-URL, exclamation + spam-URL intel."""
    from utils.spam_intel import email_local_spam_features

    if not text or not isinstance(text, str):
        text = ""
    t = text
    exclaim = min(t.count("!"), 10) / 10.0
    base = [
        count_urgent_words(t),
        count_urls(t),
        sender_domain_mismatch_score(t),
        _text_len_norm(t),
        _digit_ratio(t),
        _uppercase_ratio(t),
        has_ip_url(t),
        exclaim,
    ]
    base.extend(email_local_spam_features(t))
    return np.array([base])


# --- SMS scam features ---

SMS_SCAM_KEYWORDS = [
    "otp", "prize", "won", "click", "free", "urgent", "congratulations",
    "winner", "claim", "cash", "lottery", "bank", "verify", "account",
    "suspended", "kbps", "reply", "sms", "unsubscribe", "toll", "call",
    "reward", "selected", "reply win", "text back", "congrats",
    "bitcoin", "crypto", "airdrop", "gift card", "customs", "parcel",
    "redelivery", "your mum", "lost phone", "wire transfer", "binance",
    "metamask", "seed phrase", "double your", "act now", "limited offer",
    "tax refund", "income tax", "kyc", "loan approved", "credit score",
]


def count_sms_scam_keywords(text: str) -> int:
    """Count scam-related keywords in SMS text."""
    if not text or not isinstance(text, str):
        return 0
    text_lower = text.lower()
    return sum(1 for w in SMS_SCAM_KEYWORDS if w in text_lower)


def _sms_digit_run_score(text: str) -> float:
    """Long digit sequences often appear in fake OTP / prize scams."""
    if not text:
        return 0.0
    m = re.findall(r"\d{5,}", text)
    return min(len(m), 5) / 5.0


def get_sms_extra_features(text: str) -> np.ndarray:
    """Keywords, URLs, length, digit density, digit-run score + local spam-URL intel — stacked with TF-IDF."""
    from utils.spam_intel import sms_local_spam_features

    if not text or not isinstance(text, str):
        text = ""
    t = text
    tl = len(t)
    len_norm = min(tl, 2000) / 2000.0
    has_http = 1.0 if re.search(r"https?://", t, re.I) else 0.0
    base = [
        count_sms_scam_keywords(t),
        count_urls(t),
        len_norm,
        _digit_ratio(t),
        has_http,
        _sms_digit_run_score(t),
    ]
    base.extend(sms_local_spam_features(t))
    return np.array([base])


# --- UPI feature encoding ---

# Known UPI provider domains and risk (low = trusted, high = unknown)
UPI_DOMAIN_RISK = {
    "paytm": 0.0, "ybl": 0.0, "okaxis": 0.0, "okicici": 0.0, "axl": 0.0,
    "ibl": 0.0, "phonepe": 0.0, "gpay": 0.0, "amazonpay": 0.0,
    "bhim": 0.0, "upi": 0.2, "bank": 0.2,
}
DEFAULT_UPI_RISK = 0.8  # Unknown domains get higher risk


def upi_domain_risk_score(upi_id: str) -> float:
    """Extract domain from UPI ID (e.g. user@okaxis -> okaxis) and return risk score 0-1."""
    if not upi_id or not isinstance(upi_id, str) or "@" not in upi_id:
        return DEFAULT_UPI_RISK
    domain = upi_id.split("@")[-1].lower().strip()
    return UPI_DOMAIN_RISK.get(domain, DEFAULT_UPI_RISK)


# Transaction type encoding for UPI model
TRANSACTION_TYPE_MAP = {"P2P": 0, "P2M": 1, "Collect": 2, "Other": 3}


def encode_transaction_type(txn_type: str) -> int:
    """Map transaction type string to integer for model input."""
    return TRANSACTION_TYPE_MAP.get(str(txn_type).strip(), 3)


def upi_feature_vector(
    amount: float,
    sender_upi: str,
    receiver_upi: str,
    time_of_day: int,
    day_of_week: int,
    transaction_type: str,
    is_new_recipient: bool | int,
    device_changed: bool | int,
) -> np.ndarray:
    """
    Single-row feature vector; must stay in sync with train_upi.build_features order.
    Adds cyclical hour, log amount, weekend flag, and receiver–sender risk gap.
    """
    receiver_risk = upi_domain_risk_score(receiver_upi)
    sender_risk = upi_domain_risk_score(sender_upi)
    amt = max(0.0, float(amount))
    log_amt = np.log1p(amt)
    hr = int(time_of_day) % 24
    hr_sin = float(np.sin(2 * np.pi * hr / 24.0))
    hr_cos = float(np.cos(2 * np.pi * hr / 24.0))
    dow = int(day_of_week) % 7
    is_weekend = 1.0 if dow >= 5 else 0.0
    risk_delta = float(receiver_risk) - float(sender_risk)
    txn_enc = encode_transaction_type(transaction_type)
    is_new = 1.0 if int(is_new_recipient) else 0.0
    dev = 1.0 if int(device_changed) else 0.0
    return np.array([[
        amt,
        float(hr),
        float(dow),
        is_new,
        dev,
        float(txn_enc),
        receiver_risk,
        sender_risk,
        log_amt,
        hr_sin,
        hr_cos,
        is_weekend,
        risk_delta,
    ]])

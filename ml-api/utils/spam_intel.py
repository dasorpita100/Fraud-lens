# utils/spam_intel.py
# Local spam/phishing signals for ML (always available at train & inference time)
# plus optional public API lookups (URLhaus, StopForumSpam) for explanations / metadata.

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import numpy as np

# --- Known short-link / redirect hosts (common in SMS & email spam) ---
SHORTLINK_HOST_FRAGMENTS = (
    "bit.ly", "tinyurl", "goo.gl", "t.co", "ow.ly", "buff.ly", "is.gd",
    "cutt.ly", "rebrand.ly", "short.link", "tiny.cc", "adf.ly", "linktr.ee",
    "rb.gy", "shorturl", "cli.re", "s.id", "sh.st", "pic.gd", "vm.tiktok",
    "discord.gg", "t.me", "telegram.me", "wa.me", "chat.whatsapp",
)

# --- High-risk TLDs often abused in phishing / spam ---
RISKY_TLDS = (
    ".tk", ".ml", ".ga", ".cf", ".gq", ".xyz", ".top", ".club", ".work",
    ".click", ".link", ".buzz", ".loan", ".date", ".racing", ".science",
)

# --- Disposable / throwaway email domains (subset; local heuristic only) ---
DISPOSABLE_EMAIL_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "tempmail.com", "10minutemail.com",
    "throwaway.email", "yopmail.com", "trashmail.com", "fakeinbox.com",
    "dispostable.com", "getnada.com", "maildrop.cc", "sharklasers.com",
})


def extract_http_urls(text: str) -> list[str]:
    """Extract http(s) URLs; normalizes hxxp(s):// obfuscation for matching and API checks."""
    if not text:
        return []
    norm = re.sub(r"hxxps?://", "http://", text, flags=re.IGNORECASE)
    return re.findall(r"https?://[^\s<>\'\"]+", norm, flags=re.IGNORECASE)


def extract_email_addresses(text: str) -> list[str]:
    if not text:
        return []
    pat = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    return re.findall(pat, text)


def _host_from_url(url: str) -> str:
    try:
        u = url.split("//", 1)[-1].split("/", 1)[0].lower()
        return u.split("@")[-1]
    except Exception:
        return ""


def shortlink_score(text: str) -> float:
    """0-1: density of known URL shorteners."""
    urls = extract_http_urls(text)
    if not urls:
        return 0.0
    n = sum(1 for u in urls if any(s in u.lower() for s in SHORTLINK_HOST_FRAGMENTS))
    return min(1.0, n / max(len(urls), 1))


def risky_tld_score(text: str) -> float:
    """0-1: URLs ending with suspicious TLDs."""
    urls = extract_http_urls(text)
    if not urls:
        return 0.0
    n = sum(1 for u in urls if any(u.lower().rstrip("/").endswith(t) or t in u.lower() for t in RISKY_TLDS))
    return min(1.0, n / max(len(urls), 1))


def disposable_email_score(text: str) -> float:
    """1.0 if any email uses a known disposable domain."""
    for em in extract_email_addresses(text):
        dom = em.split("@")[-1].lower().strip()
        if dom in DISPOSABLE_EMAIL_DOMAINS:
            return 1.0
    return 0.0


def sms_promo_spam_score(text: str) -> float:
    """0-1: toll-free / prize / reply-to-win style SMS patterns."""
    if not text:
        return 0.0
    t = text.lower()
    hits = 0
    patterns = (
        r"call\s+\d{10,}",
        r"toll[\s-]?free",
        r"text\s+(win|yes|stop|start)\b",
        r"reply\s+(win|yes|stop)\b",
        r"\b(win|winner|won)\b.*\b(cash|prize|reward)\b",
        r"\b(urgent|limited time|act now)\b",
        r"\bkbps\b",
        r"\b\d{6,}\b.*\b(otp|pin|code)\b",
    )
    for p in patterns:
        if re.search(p, t):
            hits += 1
    return min(1.0, hits / 5.0)


def url_density_per_1k_chars(text: str) -> float:
    """Normalized URL count for very short SMS."""
    urls = extract_http_urls(text)
    if not text:
        return 0.0
    n = len(urls)
    return min(1.0, (n * 1000) / max(len(text), 1) / 10.0)


def obfuscation_spam_score(text: str) -> float:
    """hxxp, bracket-dot URLs, defanged links — common evasion."""
    if not text:
        return 0.0
    t = text.lower()
    hits = 0
    if re.search(r"hxxps?://|h\*\*\*p://|\[\.\]|dot\s+com|\(dot\)|w\s*w\s*w", t):
        hits += 2
    if re.search(r"https?://[^\s]+\s+\[", t):
        hits += 1
    return min(1.0, hits / 3.0)


def crypto_scam_score(text: str) -> float:
    """Crypto investment, wallet, seed phrase, airdrop scams."""
    if not text:
        return 0.0
    t = text.lower()
    keys = (
        "bitcoin", "btc", "ethereum", "eth", "usdt", "crypto wallet", "seed phrase",
        "private key", "airdrop", "binance", "coinbase", "metamask", "defi",
        "double your", "guaranteed return", "mining pool", "withdrawal fee",
    )
    c = sum(1 for k in keys if k in t)
    return min(1.0, c / 4.0)


def impersonation_scam_score(text: str) -> float:
    """Pretends to be family, boss, government, bank rep."""
    if not text:
        return 0.0
    t = text.lower()
    patterns = (
        r"\b(mum|mom|dad|son|daughter)\b.*\b(new phone|lost phone|help)\b",
        r"\b(it'?s me|this is your)\b",
        r"\b(ceo|cfo|director)\b.*\b(urgent|wire|transfer)\b",
        r"\b(income tax|gst|customs)\b.*\b(penalty|pay|link)\b",
        r"\b(hr|payroll)\b.*\b(verify|update)\b.*\b(details|bank)\b",
    )
    return min(1.0, sum(1 for p in patterns if re.search(p, t)) / 2.0)


def parcel_delivery_scam_score(text: str) -> float:
    """DHL/FedEx/customs fee / package redelivery smishing."""
    if not text:
        return 0.0
    t = text.lower()
    brands = ("dhl", "fedex", "usps", "royal mail", "blue dart", "delhivery", "aramex")
    fee = ("customs", "duty", "redelivery", "tracking", "reschedule", "fee due")
    if any(b in t for b in brands) and any(f in t for f in fee):
        return 1.0
    if re.search(r"\bparcel\b.*\b(held|stuck|pay)\b", t):
        return 0.8
    return 0.0


def multi_phone_spam_score(text: str) -> float:
    """Several phone numbers in one short message — bulk scam."""
    if not text:
        return 0.0
    # E.164-ish and grouped digits
    nums = re.findall(r"(?:\+?\d{1,3}[-.\s]?)?(?:\d{3}[-.\s]?){2,4}\d{3,}", text)
    return min(1.0, (len(nums) - 1) / 3.0) if len(nums) > 1 else 0.0


def mixed_script_risk_score(text: str) -> float:
    """Latin mixed with Cyrillic/Greek lookalikes in tokens (homoglyph bait)."""
    if not text:
        return 0.0
    has_latin = bool(re.search(r"[a-zA-Z]", text))
    has_cyr = bool(re.search(r"[\u0400-\u04FF]", text))
    has_greek = bool(re.search(r"[\u0370-\u03FF]", text))
    if has_latin and (has_cyr or has_greek):
        return 1.0
    return 0.0


def zero_width_noise_score(text: str) -> float:
    """Invisible joiners sometimes used to break filters."""
    if not text:
        return 0.0
    zw = ("\u200b", "\u200c", "\u200d", "\ufeff")
    n = sum(text.count(z) for z in zw)
    return min(1.0, n / 3.0)


def emoji_spam_pressure_score(text: str) -> float:
    """Heavy emoji + money/alert symbols — common in scam SMS."""
    if not text:
        return 0.0
    emoji_like = len(re.findall(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]", text))
    money_syms = sum(1 for c in text if c in ("\u0024", "\u00A3", "\u20AC", "\u20B9", "\u00A5"))
    return min(1.0, (emoji_like + money_syms * 2) / 12.0)


def gift_card_scam_score(text: str) -> float:
    """Gift card / voucher payment requests (BEC, refund scams)."""
    if not text:
        return 0.0
    t = text.lower()
    if re.search(r"\b(gift card|itunes|google play|steam card|voucher code)\b", t):
        if re.search(r"\b(urgent|verify|pay|send|scratch)\b", t):
            return 1.0
        return 0.6
    return 0.0


def attachment_phishing_score(text: str) -> float:
    """Risky attachment mentions in email bodies."""
    if not text:
        return 0.0
    t = text.lower()
    risky = (".exe", ".scr", ".bat", ".js", ".vbs", ".zip", ".rar", "invoice", "remittance")
    if "attach" in t or "download" in t:
        if any(x in t for x in risky):
            return 1.0
    if re.search(r"invoice[_\-]?\d+\.(pdf|zip|doc)", t):
        return 0.9
    return 0.0


def sms_local_spam_features(text: str) -> list[float]:
    """
    Twelve dimensions: URL abuse, promo patterns, obfuscation, crypto, impersonation,
    parcel scams, multi-phone, script tricks, zero-width, emoji pressure, gift cards.
    """
    if not text or not isinstance(text, str):
        text = ""
    return [
        float(shortlink_score(text)),
        float(risky_tld_score(text)),
        float(disposable_email_score(text)),
        float(sms_promo_spam_score(text)),
        float(url_density_per_1k_chars(text)),
        float(obfuscation_spam_score(text)),
        float(crypto_scam_score(text)),
        float(impersonation_scam_score(text)),
        float(parcel_delivery_scam_score(text)),
        float(multi_phone_spam_score(text)),
        float(mixed_script_risk_score(text) + zero_width_noise_score(text)) / 2.0,
        float(emoji_spam_pressure_score(text) + gift_card_scam_score(text)) / 2.0,
    ]


def generic_phishing_salutation_score(text: str) -> float:
    """Generic greetings common in bulk phishing."""
    if not text:
        return 0.0
    t = text[:2000].lower()
    patterns = (
        r"dear\s+(customer|user|member|valued)",
        r"dear\s+[\w.-]+@",
        r"hello\s+dear",
        r"attention\s+(customer|user|account)",
    )
    return 1.0 if any(re.search(p, t) for p in patterns) else 0.0


def financial_urgency_combo_score(text: str) -> float:
    """Co-occurrence of financial + urgency tokens."""
    if not text:
        return 0.0
    t = text.lower()
    fin = any(w in t for w in ("bank", "account", "card", "payment", "password", "verify", "paypal", "invoice"))
    urg = any(w in t for w in ("urgent", "suspended", "locked", "immediately", "expire", "24 hours", "verify now"))
    link = "http" in t or "www." in t or ".com" in t
    if fin and urg and link:
        return 1.0
    if fin and urg:
        return 0.6
    return 0.0


def email_local_spam_features(text: str) -> list[float]:
    """Twelve dimensions: URL risk, salutation, urgency, obfuscation, crypto, BEC, parcel, scripts, attachments."""
    if not text or not isinstance(text, str):
        text = ""
    return [
        float(shortlink_score(text)),
        float(risky_tld_score(text)),
        float(disposable_email_score(text)),
        float(generic_phishing_salutation_score(text)),
        float(financial_urgency_combo_score(text)),
        float(obfuscation_spam_score(text)),
        float(crypto_scam_score(text)),
        float(impersonation_scam_score(text)),
        float(parcel_delivery_scam_score(text)),
        float(gift_card_scam_score(text)),
        float(mixed_script_risk_score(text) + zero_width_noise_score(text)) / 2.0,
        float(attachment_phishing_score(text)),
    ]


# --- Public APIs (optional; network failures return empty / safe defaults) ---

URLHAUS_API = "https://urlhaus-api.abuse.ch/v1/url/"
SFS_API = "https://api.stopforumspam.org/api"


def urlhaus_lookup(url: str, timeout: float = 8.0) -> dict[str, Any]:
    """
    URLhaus public API (no key). Returns parsed JSON or {"error": "..."}.
    """
    if not url or not url.startswith("http"):
        return {}
    try:
        data = urllib.parse.urlencode({"url": url[:2048]}).encode()
        req = urllib.request.Request(
            URLHAUS_API,
            data=data,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        return json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return {"error": str(e), "query_status": "failed"}


def stopforumspam_email(email: str, timeout: float = 8.0) -> dict[str, Any]:
    """
    StopForumSpam email check (no API key for light use). Returns JSON or error dict.
    """
    if not email or "@" not in email:
        return {}
    try:
        q = urllib.parse.urlencode({"email": email.strip(), "json": "true"})
        url = f"{SFS_API}?{q}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        return json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return {"error": str(e), "success": False}


def collect_spam_intel_report(text: str, mode: str = "sms") -> dict[str, Any]:
    """
    Run optional API lookups for response metadata (not used as ML features).
    mode: 'sms' | 'email'
    """
    out: dict[str, Any] = {
        "mode": mode,
        "urls_checked": [],
        "urlhaus": [],
        "stopforumspam": None,
    }
    urls = extract_http_urls(text)[:5]
    for u in urls:
        r = urlhaus_lookup(u)
        entry: dict[str, Any] = {"url": u[:500]}
        qs = r.get("query_status")
        if qs == "ok" and r.get("threat"):
            entry["listed"] = True
            entry["threat"] = r.get("threat")
            entry["tags"] = r.get("tags", [])
        elif qs == "no_results":
            entry["listed"] = False
        else:
            entry["listed"] = None
            if r.get("error"):
                entry["note"] = "lookup_unavailable"
        out["urlhaus"].append(entry)
        out["urls_checked"].append(u[:500])

    emails = extract_email_addresses(text)[:2]
    if emails:
        sfs = stopforumspam_email(emails[0])
        out["stopforumspam"] = {"email": emails[0], "raw": sfs}
        em = sfs.get("email") if isinstance(sfs.get("email"), dict) else {}
        freq = em.get("frequency")
        appears = em.get("appears")
        out["stopforumspam"]["appears_in_spam_db"] = bool(appears) if appears is not None else None
        out["stopforumspam"]["frequency"] = int(freq) if freq is not None else None

    return out


def spam_api_flags_for_reasons(report: dict[str, Any]) -> list[str]:
    """Human-readable lines from collect_spam_intel_report output."""
    reasons = []
    for entry in report.get("urlhaus") or []:
        if entry.get("listed") is True:
            reasons.append(
                f"URLhaus lists a linked URL as malicious ({entry.get('threat', 'threat')})"
            )
    sfs = report.get("stopforumspam")
    if isinstance(sfs, dict) and sfs.get("appears_in_spam_db"):
        reasons.append("Sender email appears in StopForumSpam abuse database (high risk)")
    elif isinstance(sfs, dict):
        try:
            fq = int(sfs["frequency"]) if sfs.get("frequency") is not None else 0
            if fq > 50:
                reasons.append("Sender email has many spam reports on StopForumSpam")
        except (TypeError, ValueError, KeyError):
            pass
    return reasons

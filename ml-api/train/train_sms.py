# train/train_sms.py
# Trains the SMS scam classifier: TF-IDF + extra features + XGBoost.
# Auto-downloads UCI SMS Spam Collection; augments with advanced synthetic smishing.
# Saves sms_model.pkl and sms_vectorizer.pkl to ../models/

import sys
import zipfile
import io
import urllib.request
import joblib
import numpy as np
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report, roc_auc_score
from sklearn.utils.class_weight import compute_sample_weight
from scipy.sparse import hstack
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.feature_extractor import get_sms_extra_features

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# UCI archive zip endpoints often return 502; try a raw mirror first (same5,574 messages as UCI).
SMS_SPAM_RAW_URLS = (
    "https://raw.githubusercontent.com/justmarkham/pycon-2016-tutorial/master/data/sms.tsv",
)

# Official UCI zips (fallback when raw mirrors are blocked)
SMS_SPAM_ZIP_URLS = (
    "https://archive.ics.uci.edu/ml/machine-learning-databases/00228/smsspamcollection.zip",
    "http://archive.ics.uci.edu/ml/machine-learning-databases/00228/smsspamcollection.zip",
    "https://archive.ics.uci.edu/static/public/228/sms+spam+collection.zip",
)

_DOWNLOAD_UA = "Mozilla/5.0 (compatible; FraudLens-ML/1.0; +https://github.com/)"

# None = use every row after load/download (full dataset). Set to e.g. 1000 to cap for quick tests.
MAX_DATASET_SAMPLES = None
# When no real data file is available, generate this many ham + this many spam synthetically.
SYNTHETIC_PER_CLASS = 8000

# --- Legitimate SMS templates (diverse, transactional, personal) ---
_HAM_TEMPLATES = [
    "Ok see you tomorrow",
    "Call me when you're free",
    "Meeting at 5pm. Don't forget.",
    "Thanks for the update",
    "I'll be there in 10 minutes",
    "Can we reschedule to next week?",
    "Got it, thanks!",
    "Your appointment is confirmed for 3pm.",
    "Running5 min late",
    "Picked up milk on the way home",
    "Happy birthday! See you at 7",
    "The train is delayed20 mins",
    "Left your keys on the counter",
    "Dinner at mine Saturday?",
    "Please send the file when ready",
    "Confirmed for Tuesday 2pm with Dr Smith",
    "Your order #8821 shipped — track on retailer site",
    "Parking is on level B2",
    "WiFi password is on the fridge",
    "Kids soccer moved to Sunday 9am",
    "Board meeting agenda attached in email",
    "Flight landed, getting Uber",
    "Safe travels!",
    "Reminder: dentist4pm Thursday",
    "Groceries list: milk, eggs, bread",
    "Thanks for lunch today",
    "See you at the station",
    "VPN access renewed — IT sent details by email",
    "Payroll processed; payslip in portal",
    "Team lunch Friday 12:30 default room",
    "Your prescription is ready at City Pharmacy",
    "Library book due Friday — renew online",
    "Class cancelled today due to weather",
    "Rent transferred — check bank app",
    "Backup completed successfully overnight",
    "Code review comments left on PR #441",
    "Coffee machine fixed — thanks facilities",
]

# --- Spam / smishing templates (broad attack coverage) ---
_SPAM_TEMPLATES = [
    "Congratulations! You have won a prize. Click here to claim: http://win.com",
    "URGENT: Your bank account is suspended. Verify now: http://bank-verify.com",
    "Free cash! Reply WIN to get your reward.",
    "You have been selected for a lottery. Send your details to claim.",
    "OTP for your transaction is 123456. Do not share.",
    "Claim your free gift now. Limited time offer. Click http://gift.com",
    "Your account will be locked. Verify immediately at http://secure.com",
    "Congratulations winner! You won 50000. Call now to claim.",
    "Prize! Open https://bit.ly/claim-now — toll free 1800123456",
    "URGENT act now: https://tinyurl.com/verify-acct winner selected",
    "Your Netflix payment failed. Update: http://netflix-billing.xyz",
    "DHL: Parcel held — pay customs fee http://dhl-track.fake/pay",
    "FedEx: Reschedule delivery http://fedex-reschedule.ml",
    "Income Tax Dept: Refund pending. Verify PAN http://incometax-refund.xyz",
    "Your Aadhaar will be blocked. Link: http://uidai-verify.fake",
    "CRYPTO: Double your BTC in 48h — http://trade-invest.xyz",
    "AirDrop: Claim 5000 USDT wallet connect http://airdrop-claim.top",
    "Metamask: Unusual activity — verify seed http://metamask-secure.xyz",
    "Mum I lost my phone this is my new number — need200 for taxi",
    "CEO urgent: wire50k to supplier today — reply for account",
    "HR: Update bank details before payroll http://hr-portal.fake",
    "Gift cards needed for client — buy 5x $500 iTunes scratch and send codes",
    "Your package is stuck at customs pay 4999 INR http://customs-pay.in",
    "Bitly verify: https://bit.ly/3xK9mZ2 login required",
    "hxxps://secure-bank[.]com/verify — do not ignore",
    "You won! Text YES to 55665 then open https://t.co/fakeprize",
    "WhatsApp: Your account will expire. Verify: http://wa-verify.xyz",
    "Loan approved Rs 5L — zero paperwork http://instant-loan.club",
    "Credit score updated — view http://credit-fix.xyz",
    "IRS: Tax warrant — pay now http://irs-pay.tk",
    "Your son is in hospital send money urgent call 0900123456",
    "Amazon: Unauthorized order — cancel http://amazon-secure.xyz/order",
    "PayPal: Confirm identity or limited http://paypal-verify.ml",
    "Binance: Withdrawal suspended verify http://binance-auth.xyz",
    "Telegram premium gift — claim t.me/fakegiveaway",
    "Your SIM will be deactivated. Verify KYC http://sim-kyc.in",
    "Lucky draw winner! Rs 100000 — http://lucky-draw.top",
    "Free iPhone 15 — first 100 users http://apple-giveaway.xyz",
    "Your UPI limit exceeded verify http://upi-rbi.xyz",
    "Electricity bill unpaid — pay or disconnect http://bijli-pay.fake",
    "COVID relief fund — register http://gov-relief.ml",
    "You have 1 new voicemail. Listen: http://voicemail-scam.xyz",
    "Survey reward Rs 500 — complete http://survey-reward.club",
    "Your Instagram was hacked recover http://ig-recover.xyz",
    "Security alert: login from Russia verify http://secure-login.xyz",
    "Final notice: lawsuit filed pay legal fee http://legal-notice.tk",
    "Investment tip: 300% returns guaranteed http://crypto-pump.xyz",
    "Join our signal group for free trades http://t.me/pumpsignals",
    "Your FedEx package needs signature fee $2.99 http://fedex-fee.xyz",
    "Royal Mail: Fee due for redelivery http://royalmail-fee.xyz",
    "We noticed login attempt — secure account bit.ly/3fake",
    "Act now limited slots http://flash-deal.xyz",
    "You have been chosen for government grant http://grant-apply.ga",
    "Wire recall required — finance team http://wire-verify.xyz",
    "Your cloud storage full — upgrade http://cloud-lock.xyz",
    "Microsoft365 password expires today http://ms-renew.xyz",
    "Apple ID locked — unlock http://apple-unlock.xyz",
    "Google: Someone has your password http://goo-gl-security.xyz",
    "Venmo: Payment received pending verify http://venmo-pending.xyz",
    "CashApp: Send $5 to receive $500 promotion http://cashapp-promo.xyz",
    "Zelle transfer failed — confirm bank http://zelle-verify.xyz",
    "Your Social Security number suspended http://ssa-verify.xyz",
    "Medicare: New card activation http://medicare-card.xyz",
    "AT&T: Bill overdue pay now http://att-bill.xyz",
    "Verizon: Free iPad survey http://verizon-survey.xyz",
    "Chase: Fraud alert confirm http://chase-secure.xyz",
    "Wells Fargo: Account review http://wells-verify.xyz",
    "Coinbase: Reset2FA http://coinbase-2fa.xyz",
    "Kraken: Withdrawal hold http://kraken-hold.xyz",
    "NFT mint free — connect wallet http://nft-free-mint.xyz",
    "Job offer $200/hr work from home http://job-scam.xyz/apply",
    "Interview scheduled — pay background check fee http://hr-check.xyz",
    "You matched on our dating site — verify age http://dating-verify.xyz",
    "Hot singles in your area — reply STOP to opt out http://dating-spam.xyz",
]


def _augment_sms(text: str, rng: np.random.Generator, spam: bool) -> str:
    """Light mutations so the model sees obfuscation and noise."""
    t = text
    if spam and rng.random() < 0.12:
        t = t.replace("http://", "hxxp://", 1)
    if spam and rng.random() < 0.08:
        t = t.replace(".com", " [.] com", 1)
    if spam and rng.random() < 0.05:
        t = "\u200b" + t  # zero-width
    if rng.random() < 0.06:
        t = t + " " + str(rng.integers(100, 999))
    return t


def _advanced_synthetic(n_ham: int, n_spam: int, seed: int = 44):
    rng = np.random.default_rng(seed)
    texts, labels = [], []
    for _ in range(n_ham):
        base = str(rng.choice(_HAM_TEMPLATES))
        texts.append(_augment_sms(base, rng, spam=False))
        labels.append(0)
    for _ in range(n_spam):
        base = str(rng.choice(_SPAM_TEMPLATES))
        texts.append(_augment_sms(base, rng, spam=True))
        labels.append(1)
    return texts, np.array(labels)


def _parse_sms_spam_lines(raw: str):
    """Parse UCI-style lines: label<TAB>text (or comma in some exports)."""
    texts, labels = [], []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if "\t" in line:
            parts = line.split("\t", 1)
        elif "," in line:
            parts = line.split(",", 1)
        else:
            continue
        if len(parts) != 2:
            continue
        label_str, text = parts[0].strip().lower(), parts[1].strip()
        if not text:
            continue
        label = 1 if label_str in ("spam", "1") else 0
        texts.append(text)
        labels.append(label)
    return texts, labels


def _urlopen_bytes(url: str, timeout: float = 45.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _DOWNLOAD_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _download_uci_sms():
    """Download SMS Spam Collection (UCI-equivalent). Tries raw TSV mirrors first, then UCI zips."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = None
    last_err = None

    for url in SMS_SPAM_RAW_URLS:
        try:
            data = _urlopen_bytes(url)
            raw = data.decode("utf-8", errors="ignore")
            print(f"Downloaded SMS Spam dataset (TSV): {url[:72]}...")
            break
        except Exception as e:
            last_err = e
            continue

    if raw is None:
        for url in SMS_SPAM_ZIP_URLS:
            try:
                data = _urlopen_bytes(url)
                with zipfile.ZipFile(io.BytesIO(data), "r") as z:
                    names = [
                        n
                        for n in z.namelist()
                        if not n.endswith("/")
                        and ("SMSSpam" in n or "spam" in n.lower() or n.endswith(".txt"))
                    ]
                    if not names:
                        names = [n for n in z.namelist() if not n.endswith("/")]
                    fname = names[0] if names else None
                    if not fname:
                        continue
                    raw = z.read(fname).decode("utf-8", errors="ignore")
                    print(f"Downloaded SMS Spam zip: {url[:72]}...")
                    break
            except Exception as e:
                last_err = e
                continue

    if raw is None:
        print(f"All SMS dataset downloads failed ({last_err}). Using synthetic data.")
        return None

    texts, labels = _parse_sms_spam_lines(raw)
    labels = np.array(labels)
    if len(texts) < 100:
        print("Downloaded file parsed too few rows. Using synthetic data.")
        return None
    print(f"SMS Spam Collection: {len(texts)} messages ({int(labels.sum())} spam)")
    return texts, labels


def _load_uci_sms(path: Path):
    texts, labels = [], []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            label_str, text = parts
            label = 1 if label_str.strip().lower() == "spam" else 0
            texts.append(text)
            labels.append(label)
    return texts, labels


def _cap_stratified(texts, labels, max_total: int | None = MAX_DATASET_SAMPLES):
    """If max_total is None, return all rows. Else shrink to at most max_total (balanced per class)."""
    labels = np.asarray(labels)
    texts = list(texts)
    if max_total is None:
        return texts, labels
    if len(texts) <= max_total:
        return texts, labels
    rng = np.random.default_rng(42)
    per = max_total // 2
    out_texts, out_labels = [], []
    for c in (0, 1):
        idx = np.where(labels == c)[0]
        if len(idx) == 0:
            continue
        take = min(per, len(idx))
        pick = rng.choice(idx, size=take, replace=False)
        out_texts.extend(texts[i] for i in pick)
        out_labels.extend([c] * take)
    return out_texts, np.array(out_labels)


def load_data():
    """Real UCI data when available, plus synthetic augment; else large synthetic-only corpus."""
    syn_ham = syn_spam = (
        SYNTHETIC_PER_CLASS
        if MAX_DATASET_SAMPLES is None
        else max(1, MAX_DATASET_SAMPLES // 2)
    )

    result = _download_uci_sms()
    if result is not None:
        texts, labels = result
        syn_t, syn_y = _advanced_synthetic(800, 800, seed=99)
        texts = list(texts) + syn_t
        labels = np.concatenate([labels, syn_y])
        print(f"Augmented real SMS data with {len(syn_t)} synthetic examples. Total rows: {len(texts)}")
        return _cap_stratified(texts, labels, MAX_DATASET_SAMPLES)

    for name in ("SMSSpamCollection", "sms_spam_collection.txt", "spam.csv"):
        p = DATA_DIR / name
        if p.exists():
            print(f"Loading from {p}...")
            texts, labels = _load_uci_sms(p)
            if len(texts) > 100:
                syn_t, syn_y = _advanced_synthetic(800, 800, seed=101)
                texts = texts + syn_t
                labels = np.concatenate([labels, syn_y])
                return _cap_stratified(texts, labels, MAX_DATASET_SAMPLES)
    csv_path = DATA_DIR / "sms.csv"
    if csv_path.exists():
        import pandas as pd
        df = pd.read_csv(csv_path)
        if "text" in df.columns and "label" in df.columns:
            labels_arr = (df["label"].astype(str).str.lower() == "spam").astype(int).values
            texts = df["text"].astype(str).tolist()
            syn_t, syn_y = _advanced_synthetic(800, 800, seed=102)
            texts = texts + syn_t
            labels_arr = np.concatenate([labels_arr, syn_y])
            return _cap_stratified(texts, labels_arr, MAX_DATASET_SAMPLES)

    print(
        f"Using synthetic SMS only ({syn_ham + syn_spam} samples). "
        "Add data/sms.csv or run online once to pull the UCI collection."
    )
    texts, labels = _advanced_synthetic(syn_ham, syn_spam, seed=44)
    return _cap_stratified(texts, labels, MAX_DATASET_SAMPLES)


def main():
    print("Loading SMS dataset...")
    texts, labels = load_data()
    cap_msg = "full" if MAX_DATASET_SAMPLES is None else str(MAX_DATASET_SAMPLES)
    print(f"Training pool size: {len(texts)} (cap={cap_msg})")

    X_texts, X_test_texts, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    min_df = 1 if len(X_texts) < 4000 else 2
    max_feat = 14000 if len(X_texts) > 5000 else 6000
    print(f"Fitting TF-IDF (max {max_feat} features, min_df={min_df}, char-like ngrams)...")
    vectorizer = TfidfVectorizer(
        max_features=max_feat,
        stop_words="english",
        ngram_range=(1, 3),
        min_df=min_df,
        max_df=0.92,
        sublinear_tf=True,
    )
    X_tfidf = vectorizer.fit_transform(X_texts)
    extra = np.vstack([get_sms_extra_features(t) for t in X_texts])
    X_train = hstack([X_tfidf, extra])

    X_test_tfidf = vectorizer.transform(X_test_texts)
    X_test_extra = np.vstack([get_sms_extra_features(t) for t in X_test_texts])
    X_test = hstack([X_test_tfidf, X_test_extra])

    sw = compute_sample_weight("balanced", y_train)
    print("Training XGBoost (stronger capacity, balanced)...")
    clf = xgb.XGBClassifier(
        n_estimators=420,
        max_depth=14,
        min_child_weight=1,
        learning_rate=0.055,
        subsample=0.85,
        colsample_bytree=0.75,
        colsample_bylevel=0.85,
        gamma=0.05,
        reg_alpha=0.08,
        reg_lambda=1.2,
        random_state=42,
        eval_metric="logloss",
        n_jobs=-1,
    )
    clf.fit(X_train, y_train, sample_weight=sw)

    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, average="weighted")
    try:
        auc = roc_auc_score(y_test, clf.predict_proba(X_test)[:, 1])
        auc_s = f"{auc:.4f}"
    except Exception:
        auc_s = "n/a"
    print(f"\n--- Test set metrics ---")
    print(f"Accuracy: {acc:.2%}")
    print(f"F1 (weighted): {f1:.2%}")
    print(f"ROC-AUC (spam): {auc_s}")
    print(classification_report(y_test, y_pred, target_names=["Ham", "Spam"]))

    joblib.dump(clf, MODELS_DIR / "sms_model.pkl")
    joblib.dump(vectorizer, MODELS_DIR / "sms_vectorizer.pkl")
    print(f"Saved sms_model.pkl and sms_vectorizer.pkl to {MODELS_DIR}")


if __name__ == "__main__":
    main()

# train/train_email.py
# Trains the email phishing classifier: TF-IDF + hand-crafted features + XGBoost.
# Uses data/emails.csv if present (columns: text, label with 1=phishing, 0=legitimate).
# Otherwise uses expanded synthetic data. Reports test accuracy and F1.
# Saves email_model.pkl and email_vectorizer.pkl to ../models/

import sys
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
from utils.feature_extractor import get_email_extra_features

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
# None = use all rows from CSV / full synthetic. Set to e.g. 1000 to cap.
MAX_DATASET_SAMPLES = None
SYNTHETIC_PER_CLASS = 8000  # when emails.csv is missing


def _cap_stratified(texts, labels, max_total: int | None = MAX_DATASET_SAMPLES):
    """If max_total is None, keep all rows. Else cap with balanced sampling per class."""
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


def _synthetic_phishing_samples(n: int = 1200):
    """Generate varied synthetic phishing-like emails for broad attack coverage."""
    templates = [
        "Urgent: Your account has been suspended. Click here to verify: https://fake-bank.com/login",
        "Verify your identity immediately. Login at http://secure-paypal.xyz to avoid account lock.",
        "Congratulations! You have won a prize. Claim now: https://winner-gift.com/claim",
        "Action required: Your password will expire in 24 hours. Confirm at https://account-verify.net",
        "Dear customer, your card is blocked. Click to unblock: https://card-service.com",
        "We detected unusual activity. Login to secure your account: https://suspicious-login.com",
        "Your order is pending. Verify payment at https://payment-gateway.fake",
        "Winner! You have been selected. Reply with your details to claim the cash prize.",
        "Account security alert. Someone tried to login. Verify it was you: https://phish-site.com",
        "Limited time offer. Click here to get your free gift: https://free-gift.xyz",
        "Your Amazon account will be closed. Confirm your details: http://amazon-secure.xyz",
        "Microsoft support: Your license has expired. Renew now: https://microsoft-renew.fake",
        "Your bank has flagged a transaction. Login to approve: http://bank-verify.xyz",
        "Unusual login from new device. Click to verify: https://account-security.net",
        "Your Apple ID was used to sign in. If this wasn't you, click here: http://apple-id.xyz",
        "PayPal: Confirm your identity. Link expires in 24 hours: https://paypal-verify.fake",
        "You have been selected for a government refund. Enter your bank details: http://refund-gov.xyz",
        "Your Netflix subscription failed. Update payment: https://netflix-billing.fake",
        "Suspicious activity on your Google account. Secure now: http://google-security.xyz",
        "IRS notice: You have a tax refund. Claim here: https://irs-refund.fake",
        "From: security@wellsfargo-secure.xyz\nSubject: Wire recall\nPlease verify wire instructions: https://wells-verify.tk",
        "DHL: Shipment on hold — customs payment http://dhl-fee.xyz",
        "HR Payroll: Update direct deposit before Friday http://hr-portal.fake",
        "CEO: I need you to buy gift cards for a client — urgent http://exec-request.xyz",
        "Coinbase: Your wallet needs verification http://coinbase-auth.ml",
        "Attached: invoice_88291.zip (password:1234)",
        "hxxps://login-microsoftonline.com-verify.xyz/oauth",
        "LinkedIn: Someone viewed your profile from suspicious location http://linkedin-secure.xyz",
        "DocuSign: Please sign document http://docusign-fake.xyz",
        "Zoom: Meeting recording shared http://zoom-download.xyz/file.exe",
        "Slack: You have pending invites http://slack-workspace.xyz",
        "Dropbox: File shared with you http://dropbox-file.xyz/malware.zip",
        "Adobe: Invoice overdue http://adobe-billing.xyz",
        "Chase: Zelle payment failed http://chase-zelle.xyz",
        "Binance: KYC required http://binance-kyc.xyz",
        "MetaMask: Sync wallet http://metamask-sync.xyz",
        "Steam: Your account will be deleted http://steam-support.xyz",
        "Instagram: Copyright violation http://ig-verify.xyz",
        "WhatsApp Business: Verify number http://wa-business.xyz",
        "Aadhaar KYC update required http://uidai-kyc.xyz",
        "SBI: Your account is frozen http://sbi-secure.xyz",
        "ICICI: OTP phishing simulation http://icici-alert.xyz",
        "FedEx: Delivery exception fee http://fedex-pay.xyz",
        "AT&T: Bill payment failed http://att-pay.xyz",
    ]
    suffixes = [
        "", " Do not ignore this message.", " Act now to avoid account closure.",
        " This is a security requirement.", " Reply within 24 hours.",
        " Failure to comply may result in legal action.",
    ]
    rng = np.random.default_rng(42)
    out = []
    for _ in range(n):
        t = str(rng.choice(templates))
        t += rng.choice(suffixes)
        if rng.random() < 0.1:
            t = t.replace("http://", "hxxp://", 1)
        out.append((t, 1))
    return out


def _synthetic_legitimate_samples(n: int = 1200):
    """Generate varied legitimate email samples."""
    templates = [
        "Hi, just checking in about our meeting tomorrow at 3pm. Let me know if that works.",
        "Your invoice for March is ready. You can download it from the customer portal.",
        "Thanks for your order. Your package will arrive by Friday. Track at ups.com with your ID.",
        "Reminder: Team standup is at 10am in the main room. See you there.",
        "The document you requested is attached. Please review when you get a chance.",
        "Your subscription has been renewed. Next billing date: April 1. Manage at account settings.",
        "We received your application. Our team will review it and get back within 5 business days.",
        "Your password was successfully changed. If you did not do this, contact support.",
        "Your appointment is confirmed for Tuesday at 2pm. Reply CANCEL to cancel.",
        "Monthly newsletter: Here are the top updates from our product team this month.",
        "Your receipt for order #12345 is attached. Thank you for shopping with us.",
        "Reminder: Your loan payment of Rs 5000 is due on March 20. Pay via net banking or UPI.",
        "Your ticket #789 has been resolved. Let us know if you need anything else.",
        "The team has commented on your document. View feedback in the shared drive.",
        "Your verification code is 847291. Valid for 10 minutes. Do not share.",
        "We have received your feedback. Thank you for helping us improve.",
        "Your delivery is out for delivery today. Track live at courier-website.com.",
        "Your statement for February is ready. Log in to your account to view.",
        "Quarterly roadmap review slides are in the wiki — no action needed.",
        "PTO request approved for June 12-14. Enjoy your time off.",
        "Build #4412 passed CI on main branch.",
        "Please review the design doc by EOD Thursday.",
        "Office closed Monday for holiday — see HR calendar.",
        "Lunch order form for Friday — reply by 11am.",
        "VPN certificate renewed automatically — no steps required.",
        "Your 401k contribution rate change is effective next pay period.",
        "Parking pass renewal link: internal portal only (intranet).",
        "Book club meets next Wednesday — optional reading chapter 3.",
        "Parents evening moved to gym hall — same time.",
        "Dentist reminder: cleaning next month — call to reschedule if needed.",
    ]
    suffixes = ["", " Best regards.", " Thanks.", " Regards."]
    rng = np.random.default_rng(43)
    out = []
    for _ in range(n):
        t = str(rng.choice(templates))
        t += rng.choice(suffixes)
        out.append((t, 0))
    return out


def load_or_generate_data():
    """Load from data/emails.csv (text, label) if present; else use expanded synthetic."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    emails_path = DATA_DIR / "emails.csv"
    if emails_path.exists():
        import pandas as pd
        df = pd.read_csv(emails_path)
        if "text" in df.columns and "label" in df.columns:
            df["text"] = df["text"].astype(str)
            df["label"] = df["label"].astype(int).clip(0, 1)
            if len(df) >= 100:
                print(f"Loaded {len(df)} emails from data/emails.csv")
                rows = [(row["text"], int(row["label"])) for _, row in df.iterrows()]
                t = [x[0] for x in rows]
                y = np.array([x[1] for x in rows])
                t, y = _cap_stratified(t, y, MAX_DATASET_SAMPLES)
                return list(zip(t, y))
    half = (
        SYNTHETIC_PER_CLASS
        if MAX_DATASET_SAMPLES is None
        else max(1, MAX_DATASET_SAMPLES // 2)
    )
    n_syn = half * 2
    print(f"No data/emails.csv found. Using synthetic data ({n_syn} samples).")
    return _synthetic_phishing_samples(half) + _synthetic_legitimate_samples(half)


def main():
    print("Loading email dataset...")
    data = load_or_generate_data()
    texts = [t for t, _ in data]
    labels = np.array([l for _, l in data])
    texts, labels = _cap_stratified(texts, labels, MAX_DATASET_SAMPLES)
    cap_msg = "full" if MAX_DATASET_SAMPLES is None else str(MAX_DATASET_SAMPLES)
    print(f"Training pool size: {len(texts)} (cap={cap_msg})")

    X_train_texts, X_test_texts, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    min_df = 1 if len(X_train_texts) < 4000 else 2
    max_feat = 14000 if len(X_train_texts) > 5000 else 6000
    print(f"Fitting TF-IDF vectorizer (max {max_feat} features, min_df={min_df}, ngram 1-3)...")
    vectorizer = TfidfVectorizer(
        max_features=max_feat,
        stop_words="english",
        ngram_range=(1, 3),
        min_df=min_df,
        max_df=0.92,
        sublinear_tf=True,
    )
    X_tfidf_train = vectorizer.fit_transform(X_train_texts)
    extra_train = np.vstack([get_email_extra_features(t) for t in X_train_texts])
    X_train = hstack([X_tfidf_train, extra_train])

    X_tfidf_test = vectorizer.transform(X_test_texts)
    extra_test = np.vstack([get_email_extra_features(t) for t in X_test_texts])
    X_test = hstack([X_tfidf_test, extra_test])

    sw = compute_sample_weight("balanced", y_train)
    print("Training XGBoost classifier (balanced)...")
    clf = xgb.XGBClassifier(
        n_estimators=400,
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
    print("\n--- Test set metrics ---")
    print(f"Accuracy: {acc:.2%}")
    print(f"F1 (weighted): {f1:.2%}")
    print(f"ROC-AUC (phishing): {auc_s}")
    print(classification_report(y_test, y_pred, target_names=["Legitimate", "Phishing"]))

    joblib.dump(clf, MODELS_DIR / "email_model.pkl")
    joblib.dump(vectorizer, MODELS_DIR / "email_vectorizer.pkl")
    print(f"Saved email_model.pkl and email_vectorizer.pkl to {MODELS_DIR}")


if __name__ == "__main__":
    main()

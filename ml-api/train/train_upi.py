# train/train_upi.py
# Trains the UPI fraud classifier: XGBoost on transaction features.
# Uses synthetic dataset (15k rows) with clear fraud rules. Reports test accuracy and F1.
# Saves upi_model.pkl to ../models/

import sys
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.utils.class_weight import compute_sample_weight
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.feature_extractor import upi_domain_risk_score, upi_feature_vector

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

SENDER_DOMAINS = ["okaxis", "ybl", "okicici", "paytm", "phonepe", "gpay", "unknown"]
RECEIVER_DOMAINS = ["ybl", "okaxis", "paytm", "okicici", "axl", "unknown"]
TXN_TYPES = ["P2P", "P2M", "Collect", "Other"]


def generate_synthetic_upi(n: int = 15000, seed: int = 42):
    """Generate synthetic UPI transactions with consistent fraud labels (more data = better accuracy)."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        amount = float(rng.integers(100, 500000, 1)[0])
        time_of_day = rng.integers(0, 24, 1)[0]
        day_of_week = rng.integers(0, 7, 1)[0]
        txn_type = rng.choice(TXN_TYPES)
        is_new_recipient = rng.random() > 0.6
        device_changed = rng.random() > 0.85
        sender_d = rng.choice(SENDER_DOMAINS)
        receiver_d = rng.choice(RECEIVER_DOMAINS)
        sender_upi = f"user{i % 1000}@{sender_d}"
        receiver_upi = f"merchant{rng.integers(0, 500)}@{receiver_d}"

        fraud_score = 0.0
        if amount > 50000 and (time_of_day <= 4 or time_of_day >= 23):
            fraud_score += 0.4
        if amount > 30000 and is_new_recipient:
            fraud_score += 0.35
        if txn_type == "P2P" and receiver_d == "unknown":
            fraud_score += 0.3
        if day_of_week >= 5 and amount > 40000 and device_changed:
            fraud_score += 0.25
        if receiver_d == "unknown":
            fraud_score += 0.2
        if amount > 100000:
            fraud_score += 0.1

        if fraud_score >= 0.7:
            label = 2
        elif fraud_score >= 0.35:
            label = 1
        else:
            label = 0

        rows.append({
            "amount": amount,
            "sender_upi": sender_upi,
            "receiver_upi": receiver_upi,
            "time_of_day": time_of_day,
            "day_of_week": day_of_week,
            "transaction_type": txn_type,
            "is_new_recipient": int(is_new_recipient),
            "device_changed": int(device_changed),
            "receiver_domain_risk": upi_domain_risk_score(receiver_upi),
            "sender_domain_risk": upi_domain_risk_score(sender_upi),
            "label": label,
        })

    return pd.DataFrame(rows)


def build_features(df: pd.DataFrame):
    """Feature order must match utils.feature_extractor.upi_feature_vector."""
    rows = []
    for _, row in df.iterrows():
        v = upi_feature_vector(
            float(row["amount"]),
            str(row["sender_upi"]),
            str(row["receiver_upi"]),
            int(row["time_of_day"]),
            int(row["day_of_week"]),
            str(row["transaction_type"]),
            int(row["is_new_recipient"]),
            int(row["device_changed"]),
        )
        rows.append(v.ravel())
    return np.vstack(rows), df["label"].values


def main():
    print("Generating synthetic UPI dataset (25,000 rows)...")
    df = generate_synthetic_upi(25000)
    X, y = build_features(df)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    sample_w = compute_sample_weight("balanced", y_train)

    print("Training XGBoost classifier (tuned, class-balanced)...")
    clf = xgb.XGBClassifier(
        n_estimators=400,
        max_depth=8,
        min_child_weight=2,
        learning_rate=0.06,
        subsample=0.85,
        colsample_bytree=0.85,
        gamma=0.1,
        reg_alpha=0.05,
        reg_lambda=1.0,
        random_state=42,
        eval_metric="mlogloss",
        n_jobs=-1,
    )
    clf.fit(X_train, y_train, sample_weight=sample_w, verbose=False)

    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, average="weighted")
    print("\n--- Test set metrics ---")
    print(f"Accuracy: {acc:.2%}")
    print(f"F1 (weighted): {f1:.2%}")
    print(classification_report(y_test, y_pred, target_names=["Legitimate", "Suspicious", "Fraud"]))

    joblib.dump(clf, MODELS_DIR / "upi_model.pkl")
    print(f"Saved upi_model.pkl to {MODELS_DIR}")


if __name__ == "__main__":
    main()

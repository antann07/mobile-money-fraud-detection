"""
train_model.py — Train the Fraud Detection Model
==================================================
Reads data/fraud_training_data.csv, trains a Random Forest classifier,
and saves the model + label encoders to the model/ folder.

Usage:
    python train_model.py

Outputs:
    model/fraud_model.pkl       — trained Random Forest model
    model/label_encoders.pkl    — dict of LabelEncoders for categorical cols
"""

import os
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

from behavioral_features import add_behavioral_features, BEHAVIORAL_FEATURES

# ── Paths ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "fraud_training_data.csv")
MODEL_DIR = os.path.join(BASE_DIR, "model")
MODEL_PATH = os.path.join(MODEL_DIR, "fraud_model.pkl")
ENCODERS_PATH = os.path.join(MODEL_DIR, "label_encoders.pkl")

# ── Feature definitions (must match predict_api.py) ──────────────────
CATEGORICAL_FEATURES = [
    "transactionType",
    "transactionDirection",
    "verificationStatus",
    "trustLevel",
]
# Behavioural features are added at load-time when the enriched dataset
# contains userId / timestamp / deviceId / region / balanceBefore.
# Features that are always numeric and never need encoding:
BEHAVIORAL_NUMERIC = [
    "txn_hour",
    "amount_zscore",
    "txn_time_deviation",
    "balance_drain_ratio",
    "is_new_device",
    "is_new_location",
    "velocity_1day",
    "sim_swap_flag",
]
NUMERIC_FEATURES = [
    "amount",
    "hourOfDay",
    "isWeekend",
    "availableForUse",
    "blocked",
    "hasLinkedSource",
]

FEATURE_ORDER = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET = "label"


def main():
    # ── 1. Load dataset ──────────────────────────────────────────────
    print(f"Loading data from {DATA_PATH} ...")
    df = pd.read_csv(DATA_PATH)
    print(f"  Rows: {len(df)}  Columns: {list(df.columns)}")

    # ── 1b. Behavioural feature engineering (runs when enriched data
    #        contains userId + timestamp + deviceId / region /
    #        balanceBefore columns; otherwise skipped gracefully) ─────
    if "userId" in df.columns and "timestamp" in df.columns:
        print("  Applying behavioural feature engineering ...")
        df = add_behavioral_features(df)
        # Include behavioral numeric features in the model
        extra = [f for f in BEHAVIORAL_NUMERIC if f in df.columns]
        effective_numeric = NUMERIC_FEATURES + [f for f in extra if f not in NUMERIC_FEATURES]
        print(f"  Behavioural features added: {extra}")
    else:
        effective_numeric = NUMERIC_FEATURES
        print("  Skipping behavioural features (userId/timestamp not in dataset).")

    # ── 2. Encode categorical features ───────────────────────────────
    encoders = {}
    for col in CATEGORICAL_FEATURES:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col].astype(str))
        encoders[col] = le
        print(f"  Encoded '{col}': {list(le.classes_)}")

    # ── 3. Prepare X and y ───────────────────────────────────────────
    FEATURE_ORDER = CATEGORICAL_FEATURES + effective_numeric
    X = df[[c for c in FEATURE_ORDER if c in df.columns]]
    y = df[TARGET]

    print(f"\n  Feature matrix shape: {X.shape}")
    print(f"  Label distribution:\n{y.value_counts().to_string()}\n")

    # ── 4. Train / test split ────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # ── 5. Train Random Forest ───────────────────────────────────────
    print("Training Random Forest ...")
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        random_state=42,
        class_weight="balanced",
    )
    model.fit(X_train, y_train)

    # ── 6. Evaluate ──────────────────────────────────────────────────
    y_pred = model.predict(X_test)
    print(f"\nAccuracy: {accuracy_score(y_test, y_pred):.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=["normal", "fraudulent"]))

    # ── 7. Save model and encoders ───────────────────────────────────
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    joblib.dump(encoders, ENCODERS_PATH)

    print(f"✓ Model saved to     {MODEL_PATH}")
    print(f"✓ Encoders saved to  {ENCODERS_PATH}")
    print("\nDone! You can now run:  python predict_api.py")


if __name__ == "__main__":
    main()

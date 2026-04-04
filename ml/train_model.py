"""
train_model.py — MTN MoMo SMS Authenticity Classifier (Baseline)
=================================================================
Reads data/fraud_training_data.csv and trains a Logistic Regression
model that classifies SMS messages as *genuine* or *fraudulent*.

Features used:
  - TF-IDF on the raw_text column  (text signal)
  - 12 structured numeric / binary columns  (metadata signal)

Label mapping (2-class baseline):
  genuine            -> genuine
  suspicious         -> fraudulent
  likely_fraudulent  -> fraudulent

Usage:
    python train_model.py

Outputs:
    model/fraud_model.pkl    — trained LogisticRegression pipeline
    model/tfidf.pkl          — fitted TF-IDF vectorizer
"""

import os
import numpy as np
import pandas as pd
import joblib
from scipy.sparse import hstack

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
)

# ── Paths ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "fraud_training_data.csv")
MODEL_DIR = os.path.join(BASE_DIR, "model")
MODEL_PATH = os.path.join(MODEL_DIR, "fraud_model.pkl")
TFIDF_PATH = os.path.join(MODEL_DIR, "tfidf.pkl")

# ── Structured features (all numeric / binary) ──────────────────────
STRUCTURED_FEATURES = [
    "amount",
    "fee",
    "balance_after",
    "available_balance",
    "has_valid_mtn_format",
    "has_balance_info",
    "has_fee_info",
    "has_transaction_id",
    "has_sender_name",
    "has_character_anomaly",
    "has_spacing_anomaly",
    "has_urgency_language",
]

# ── Label mapping (3-class → 2-class) ───────────────────────────────
LABEL_MAP = {
    "genuine": "genuine",
    "suspicious": "fraudulent",
    "likely_fraudulent": "fraudulent",
}


def main():
    # ── 1. Load dataset ──────────────────────────────────────────────
    print(f"Loading data from {DATA_PATH} ...")
    df = pd.read_csv(DATA_PATH)
    print(f"  Rows: {len(df)}   Columns: {len(df.columns)}")

    # ── 2. Map labels to 2 classes ───────────────────────────────────
    df["label"] = df["label"].map(LABEL_MAP)
    print(f"\n  Label distribution after mapping:")
    print(f"  {df['label'].value_counts().to_dict()}\n")

    # ── 3. Build TF-IDF features from raw_text ──────────────────────
    print("Building TF-IDF features from raw_text ...")
    tfidf = TfidfVectorizer(
        max_features=500,       # keep it small for a 20-row dataset
        stop_words="english",
        ngram_range=(1, 2),     # unigrams + bigrams
    )
    X_text = tfidf.fit_transform(df["raw_text"].fillna(""))
    print(f"  TF-IDF matrix shape: {X_text.shape}")

    # ── 4. Build structured feature matrix ───────────────────────────
    X_struct = df[STRUCTURED_FEATURES].fillna(0).values
    print(f"  Structured feature matrix shape: {X_struct.shape}")

    # ── 5. Combine text + structured features ────────────────────────
    from scipy.sparse import csr_matrix
    X = hstack([X_text, csr_matrix(X_struct)])
    y = df["label"]
    print(f"  Combined feature matrix shape: {X.shape}")

    # ── 6. 80/20 stratified train/test split ─────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y,
    )
    print(f"\n  Train: {X_train.shape[0]} samples")
    print(f"  Test:  {X_test.shape[0]} samples")

    # ── 7. Train Logistic Regression ─────────────────────────────────
    print("\nTraining Logistic Regression (class_weight='balanced') ...")
    model = LogisticRegression(
        class_weight="balanced",
        max_iter=1000,
        random_state=42,
    )
    model.fit(X_train, y_train)

    # ── 8. Evaluate ──────────────────────────────────────────────────
    y_pred = model.predict(X_test)

    acc  = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, pos_label="fraudulent", zero_division=0)
    rec  = recall_score(y_test, y_pred, pos_label="fraudulent", zero_division=0)
    f1   = f1_score(y_test, y_pred, pos_label="fraudulent", zero_division=0)
    cm   = confusion_matrix(y_test, y_pred, labels=["genuine", "fraudulent"])

    print(f"\n{'='*45}")
    print(f"  Accuracy:   {acc:.4f}")
    print(f"  Precision:  {prec:.4f}")
    print(f"  Recall:     {rec:.4f}")
    print(f"  F1-score:   {f1:.4f}")
    print(f"{'='*45}")

    print(f"\nConfusion Matrix (rows=actual, cols=predicted):")
    print(f"                 predicted")
    print(f"                 genuine  fraudulent")
    print(f"  actual genuine   {cm[0][0]:>4}      {cm[0][1]:>4}")
    print(f"  actual fraud     {cm[1][0]:>4}      {cm[1][1]:>4}")

    print(f"\nClassification Report:")
    print(classification_report(y_test, y_pred, labels=["genuine", "fraudulent"]))

    # ── 9. Save model and vectorizer ─────────────────────────────────
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    joblib.dump(tfidf, TFIDF_PATH)

    print(f"Model saved to      {MODEL_PATH}")
    print(f"TF-IDF saved to     {TFIDF_PATH}")
    print("\nDone!  You can now use predict_api.py for inference.")


if __name__ == "__main__":
    main()

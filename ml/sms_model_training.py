"""
sms_model_training.py — Train SMS Fraud Detection Baseline Model
=================================================================
Phase 9 Part 2: First baseline ML pipeline for MTN MoMo SMS classification.

Strategy:
    - 2-class: genuine (0) vs fraudulent (1)
    - suspicious + likely_fraudulent → fraudulent
    - Combines TF-IDF text features with structured boolean/numeric features
    - Logistic Regression with balanced class weights
    - Stratified K-Fold cross-validation (safe for small datasets)

Usage:
    python sms_model_training.py

Outputs:
    model/sms_fraud_model.pkl       — trained Logistic Regression model
    model/sms_tfidf_vectorizer.pkl  — fitted TF-IDF vectorizer

To extend to 3-class later:
    1. Change LABEL_MAP to: {"genuine": 0, "suspicious": 1, "likely_fraudulent": 2}
    2. Change LABEL_NAMES to: ["genuine", "suspicious", "fraudulent"]
    3. Change pos_label=1 to average="macro" in F1 calls
    4. Need 150+ samples (50+ per class) for reliable 3-class results
"""

import os
import sys
import numpy as np
import pandas as pd
import joblib
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
)

# =====================================================================
# CONFIGURATION — edit these if your file paths or columns change
# =====================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Which CSV to load (change this when you create v5, v6, etc.)
DATA_PATH = os.path.join(BASE_DIR, "data", "momo_sms_training_seed_v4.csv")

# Where to save trained model artifacts
MODEL_DIR = os.path.join(BASE_DIR, "model")
MODEL_PATH = os.path.join(MODEL_DIR, "sms_fraud_model.pkl")
VECTORIZER_PATH = os.path.join(MODEL_DIR, "sms_tfidf_vectorizer.pkl")

# ── Column name mapping ──
# v4 CSV uses "raw_sms"; phase7 CSV uses "raw_text".
# The script auto-detects which one exists.
TEXT_COLUMN_CANDIDATES = ["raw_sms", "raw_text"]

# ── Structured features (boolean/numeric) ──
# These are the 13 features we selected in Phase 9 Part 1.
# The script uses whichever columns exist in your CSV.
STRUCTURED_FEATURES_V4 = [
    "has_valid_txn_id",        # 0/1 — valid 10-digit numeric transaction ID
    "has_balance",             # 0/1 — balance shown in SMS
    "has_fee",                 # 0/1 — fee or e-levy mentioned
    "has_counterparty_name",   # 0/1 — sender/receiver name present
    "has_counterparty_number", # 0/1 — phone number present
    "has_valid_datetime",      # 0/1 — parseable date/time in SMS
    "amount_unusually_round",  # 0/1 — amount is suspiciously round
    "contains_url",            # 0/1 — SMS has a link
    "contains_urgency_words",  # 0/1 — pressure language detected
    "contains_pin_request",    # 0/1 — asks for PIN/OTP
    "spelling_error_count",    # int — number of spelling mistakes
    "message_length",          # int — character count
    "parser_confidence",       # float 0.0–1.0 — template match score
]

STRUCTURED_FEATURES_PHASE7 = [
    "has_valid_mtn_format",    # 0/1
    "has_balance_info",        # 0/1
    "has_fee_info",            # 0/1
    "has_transaction_id",      # 0/1
    "has_sender_name",         # 0/1
    "has_character_anomaly",   # 0/1
    "has_spacing_anomaly",     # 0/1
    "has_urgency_language",    # 0/1
]

# Label mapping: 3-class → 2-class
LABEL_MAP = {
    "genuine": 0,
    "suspicious": 1,
    "likely_fraudulent": 1,
}

LABEL_NAMES = ["genuine", "fraudulent"]

# Model hyperparameters
RANDOM_STATE = 42
TEST_SIZE = 0.20
TFIDF_MAX_FEATURES = 100
CV_FOLDS = 5

# Minimum samples needed for hold-out split (below this, use CV only)
MIN_SAMPLES_FOR_HOLDOUT = 40


# =====================================================================
# STEP 1: Load and prepare data
# =====================================================================

def load_and_prepare(csv_path):
    """
    Load the CSV, detect column format, map labels to binary.

    Returns:
        df: cleaned DataFrame
        text_col: name of the raw SMS text column
        structured_cols: list of structured feature column names found
    """
    print(f"Loading data from:\n  {csv_path}\n")

    if not os.path.exists(csv_path):
        print(f"ERROR: File not found: {csv_path}")
        print("Make sure your CSV is in the ml/data/ folder.")
        sys.exit(1)

    df = pd.read_csv(csv_path)
    print(f"  Rows: {len(df)}  |  Columns: {len(df.columns)}")

    # ── Detect text column ──
    text_col = None
    for candidate in TEXT_COLUMN_CANDIDATES:
        if candidate in df.columns:
            text_col = candidate
            break
    if text_col is None:
        print(f"ERROR: No text column found. Expected one of: {TEXT_COLUMN_CANDIDATES}")
        sys.exit(1)
    print(f"  Text column: '{text_col}'")

    # ── Detect structured features ──
    # Try v4 columns first, then fall back to phase7 columns
    structured_cols = [c for c in STRUCTURED_FEATURES_V4 if c in df.columns]
    if len(structured_cols) < 3:
        structured_cols = [c for c in STRUCTURED_FEATURES_PHASE7 if c in df.columns]
    print(f"  Structured features found: {len(structured_cols)}")
    for col in structured_cols:
        print(f"    - {col}")

    # ── Map labels to binary ──
    if "label" not in df.columns:
        print("ERROR: No 'label' column found in CSV.")
        sys.exit(1)

    original_counts = df["label"].value_counts()
    print(f"\n  Original label distribution:")
    for lbl, count in original_counts.items():
        print(f"    {lbl}: {count}")

    df["label_binary"] = df["label"].map(LABEL_MAP)

    unmapped = df["label_binary"].isna().sum()
    if unmapped > 0:
        unknown_labels = df.loc[df["label_binary"].isna(), "label"].unique()
        print(f"\n  WARNING: {unmapped} rows have unknown labels: {unknown_labels}")
        print("  These rows will be dropped.")
        df = df.dropna(subset=["label_binary"])

    df["label_binary"] = df["label_binary"].astype(int)

    binary_counts = df["label_binary"].value_counts()
    print(f"\n  Binary label distribution:")
    print(f"    genuine (0):    {binary_counts.get(0, 0)}")
    print(f"    fraudulent (1): {binary_counts.get(1, 0)}")

    # ── Fill missing values in structured columns ──
    for col in structured_cols:
        # Convert to numeric (handles strings like "yes"/"no" or empty cells)
        df[col] = pd.to_numeric(df[col], errors="coerce")
        missing = df[col].isna().sum()
        if missing > 0:
            df[col] = df[col].fillna(0)
            print(f"  Filled {missing} missing values in '{col}' with 0")

    # ── Fill missing text (empty SMS should be empty string, not NaN) ──
    df[text_col] = df[text_col].fillna("")

    # ── Sanity check: need at least 2 samples per class ──
    class_counts = df["label_binary"].value_counts()
    for cls in [0, 1]:
        if class_counts.get(cls, 0) < 2:
            print(f"  ERROR: Class {cls} has fewer than 2 samples. Cannot train.")
            print("  Add more labeled samples to your CSV.")
            sys.exit(1)

    print()
    return df, text_col, structured_cols


# =====================================================================
# STEP 2: Build feature matrices
# =====================================================================

def build_features(df, text_col, structured_cols, vectorizer=None):
    """
    Build the combined feature matrix: TF-IDF text + structured columns.

    Args:
        df: prepared DataFrame
        text_col: name of text column
        structured_cols: list of structured feature column names
        vectorizer: pre-fitted TfidfVectorizer (None to fit new)

    Returns:
        X_combined: sparse matrix of all features
        vectorizer: fitted TfidfVectorizer
        feature_names: list of all feature names (for interpretation)
    """
    # ── Text features (TF-IDF) ──
    if vectorizer is None:
        # Adjust min_df based on dataset size:
        # - Tiny datasets (<30 samples): min_df=1 (keep all words)
        # - Medium datasets (30–100):    min_df=2 (filter noise)
        # - Large datasets (100+):       min_df=3
        n_samples = len(df)
        if n_samples < 30:
            effective_min_df = 1
        elif n_samples < 100:
            effective_min_df = 2
        else:
            effective_min_df = 3

        vectorizer = TfidfVectorizer(
            max_features=TFIDF_MAX_FEATURES,
            stop_words="english",
            ngram_range=(1, 2),      # unigrams + bigrams like "pin request"
            min_df=effective_min_df,  # adaptive to dataset size
            lowercase=True,
        )
        X_text = vectorizer.fit_transform(df[text_col])

        # Guard: if TF-IDF produces zero features (all words filtered out),
        # fall back to structured-only mode
        if X_text.shape[1] == 0:
            print("  WARNING: TF-IDF produced 0 features (all words filtered).")
            print("           Falling back to min_df=1 ...")
            vectorizer = TfidfVectorizer(
                max_features=TFIDF_MAX_FEATURES,
                stop_words="english",
                ngram_range=(1, 2),
                min_df=1,
                lowercase=True,
            )
            X_text = vectorizer.fit_transform(df[text_col])

        print(f"  TF-IDF features: {X_text.shape[1]} (min_df={effective_min_df}, "
              f"from {n_samples} samples)")
    else:
        X_text = vectorizer.transform(df[text_col])

    # ── Structured features ──
    structured_values = df[structured_cols].values.astype(float)
    # Replace any remaining NaN/inf with 0 (safety net)
    structured_values = np.nan_to_num(structured_values, nan=0.0, posinf=0.0, neginf=0.0)
    X_structured = sp.csr_matrix(structured_values)
    print(f"  Structured features: {X_structured.shape[1]}")

    # ── Combine: [structured | text] ──
    X_combined = sp.hstack([X_structured, X_text])
    print(f"  Combined feature matrix: {X_combined.shape}")

    # ── Feature names for interpretation ──
    tfidf_names = vectorizer.get_feature_names_out().tolist()
    feature_names = structured_cols + tfidf_names

    return X_combined, vectorizer, feature_names


# =====================================================================
# STEP 3: Train and evaluate
# =====================================================================

def train_and_evaluate(X, y, feature_names):
    """
    Train Logistic Regression with 5-fold stratified cross-validation,
    then train final model on all data.

    Returns:
        model: trained LogisticRegression on full dataset
    """
    n_samples = len(y)
    minority_count = min(np.bincount(y))  # smallest class size

    # Number of CV folds can't exceed the minority class count
    # (each fold needs at least 1 sample from each class)
    n_folds = min(CV_FOLDS, minority_count)

    if n_folds < 2:
        print("  WARNING: Not enough samples for cross-validation.")
        print("  Training on all data without CV (results may be unreliable).")
        print("  Add more labeled samples to get reliable evaluation.")
        n_folds = 0

    # ── Cross-validation ──
    if n_folds >= 2:
        print(f"\n{'='*60}")
        print(f"  CROSS-VALIDATION ({n_folds}-fold stratified)")
        print(f"{'='*60}")

        skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=RANDOM_STATE)

        fold_metrics = []
        all_y_true = []
        all_y_pred = []

        for fold_num, (train_idx, test_idx) in enumerate(skf.split(X, y), 1):
            X_train_fold = X[train_idx]
            X_test_fold = X[test_idx]
            y_train_fold = y[train_idx]
            y_test_fold = y[test_idx]

            model_fold = LogisticRegression(
                class_weight="balanced",
                max_iter=1000,
                random_state=RANDOM_STATE,
            )
            model_fold.fit(X_train_fold, y_train_fold)
            y_pred_fold = model_fold.predict(X_test_fold)

            fold_f1 = f1_score(y_test_fold, y_pred_fold, pos_label=1, zero_division=0)
            fold_metrics.append(fold_f1)
            all_y_true.extend(y_test_fold)
            all_y_pred.extend(y_pred_fold)

            print(f"  Fold {fold_num}: F1 = {fold_f1:.3f}  "
                  f"(test size: {len(test_idx)}, "
                  f"genuine: {sum(y_test_fold == 0)}, "
                  f"fraud: {sum(y_test_fold == 1)})")

        # ── Aggregated CV results ──
        mean_f1 = np.mean(fold_metrics)
        std_f1 = np.std(fold_metrics)
        print(f"\n  Mean F1: {mean_f1:.3f} +/- {std_f1:.3f}")

        # ── Aggregated confusion matrix (all folds combined) ──
        all_y_true = np.array(all_y_true)
        all_y_pred = np.array(all_y_pred)

        print(f"\n  Aggregated Confusion Matrix (all folds):")
        cm = confusion_matrix(all_y_true, all_y_pred)
        print(f"                  Predicted")
        print(f"                  genuine  fraud")
        print(f"  Actual genuine  {cm[0][0]:>7}  {cm[0][1]:>5}")
        print(f"  Actual fraud    {cm[1][0]:>7}  {cm[1][1]:>5}")

        print(f"\n  Aggregated Classification Report:")
        print(classification_report(all_y_true, all_y_pred,
                                    target_names=LABEL_NAMES, digits=3,
                                    zero_division=0))

    # ── Hold-out evaluation ──
    # Only run hold-out if we have enough samples for a meaningful test set.
    # With <40 samples, the test set is too small (4–8 samples) to be reliable,
    # so we skip it and rely on cross-validation results above.
    if n_samples >= MIN_SAMPLES_FOR_HOLDOUT:
        print(f"\n{'='*60}")
        print(f"  HOLD-OUT EVALUATION (80/20 stratified split)")
        print(f"{'='*60}")

        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=TEST_SIZE,
            stratify=y,
            random_state=RANDOM_STATE,
        )
        print(f"  Train: {X_train.shape[0]} samples | Test: {X_test.shape[0]} samples")

        model_holdout = LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            random_state=RANDOM_STATE,
        )
        model_holdout.fit(X_train, y_train)
        y_pred = model_holdout.predict(X_test)

        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, pos_label=1, zero_division=0)
        rec = recall_score(y_test, y_pred, pos_label=1, zero_division=0)
        f1 = f1_score(y_test, y_pred, pos_label=1, zero_division=0)

        print(f"\n  Accuracy:  {acc:.3f}")
        print(f"  Precision: {prec:.3f}  (of flagged messages, how many were actually fraud)")
        print(f"  Recall:    {rec:.3f}  (of real fraud, how many did we catch)")
        print(f"  F1-score:  {f1:.3f}  (balance of precision and recall)")

        cm = confusion_matrix(y_test, y_pred)
        print(f"\n  Confusion Matrix:")
        print(f"                  Predicted")
        print(f"                  genuine  fraud")
        print(f"  Actual genuine  {cm[0][0]:>7}  {cm[0][1]:>5}")
        print(f"  Actual fraud    {cm[1][0]:>7}  {cm[1][1]:>5}")

        print(f"\n  Classification Report:")
        print(classification_report(y_test, y_pred,
                                    target_names=LABEL_NAMES, digits=3,
                                    zero_division=0))
    else:
        print(f"\n  Skipping hold-out evaluation ({n_samples} samples < {MIN_SAMPLES_FOR_HOLDOUT}).")
        print(f"  Cross-validation results above are more reliable for small datasets.")

    # ── Train final model on ALL data ──
    print(f"\n{'='*60}")
    print(f"  FINAL MODEL (trained on all {n_samples} samples)")
    print(f"{'='*60}")

    model = LogisticRegression(
        class_weight="balanced",
        max_iter=1000,
        random_state=RANDOM_STATE,
    )
    model.fit(X, y)

    # ── Feature importances (top 15) ──
    print(f"\n  Top 15 most important features:")
    if hasattr(model, "coef_"):
        coefs = model.coef_[0]
        top_indices = np.argsort(np.abs(coefs))[::-1][:15]
        for rank, idx in enumerate(top_indices, 1):
            name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
            direction = "fraud+" if coefs[idx] > 0 else "genuine+"
            print(f"    {rank:>2}. {name:<30} {coefs[idx]:>+7.3f}  ({direction})")

    return model


# =====================================================================
# STEP 4: Save model artifacts
# =====================================================================

def save_model(model, vectorizer):
    """Save the trained model and TF-IDF vectorizer to disk."""
    os.makedirs(MODEL_DIR, exist_ok=True)

    joblib.dump(model, MODEL_PATH)
    joblib.dump(vectorizer, VECTORIZER_PATH)

    print(f"\n  Model saved to:      {MODEL_PATH}")
    print(f"  Vectorizer saved to: {VECTORIZER_PATH}")


# =====================================================================
# MAIN — run the full pipeline
# =====================================================================

def main():
    print()
    print("=" * 60)
    print("  MTN MoMo SMS Fraud Detection — Baseline Training")
    print("  Model: Logistic Regression (2-class)")
    print("=" * 60)
    print()

    # 1. Load and prepare
    df, text_col, structured_cols = load_and_prepare(DATA_PATH)

    # 2. Build features
    print("Building feature matrix ...")
    X, vectorizer, feature_names = build_features(df, text_col, structured_cols)
    y = df["label_binary"].values

    # 3. Train and evaluate
    model = train_and_evaluate(X, y, feature_names)

    # 4. Save
    save_model(model, vectorizer)

    print()
    print("=" * 60)
    print("  DONE — Baseline training complete.")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()

"""
explain_anomalies.py
=====================
Explains WHY the Isolation Forest flagged a withdrawal as suspicious
using the engineered behavioral features.

Two explanation approaches are tried in order:
1. SHAP (TreeExplainer) — if the shap package is installed.
2. Deviation-based fallback — compares each flagged transaction's feature
   values against the dataset average and highlights the largest gaps.
   No extra packages needed.

How to run
----------
    python explain_anomalies.py

Optional (for richer SHAP plots):
    pip install shap
"""

import os
import sys
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

# ---------------------------------------------------------------------------
# Configuration — must match isolation_forest.py exactly
# ---------------------------------------------------------------------------

FEATURES = [
    "amount",
    "balance_before",
    "balance_after",
    "sim_swap_flag",
    "txn_hour",
    "amount_zscore",
    "txn_time_deviation",
    "balance_drain_ratio",
    "is_new_device",
    "is_new_location",
    "velocity_1day",
]

CONTAMINATION  = "auto"
N_ESTIMATORS   = 100
RANDOM_STATE   = 42

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
ENGINEERED_CSV = os.path.join(BASE_DIR, "data", "engineered_features.csv")

# How many flagged transactions to explain
MAX_EXPLANATIONS = 3

# Deviation threshold: features whose z-score vs. the dataset mean exceeds
# this value are highlighted as suspicious signals.
DEVIATION_THRESHOLD = 1.0


# ---------------------------------------------------------------------------
# Step 1 – Load data
# ---------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    """Load engineered_features.csv, falling back to auto-generation."""
    if os.path.exists(ENGINEERED_CSV):
        df = pd.read_csv(ENGINEERED_CSV)
        print(f"  Loaded engineered features from '{ENGINEERED_CSV}'  "
              f"({len(df):,} rows).")
        return df

    # Try to generate the CSV by running feature_engineering.py
    fe_script = os.path.join(BASE_DIR, "feature_engineering.py")
    if os.path.exists(fe_script):
        print("  engineered_features.csv not found — running feature_engineering.py ...")
        import subprocess
        result = subprocess.run([sys.executable, fe_script],
                                capture_output=True, text=True)
        if result.returncode == 0 and os.path.exists(ENGINEERED_CSV):
            df = pd.read_csv(ENGINEERED_CSV)
            print(f"  Generated and loaded engineered features ({len(df):,} rows).")
            return df
        else:
            last_err = result.stderr.strip().splitlines()[-1] if result.stderr else "unknown"
            print(f"  Could not generate features. Reason: {last_err}")

    print("  ERROR: Run 'python feature_engineering.py' first, then retry.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Step 2 – Prepare feature matrix
# ---------------------------------------------------------------------------

def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return a clean numeric matrix with exactly the FEATURES columns."""
    missing = [f for f in FEATURES if f not in df.columns]
    for col in missing:
        print(f"  Warning: '{col}' not in dataset — filling with 0.")
        df[col] = 0.0

    X = df[FEATURES].copy()
    X = X.apply(pd.to_numeric, errors="coerce").fillna(0)
    return X


# ---------------------------------------------------------------------------
# Step 3 – Train Isolation Forest
# ---------------------------------------------------------------------------

def train_model(X: pd.DataFrame) -> IsolationForest:
    """Fit and return a trained Isolation Forest."""
    model = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=CONTAMINATION,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(X)
    print(f"  Isolation Forest trained on {X.shape[0]:,} samples "
          f"with {X.shape[1]} features.")
    return model


# ---------------------------------------------------------------------------
# Step 4 – SHAP explanation (primary approach)
# ---------------------------------------------------------------------------

def explain_with_shap(model: IsolationForest, X: pd.DataFrame,
                      suspicious_idx: list) -> bool:
    """
    Use SHAP TreeExplainer to explain the flagged transactions.

    Returns True if explanation succeeded, False if shap is unavailable
    or the explainer does not support this model version.
    """
    try:
        import shap
    except ImportError:
        return False

    print("\n  Using SHAP TreeExplainer for explanations.")
    print("  (Install 'shap' with:  pip install shap)\n")

    try:
        explainer   = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)
    except Exception as exc:
        print(f"  SHAP TreeExplainer failed: {exc}")
        return False

    # shap_values shape: (n_samples, n_features)
    # For Isolation Forest the score is negative-anomaly, so a large
    # negative SHAP value means that feature PUSHED the score down (more
    # anomalous).  We rank by |shap| to find the most influential features.
    for rank, idx in enumerate(suspicious_idx[:MAX_EXPLANATIONS], start=1):
        row_shap = shap_values[idx]          # shape: (n_features,)
        row_vals = X.iloc[idx]

        # Sort features by absolute SHAP contribution (descending)
        contributions = sorted(
            zip(FEATURES, row_shap, row_vals),
            key=lambda t: abs(t[1]),
            reverse=True,
        )

        print(f"  ─── Suspicious transaction #{rank} (row {idx}) ───")
        print(f"  {'Feature':<25} {'Value':>12}  {'SHAP':>10}  Direction")
        print(f"  {'─' * 62}")
        for feat, shap_val, val in contributions[:6]:
            direction = "↑ more suspicious" if shap_val < 0 else "↓ less suspicious"
            print(f"  {feat:<25} {val:>12.4f}  {shap_val:>10.4f}  {direction}")

        # Build a plain-English sentence
        top_names = [f for f, s, _ in contributions[:3] if abs(s) > 0]
        sentence  = (
            "This withdrawal was flagged because "
            + ", ".join(top_names[:-1])
            + (" and " if len(top_names) > 1 else "")
            + top_names[-1]
            + " had the strongest anomalous signal."
        )
        print(f"\n  >> {sentence}\n")

    return True


# ---------------------------------------------------------------------------
# Step 5 – Deviation-based fallback explanation
# ---------------------------------------------------------------------------

def explain_with_deviations(X: pd.DataFrame, suspicious_idx: list) -> None:
    """
    Compare each flagged transaction's feature values against the
    dataset mean and standard deviation.  Features whose z-score
    exceeds DEVIATION_THRESHOLD are highlighted as the likely cause.

    This requires no extra packages and is always available.
    """
    print("\n  Using deviation-based explanation (no SHAP required).\n")

    col_means = X.mean()
    col_stds  = X.std().replace(0, 1)   # avoid division by zero

    for rank, idx in enumerate(suspicious_idx[:MAX_EXPLANATIONS], start=1):
        row = X.iloc[idx]
        z_scores = (row - col_means) / col_stds

        # Sort by absolute z-score — largest deviation first
        deviations = sorted(
            zip(FEATURES, row, col_means, z_scores),
            key=lambda t: abs(t[3]),
            reverse=True,
        )

        print(f"  ─── Suspicious transaction #{rank} (row {idx}) ───")
        print(f"  {'Feature':<25} {'Value':>12}  {'Dataset avg':>13}  "
              f"{'Z-score':>9}  Signal")
        print(f"  {'─' * 78}")

        flagged_features = []
        for feat, val, avg, z in deviations:
            signal = ""
            if abs(z) >= DEVIATION_THRESHOLD:
                signal = "⚑ HIGH" if z > 0 else "⚑ LOW"
                flagged_features.append((feat, val, z))
            print(f"  {feat:<25} {val:>12.4f}  {avg:>13.4f}  {z:>9.2f}  {signal}")

        # Plain-English summary
        print()
        if flagged_features:
            reasons = []
            for feat, val, z in flagged_features[:4]:
                direction = "unusually high" if z > 0 else "unusually low"
                reasons.append(f"{feat} was {direction} ({val:.2f})")
            sentence = (
                "This withdrawal was flagged because "
                + "; ".join(reasons) + "."
            )
        else:
            sentence = (
                "No single feature stands out strongly — "
                "the model flagged this based on the combined pattern of all features."
            )

        print(f"  >> {sentence}\n")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    print("\n[ Step 1 ] Loading engineered data ...")
    df = load_data()

    print("\n[ Step 2 ] Preparing feature matrix ...")
    X = prepare_features(df)
    print(f"  Shape: {X.shape[0]:,} rows × {X.shape[1]} columns")

    print("\n[ Step 3 ] Training Isolation Forest ...")
    model = train_model(X)

    # Identify flagged (anomalous) transactions
    raw_pred      = model.predict(X)                  # -1 = anomaly, +1 = normal
    anomaly_score = model.decision_function(X)        # more negative = more anomalous
    df["anomaly_label"] = np.where(raw_pred == -1, 1, 0)
    df["anomaly_score"] = anomaly_score

    suspicious_idx = (
        df[df["anomaly_label"] == 1]
        .sort_values("anomaly_score")           # most anomalous first
        .index.tolist()
    )

    total    = len(df)
    flagged  = len(suspicious_idx)
    print(f"\n  Flagged {flagged} of {total} transactions as suspicious.")

    if flagged == 0:
        print("  No suspicious transactions found — nothing to explain.")
        return

    print(f"\n[ Step 4 ] Explaining up to {MAX_EXPLANATIONS} flagged transaction(s) ...")
    print("=" * 80)

    # Try SHAP first; fall back to deviation analysis if unavailable
    shap_ok = explain_with_shap(model, X, suspicious_idx)
    if not shap_ok:
        print("  (SHAP not available — using deviation-based explanation instead.)")
        print("  To enable SHAP:  pip install shap\n")
        explain_with_deviations(X, suspicious_idx)

    print("=" * 80)
    print("\nDone.  Run 'pip install shap' for richer SHAP-based explanations.")


if __name__ == "__main__":
    main()

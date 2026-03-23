"""
isolation_forest.py
====================
Trains an Isolation Forest model to detect UNAUTHORISED WITHDRAWALS
in Mobile Money by assigning an anomaly score to each transaction.

How it works
------------
Isolation Forest is an *unsupervised* anomaly detection algorithm.
It randomly isolates observations by building trees.  Anomalies are
points that are easy to isolate — they end up near the root of the
trees and therefore get a HIGH anomaly score.

How to run
----------
    python isolation_forest.py

Requirements
------------
    pip install pandas scikit-learn
"""

import os
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# Optional: import from feature_engineering if you want to generate
# features on-the-fly from a live database.
# from feature_engineering import load_transactions, engineer_features


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The 11 behavioral features the model will learn from.
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

# Isolation Forest hyper-parameters
# contamination – expected fraction of anomalies in the dataset.
#   "auto" lets scikit-learn decide based on the original paper's threshold.
#   You can also set a float, e.g. 0.05 means ~5 % of rows are anomalies.
CONTAMINATION = "auto"
N_ESTIMATORS  = 100   # number of trees in the forest
RANDOM_STATE  = 42    # reproducibility seed

# Paths
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR  = os.path.join(BASE_DIR, "model")


# ---------------------------------------------------------------------------
# Step 1 – Load the engineered dataset
# ---------------------------------------------------------------------------

# Path to the engineered features CSV produced by feature_engineering.py
ENGINEERED_CSV = os.path.join(BASE_DIR, "data", "engineered_features.csv")


def load_engineered_data() -> pd.DataFrame:
    """
    Load the dataset that was produced by feature_engineering.py.

    Priority order
    --------------
    1. Load  ml/data/engineered_features.csv  if it already exists.
    2. If not found, try to generate it by running feature_engineering.py
       automatically (requires sqlalchemy + a valid database).
    3. If that also fails, fall back to a small synthetic dataset so the
       rest of the script can still be demonstrated.

    Returns
    -------
    pd.DataFrame
        DataFrame with (at least) the columns listed in FEATURES.
    """
    # ── 1. Happy path: CSV already exists ───────────────────────────
    if os.path.exists(ENGINEERED_CSV):
        df = pd.read_csv(ENGINEERED_CSV)
        print(f"  Loaded engineered features from '{ENGINEERED_CSV}'  "
              f"({len(df):,} rows).")
        return df

    # ── 2. Try to auto-generate by running feature_engineering.py ───
    fe_script = os.path.join(BASE_DIR, "feature_engineering.py")
    print("  WARNING: engineered_features.csv not found.")

    if os.path.exists(fe_script):
        print("  Attempting to generate it by running feature_engineering.py ...")
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, fe_script],
            capture_output=True, text=True
        )
        if result.returncode == 0 and os.path.exists(ENGINEERED_CSV):
            df = pd.read_csv(ENGINEERED_CSV)
            print(f"  Generated and loaded engineered features  "
                  f"({len(df):,} rows).")
            return df
        else:
            print("  Could not auto-generate features "
                  "(database may not be available).")
            if result.stderr:
                # Show only the last line of the error so output stays brief
                print(f"  Reason: {result.stderr.strip().splitlines()[-1]}")

    print("  Run  python feature_engineering.py  first to use real data.")
    print("  Falling back to synthetic sample data for demonstration.\n")

    np.random.seed(RANDOM_STATE)
    n_normal   = 950   # typical transactions
    n_anomaly  = 50    # suspicious withdrawals

    def normal_rows(n):
        return {
            "amount":             np.random.uniform(10,    500,  n),
            "balance_before":     np.random.uniform(500,  5000,  n),
            "balance_after":      np.random.uniform(0,    4500,  n),
            "sim_swap_flag":      np.zeros(n, dtype=int),
            "txn_hour":           np.random.randint(8, 20,       n),
            "amount_zscore":      np.random.normal(0,   0.5,     n),
            "txn_time_deviation": np.random.uniform(0,   2,      n),
            "balance_drain_ratio":np.random.uniform(0,   0.2,    n),
            "is_new_device":      np.random.choice([0, 1], n, p=[0.95, 0.05]),
            "is_new_location":    np.random.choice([0, 1], n, p=[0.97, 0.03]),
            "velocity_1day":      np.random.randint(1, 4,        n),
            "label":              np.zeros(n, dtype=int),
        }

    def anomaly_rows(n):
        return {
            "amount":             np.random.uniform(2000,  9000, n),
            "balance_before":     np.random.uniform(2000,  9000, n),
            "balance_after":      np.random.uniform(0,      200, n),
            "sim_swap_flag":      np.ones(n, dtype=int),
            "txn_hour":           np.random.randint(0, 5,        n),
            "amount_zscore":      np.random.uniform(3,    8,     n),
            "txn_time_deviation": np.random.uniform(8,   12,     n),
            "balance_drain_ratio":np.random.uniform(0.8,  1.0,   n),
            "is_new_device":      np.ones(n, dtype=int),
            "is_new_location":    np.ones(n, dtype=int),
            "velocity_1day":      np.random.randint(5, 15,       n),
            "label":              np.ones(n, dtype=int),
        }

    df = pd.concat(
        [pd.DataFrame(normal_rows(n_normal)),
         pd.DataFrame(anomaly_rows(n_anomaly))],
        ignore_index=True,
    )
    df = df.sample(frac=1, random_state=RANDOM_STATE).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Step 2 – Select and prepare feature columns
# ---------------------------------------------------------------------------

def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Select only the feature columns that the model needs and fill any
    missing values with 0 so the model always gets clean numeric input.

    Parameters
    ----------
    df : pd.DataFrame
        Raw engineered DataFrame (may contain extra columns).

    Returns
    -------
    pd.DataFrame
        DataFrame with exactly the columns in FEATURES, all numeric.
    """
    # Keep only features that actually exist in the dataframe
    available = [f for f in FEATURES if f in df.columns]
    missing   = [f for f in FEATURES if f not in df.columns]

    if missing:
        print(f"  Warning: the following features were not found and will be "
              f"set to 0: {missing}")
        for col in missing:
            df[col] = 0.0

    X = df[FEATURES].copy()
    X = X.apply(pd.to_numeric, errors="coerce").fillna(0)
    return X


# ---------------------------------------------------------------------------
# Step 3 – Train the Isolation Forest
# ---------------------------------------------------------------------------

def train_isolation_forest(X: pd.DataFrame) -> IsolationForest:
    """
    Fit an Isolation Forest on the feature matrix X.

    Parameters
    ----------
    X : pd.DataFrame
        Numeric feature matrix (n_samples × n_features).

    Returns
    -------
    IsolationForest
        Trained model ready for prediction.
    """
    model = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=CONTAMINATION,
        random_state=RANDOM_STATE,
        n_jobs=-1,          # use all CPU cores
    )
    model.fit(X)
    print(f"  Isolation Forest trained on {X.shape[0]:,} samples "
          f"with {X.shape[1]} features.")
    return model


# ---------------------------------------------------------------------------
# Step 4 & 5 – Generate predictions and add result columns
# ---------------------------------------------------------------------------

def add_anomaly_columns(df: pd.DataFrame, model: IsolationForest,
                        X: pd.DataFrame) -> pd.DataFrame:
    """
    Append anomaly_score and anomaly_label columns to *df*.

    anomaly_score
        A continuous score in (-∞, 0].
        More negative  →  more anomalous.
        Closer to 0    →  more normal.
        (This is sklearn's decision_function output.)

    anomaly_label
        1  = SUSPICIOUS  (isolation forest flagged as an outlier)
        0  = NORMAL

    Parameters
    ----------
    df    : pd.DataFrame  — original dataframe (before feature selection)
    model : IsolationForest — trained model
    X     : pd.DataFrame  — feature matrix used for training

    Returns
    -------
    pd.DataFrame
        *df* with two new columns appended.
    """
    # decision_function: negative scores = anomalies
    df = df.copy()
    df["anomaly_score"] = model.decision_function(X)

    # predict returns -1 for anomalies, +1 for normal → remap to 1/0
    raw_pred = model.predict(X)
    df["anomaly_label"] = np.where(raw_pred == -1, 1, 0)

    return df


# ---------------------------------------------------------------------------
# Step 6 – Print results and evaluation summary
# ---------------------------------------------------------------------------

def print_summary(df: pd.DataFrame) -> None:
    """
    Print a sample of flagged transactions and an evaluation summary.

    If the dataframe has a 'label' column (ground-truth fraud labels)
    the function also prints a simple comparison table so you can see
    how well the unsupervised model agrees with known labels.
    """
    total      = len(df)
    flagged    = df["anomaly_label"].sum()
    flag_rate  = flagged / total * 100

    print("\n" + "=" * 60)
    print("  ISOLATION FOREST — RESULTS SUMMARY")
    print("=" * 60)
    print(f"  Total transactions   : {total:,}")
    print(f"  Flagged as anomalies : {flagged:,}  ({flag_rate:.1f} %)")
    print(f"  Considered normal    : {total - flagged:,}  "
          f"({100 - flag_rate:.1f} %)")

    # ── Score distribution ───────────────────────────────────────────
    print("\n  Anomaly score stats (more negative = more suspicious):")
    score_stats = df["anomaly_score"].describe()
    for stat, val in score_stats.items():
        print(f"    {stat:>5}: {val:+.4f}")

    # ── Sample flagged transactions ──────────────────────────────────
    print("\n  Sample SUSPICIOUS transactions (anomaly_label = 1):")
    suspicious = df[df["anomaly_label"] == 1].sort_values("anomaly_score")

    display_cols = [c for c in
                    ["amount", "balance_before", "sim_swap_flag",
                     "txn_hour", "is_new_device", "is_new_location",
                     "velocity_1day", "anomaly_score", "anomaly_label"]
                    if c in df.columns]

    print(suspicious[display_cols].head(10).to_string(index=False))

    # ── Optional: comparison with ground-truth labels ────────────────
    if "label" in df.columns:
        print("\n  Comparison with ground-truth labels:")
        print("  (label=1 means the transaction is a known fraud case)\n")

        crosstab = pd.crosstab(
            df["label"],
            df["anomaly_label"],
            rownames=["Actual (label)"],
            colnames=["Predicted (anomaly_label)"],
            margins=True,
        )
        print(crosstab.to_string())

        # Simple precision / recall from the crosstab
        tp = ((df["label"] == 1) & (df["anomaly_label"] == 1)).sum()
        fp = ((df["label"] == 0) & (df["anomaly_label"] == 1)).sum()
        fn = ((df["label"] == 1) & (df["anomaly_label"] == 0)).sum()

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = (2 * precision * recall / (precision + recall)
                     if (precision + recall) > 0 else 0.0)

        print(f"\n  Precision : {precision:.2f}  "
              f"(of all transactions flagged, {precision*100:.0f}% are real fraud)")
        print(f"  Recall    : {recall:.2f}  "
              f"(of all real fraud cases, {recall*100:.0f}% were caught)")
        print(f"  F1 Score  : {f1:.2f}")
        print()
        print("  Note: Isolation Forest is UNSUPERVISED — it has never")
        print("  seen the labels.  Low precision / recall is expected.")
        print("  Use these scores to tune 'contamination' if needed.")

    print("=" * 60)


# ---------------------------------------------------------------------------
# Save the trained model (optional helper)
# ---------------------------------------------------------------------------

def save_model(model: IsolationForest, filename: str = "isolation_forest.pkl") -> None:
    """Save the trained model to ml/model/ using joblib."""
    try:
        import joblib
    except ImportError:
        print("  joblib not installed — model not saved.  Run: pip install joblib")
        return

    os.makedirs(MODEL_DIR, exist_ok=True)
    path = os.path.join(MODEL_DIR, filename)
    joblib.dump(model, path)
    print(f"\n  Model saved to '{path}'.")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    print("\n[ Step 1 ] Loading engineered data ...")
    df = load_engineered_data()

    print("\n[ Step 2 ] Selecting feature columns ...")
    X = prepare_features(df)
    print(f"  Feature matrix shape: {X.shape[0]:,} rows × {X.shape[1]} columns")
    print(f"  Features used: {list(X.columns)}")

    print("\n[ Step 3 ] Training Isolation Forest ...")
    model = train_isolation_forest(X)

    print("\n[ Step 4 & 5 ] Generating anomaly scores and labels ...")
    df = add_anomaly_columns(df, model, X)

    print("\n[ Step 6 ] Printing results ...")
    print_summary(df)

    # Save model artifact
    save_model(model)


if __name__ == "__main__":
    main()

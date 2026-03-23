"""
withdrawal_api.py — Isolation Forest Withdrawal Detection API
==============================================================
A lightweight Flask API that accepts a single withdrawal transaction
and returns an anomaly prediction, risk label, and plain-English
explanation of why the transaction looks suspicious.

Endpoints
---------
  GET  /          — API status / usage instructions
  POST /predict   — Analyse one withdrawal transaction

How to run
----------
  python withdrawal_api.py          # dev server on port 5002
  gunicorn withdrawal_api:app       # production

Example request
---------------
  curl -X POST http://localhost:5002/predict \\
       -H "Content-Type: application/json" \\
       -d '{
             "amount": 8000,
             "balance_before": 8500,
             "balance_after": 500,
             "sim_swap_flag": 1,
             "txn_hour": 2,
             "amount_zscore": 3.2,
             "txn_time_deviation": 9.5,
             "balance_drain_ratio": 0.94,
             "is_new_device": 1,
             "is_new_location": 1,
             "velocity_1day": 7
           }'

Example response
----------------
  {
    "prediction": "suspicious",
    "anomaly_label": 1,
    "anomaly_score": -0.18,
    "explanation": "This withdrawal was flagged because sim_swap_flag was
                    unusually high; amount was unusually high; balance_drain_ratio
                    was unusually high."
  }
"""

import os
import sys
import sqlite3
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from sklearn.ensemble import IsolationForest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The 11 behavioral features — must match isolation_forest.py exactly.
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

# Paths (using pathlib for safe, readable path construction)
BASE_DIR       = Path(__file__).resolve().parent
ENGINEERED_CSV = BASE_DIR / "data" / "engineered_features.csv"
MODEL_PATH     = BASE_DIR / "model" / "isolation_forest.pkl"
DB_PATH        = BASE_DIR / "data" / "fraud_monitor.db"

# Isolation Forest settings (used only when training from scratch)
CONTAMINATION = "auto"
N_ESTIMATORS  = 100
RANDOM_STATE  = 42

# Features flagged if their deviation from the dataset mean exceeds this
# z-score threshold.
DEVIATION_THRESHOLD = 1.0


# ---------------------------------------------------------------------------
# Model + dataset — loaded once at startup
# ---------------------------------------------------------------------------

def _load_or_train_model():
    """
    Return (model, X_train, col_means, col_stds) so the API can both
    predict and explain without re-loading data on every request.

    Priority:
    1. Load saved model from model/isolation_forest.pkl  +  training data
       from engineered_features.csv.
    2. If model file is missing, train from engineered_features.csv.
    3. If the CSV is also missing, try to generate it by running
       feature_engineering.py, then train.
    """
    # ── Ensure training data is available ───────────────────────────
    if not ENGINEERED_CSV.exists():
        fe_script = BASE_DIR / "feature_engineering.py"
        if fe_script.exists():
            print("  engineered_features.csv not found — running feature_engineering.py ...")
            import subprocess
            result = subprocess.run([sys.executable, str(fe_script)],
                                    capture_output=True, text=True)
            if result.returncode != 0 or not ENGINEERED_CSV.exists():
                last = result.stderr.strip().splitlines()[-1] if result.stderr else "unknown"
                raise RuntimeError(
                    f"Could not generate engineered_features.csv. "
                    f"Run 'python feature_engineering.py' manually. Reason: {last}"
                )
        else:
            raise RuntimeError(
                "engineered_features.csv not found and feature_engineering.py "
                "is missing. Run 'python feature_engineering.py' first."
            )

    # ── Load training data ──────────────────────────────────────────
    df_train = pd.read_csv(str(ENGINEERED_CSV))
    X_train  = _prepare_matrix(df_train)
    col_means = X_train.mean()
    col_stds  = X_train.std().replace(0, 1)   # avoid division by zero

    # ── Load or train model ─────────────────────────────────────────
    if MODEL_PATH.exists():
        model = joblib.load(str(MODEL_PATH))
        print(f"  Model loaded from '{MODEL_PATH}'.")
    else:
        print("  Model file not found — training Isolation Forest from engineered_features.csv ...")
        model = IsolationForest(
            n_estimators=N_ESTIMATORS,
            contamination=CONTAMINATION,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
        model.fit(X_train)
        # Save for next time
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, str(MODEL_PATH))
        print(f"  Model saved to '{MODEL_PATH}'.")

    return model, col_means, col_stds


def _prepare_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Return a clean numeric DataFrame with exactly the FEATURES columns."""
    for col in FEATURES:
        if col not in df.columns:
            df[col] = 0.0
    X = df[FEATURES].copy()
    X = X.apply(pd.to_numeric, errors="coerce").fillna(0)
    return X


# Load everything once when the module is imported (i.e. at server startup).
print("\n[ Startup ] Loading model and training data ...")
_model, _col_means, _col_stds = _load_or_train_model()
print("[ Startup ] Ready.\n")


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def init_db():
    """
    Create data/fraud_monitor.db and the prediction_history table
    if they do not already exist.  Safe to call on every startup.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prediction_history (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp           TEXT,
                amount              REAL,
                balance_before      REAL,
                balance_after       REAL,
                sim_swap_flag       INTEGER,
                txn_hour            INTEGER,
                amount_zscore       REAL,
                txn_time_deviation  REAL,
                balance_drain_ratio REAL,
                is_new_device       INTEGER,
                is_new_location     INTEGER,
                velocity_1day       INTEGER,
                prediction          TEXT,
                anomaly_label       INTEGER,
                anomaly_score       REAL,
                risk_level          TEXT,
                explanation         TEXT
            )
        """)
        conn.commit()
    print(f"[ DB ] fraud_monitor.db ready at '{DB_PATH}'.")


def save_prediction_to_db(record: dict):
    """
    Insert one prediction record into the prediction_history table.

    Expected keys in *record*:
        timestamp, amount, balance_before, balance_after, sim_swap_flag,
        txn_hour, amount_zscore, txn_time_deviation, balance_drain_ratio,
        is_new_device, is_new_location, velocity_1day,
        prediction, anomaly_label, anomaly_score, risk_level, explanation
    """
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            INSERT INTO prediction_history (
                timestamp, amount, balance_before, balance_after,
                sim_swap_flag, txn_hour, amount_zscore, txn_time_deviation,
                balance_drain_ratio, is_new_device, is_new_location,
                velocity_1day, prediction, anomaly_label, anomaly_score,
                risk_level, explanation
            ) VALUES (
                :timestamp, :amount, :balance_before, :balance_after,
                :sim_swap_flag, :txn_hour, :amount_zscore, :txn_time_deviation,
                :balance_drain_ratio, :is_new_device, :is_new_location,
                :velocity_1day, :prediction, :anomaly_label, :anomaly_score,
                :risk_level, :explanation
            )
        """, record)
        conn.commit()


# Initialise DB at startup
init_db()


# ---------------------------------------------------------------------------
# Explanation helper
# ---------------------------------------------------------------------------

def _build_explanation(row: pd.Series) -> str:
    """
    Compare a single transaction row against the training-set averages.
    Return a human-readable sentence naming the top suspicious signals.
    """
    z_scores = (row - _col_means) / _col_stds

    # Sort by absolute z-score, largest first
    ranked = sorted(
        zip(FEATURES, row, z_scores),
        key=lambda t: abs(t[2]),
        reverse=True,
    )

    flagged = [
        (feat, val, z)
        for feat, val, z in ranked
        if abs(z) >= DEVIATION_THRESHOLD
    ]

    if not flagged:
        return (
            "No single feature stands out strongly — the model flagged this "
            "based on the combined pattern of all features."
        )

    reasons = []
    for feat, val, z in flagged[:4]:
        direction = "unusually high" if z > 0 else "unusually low"
        reasons.append(f"{feat} was {direction} ({val:.2f})")

    return "This withdrawal was flagged because " + "; ".join(reasons) + "."


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)
CORS(app)


@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    """Health check — confirms the API is running and the model is loaded."""
    return jsonify({
        "service":        "Withdrawal Anomaly Detection API",
        "model":          "Isolation Forest",
        "status":         "running",
        "model_file":     str(MODEL_PATH),
        "endpoints": {
            "GET  /health":   "Health check (this response)",
            "POST /predict":  "Analyse a single withdrawal transaction",
            "GET  /history":  "Return full prediction history (newest first)",
        },
        "required_fields": FEATURES,
    })


@app.route("/predict", methods=["POST"])
def predict():
    """
    Accept a JSON object with the 11 behavioral features and return
    an anomaly prediction with a plain-English explanation.
    """
    data = request.get_json(silent=True)
    print(f"[/predict] incoming JSON: {data}")

    # ── Input validation ────────────────────────────────────────────
    if not data:
        return jsonify({"error": "Bad request", "details": "Request body must be valid JSON."}), 400

    missing = [f for f in FEATURES if f not in data]
    if missing:
        return jsonify({
            "error":   "Bad request",
            "details": f"Missing required fields: {missing}",
            "required": FEATURES,
        }), 400

    # ── Build feature row ───────────────────────────────────────────
    try:
        row_dict = {feat: float(data[feat]) for feat in FEATURES}
    except (ValueError, TypeError) as exc:
        return jsonify({"error": f"All feature values must be numeric. {exc}"}), 400

    row_df  = pd.DataFrame([row_dict], columns=FEATURES)
    row_ser = row_df.iloc[0]   # Series — used for explanation

    # ── Predict ─────────────────────────────────────────────────────
    raw_pred     = _model.predict(row_df)[0]       # -1 or +1
    anomaly_score = float(_model.decision_function(row_df)[0])

    # sklearn returns -1 for anomaly, +1 for normal → remap to 1/0
    anomaly_label = 1 if raw_pred == -1 else 0
    prediction    = "suspicious" if anomaly_label == 1 else "normal"

    # ── Explain ─────────────────────────────────────────────────────
    explanation = _build_explanation(row_ser)
    risk_level  = "HIGH RISK" if anomaly_label == 1 else "LOW RISK"

    # ── Save to SQLite ────────────────────────────────────────────
    save_prediction_to_db({
        "timestamp":           datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "amount":              row_dict["amount"],
        "balance_before":      row_dict["balance_before"],
        "balance_after":       row_dict["balance_after"],
        "sim_swap_flag":       int(row_dict["sim_swap_flag"]),
        "txn_hour":            int(row_dict["txn_hour"]),
        "amount_zscore":       row_dict["amount_zscore"],
        "txn_time_deviation":  row_dict["txn_time_deviation"],
        "balance_drain_ratio": row_dict["balance_drain_ratio"],
        "is_new_device":       int(row_dict["is_new_device"]),
        "is_new_location":     int(row_dict["is_new_location"]),
        "velocity_1day":       int(row_dict["velocity_1day"]),
        "prediction":          prediction,
        "anomaly_label":       anomaly_label,
        "anomaly_score":       round(anomaly_score, 6),
        "risk_level":          risk_level,
        "explanation":         explanation,
    })

    return jsonify({
        "prediction":    prediction,
        "anomaly_label": anomaly_label,
        "anomaly_score": round(anomaly_score, 6),
        "explanation":   explanation,
    })


@app.route("/history", methods=["GET"])
def history():
    """
    Return all prediction records from SQLite as JSON, newest first.
    """
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM prediction_history ORDER BY id DESC"
        ).fetchall()

    return jsonify([dict(row) for row in rows])


# ---------------------------------------------------------------------------
# Dev server entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("WITHDRAWAL_API_PORT", 5002))
    print(f"Withdrawal Detection API  →  http://localhost:{port}")
    print("  GET  /         — status")
    print("  POST /predict  — analyse a transaction\n")
    app.run(host="0.0.0.0", port=port, debug=True)

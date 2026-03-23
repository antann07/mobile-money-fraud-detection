"""
predict_api.py — Behavioral Fraud Detection API
================================================
Uses an Isolation Forest model trained on engineered behavioral
features to detect fraudulent / anomalous transactions.

Usage:
    python predict_api.py          # dev mode (port 5001)
    gunicorn predict_api:app       # production

Request  (JSON):
    {
      "amount":             8000,
      "balance_before":     8500,
      "balance_after":       500,
      "sim_swap_flag":         1,
      "txn_hour":              2,
      "amount_zscore":       3.2,
      "txn_time_deviation":  9.5,
      "balance_drain_ratio": 0.94,
      "is_new_device":         1,
      "is_new_location":       1,
      "velocity_1day":         7
    }

Response (JSON):
    {
      "prediction":    "suspicious",
      "anomaly_label": 1,
      "anomaly_score": -0.18,
      "explanation":   "This transaction was flagged because ..."
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
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from sklearn.ensemble import IsolationForest

# SQLite helpers from db_helper
from db_helper import init_db, save_prediction_to_db, get_prediction_history, DB_PATH

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The 11 behavioral features the model expects
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

# File paths
BASE_DIR       = Path(__file__).resolve().parent
ENGINEERED_CSV = BASE_DIR / "data" / "engineered_features.csv"
MODEL_PATH     = BASE_DIR / "model" / "isolation_forest.pkl"

# Isolation Forest settings (only used when training from scratch)
N_ESTIMATORS = 100
CONTAMINATION = "auto"
RANDOM_STATE  = 42

# A feature is considered suspicious when its z-score exceeds this threshold
DEVIATION_THRESHOLD = 1.0


# ---------------------------------------------------------------------------
# Startup: load or train the model
# ---------------------------------------------------------------------------

def load_or_train_model():
    """
    Load the saved Isolation Forest model and training data.
    If the model file does not exist yet, train it automatically
    from engineered_features.csv and save it for next time.

    Returns: (model, col_means, col_stds)
    """
    # Step 1 — make sure training data exists
    if not ENGINEERED_CSV.exists():
        fe_script = BASE_DIR / "feature_engineering.py"
        if fe_script.exists():
            print("  engineered_features.csv not found — running feature_engineering.py ...")
            import subprocess
            result = subprocess.run(
                [sys.executable, str(fe_script)],
                capture_output=True, text=True
            )
            if result.returncode != 0 or not ENGINEERED_CSV.exists():
                raise RuntimeError(
                    "Could not generate engineered_features.csv. "
                    "Run 'python feature_engineering.py' manually first."
                )
        else:
            raise RuntimeError(
                "engineered_features.csv not found. "
                "Run 'python feature_engineering.py' first."
            )

    # Step 2 — load training data and compute column statistics
    df_train = pd.read_csv(str(ENGINEERED_CSV))

    # Make sure every expected feature column is present
    for col in FEATURES:
        if col not in df_train.columns:
            df_train[col] = 0.0

    X_train = df_train[FEATURES].apply(pd.to_numeric, errors="coerce").fillna(0)

    col_means = X_train.mean()
    col_stds  = X_train.std().replace(0, 1)   # avoid division by zero

    # Step 3 — load saved model, or train a new one
    if MODEL_PATH.exists():
        model = joblib.load(str(MODEL_PATH))
        print(f"  Model loaded from '{MODEL_PATH}'.")
    else:
        print("  No saved model found — training Isolation Forest ...")
        model = IsolationForest(
            n_estimators=N_ESTIMATORS,
            contamination=CONTAMINATION,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
        model.fit(X_train)
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, str(MODEL_PATH))
        print(f"  Model saved to '{MODEL_PATH}'.")

    return model, col_means, col_stds


def build_explanation(row: pd.Series, col_means: pd.Series, col_stds: pd.Series) -> str:
    """
    Compare one transaction row against training-set averages.
    Returns a plain-English sentence describing the suspicious signals.
    """
    z_scores = (row - col_means) / col_stds

    # Sort features by how far they deviate (largest deviation first)
    ranked = sorted(
        zip(FEATURES, row, z_scores),
        key=lambda t: abs(t[2]),
        reverse=True,
    )

    # Keep only features that exceed the threshold
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
    for feat, val, z in flagged[:4]:   # show at most 4 reasons
        direction = "unusually high" if z > 0 else "unusually low"
        reasons.append(f"{feat} was {direction} ({val:.2f})")

    return "This transaction was flagged because " + "; ".join(reasons) + "."


# Load everything once when the server starts
print("\n[ Startup ] Loading model ...")
_model, _col_means, _col_stds = load_or_train_model()
print("[ Startup ] Ready.\n")


# ---------------------------------------------------------------------------
# SQLite — persistent prediction history (via db_helper)
# ---------------------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    """Return a SQLite connection to the shared fraud_monitor.db."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)
CORS(app)   # allow requests from any origin (e.g. the dashboard)

# Initialise DB on startup (creates fraud_monitor.db + prediction_history table)
init_db()


@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "Mobile Money Fraud Detection API is running"})


@app.route("/health", methods=["GET"])
def health():
    """Health check — also reports total predictions stored."""
    with _get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM prediction_history").fetchone()
        total = row["n"] if row else 0
    return jsonify({
        "status":            "ok",
        "model":             "Isolation Forest",
        "detection_type":    "Unsupervised Anomaly Detection",
        "features":          FEATURES,
        "total_predictions": total,
    })


@app.route("/predict", methods=["POST"])
def predict():
    """
    Analyse one transaction and return a fraud prediction.

    Accepts a JSON object with the 11 behavioral features.
    Stores the result in SQLite and returns it to the caller.
    """
    # ── Parse request body ───────────────────────────────────────────
    data = request.get_json(silent=True)
    print(f"[/predict] incoming JSON: {data}")

    if not data:
        return jsonify({"error": "Bad request", "details": "Request body must be valid JSON."}), 400

    # ── Check for missing fields ─────────────────────────────────────
    missing = [f for f in FEATURES if f not in data]
    if missing:
        return jsonify({
            "error":    "Bad request",
            "details":  f"Missing required fields: {missing}",
            "required": FEATURES,
        }), 400

    # ── Convert all values to float ──────────────────────────────────
    try:
        row_dict = {feat: float(data[feat]) for feat in FEATURES}
    except (ValueError, TypeError) as exc:
        return jsonify({"error": "Bad request", "details": f"All values must be numeric. {exc}"}), 400

    # ── Build a one-row DataFrame ────────────────────────────────────
    row_df  = pd.DataFrame([row_dict], columns=FEATURES)
    row_ser = row_df.iloc[0]

    # ── Run Isolation Forest ─────────────────────────────────────────
    raw_pred      = _model.predict(row_df)[0]          # -1 or +1
    anomaly_score = float(_model.decision_function(row_df)[0])
    anomaly_label = 1 if raw_pred == -1 else 0
    prediction    = "suspicious" if anomaly_label == 1 else "normal"

    # ── Plain-English explanation ────────────────────────────────────
    explanation = build_explanation(row_ser, _col_means, _col_stds)

    # ── Determine risk level ──────────────────────────────────────────
    risk_level = "HIGH RISK" if prediction == "suspicious" else "LOW RISK"

    # ── Persist to SQLite via db_helper ──────────────────────────────
    record = {
        "timestamp":           datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "amount":              row_dict.get("amount"),
        "balance_before":      row_dict.get("balance_before"),
        "balance_after":       row_dict.get("balance_after"),
        "sim_swap_flag":       int(row_dict.get("sim_swap_flag", 0)),
        "txn_hour":            int(row_dict.get("txn_hour", 0)),
        "amount_zscore":       row_dict.get("amount_zscore"),
        "txn_time_deviation":  row_dict.get("txn_time_deviation"),
        "balance_drain_ratio": row_dict.get("balance_drain_ratio"),
        "is_new_device":       int(row_dict.get("is_new_device", 0)),
        "is_new_location":     int(row_dict.get("is_new_location", 0)),
        "velocity_1day":       int(row_dict.get("velocity_1day", 0)),
        "prediction":          prediction,
        "anomaly_label":       anomaly_label,
        "anomaly_score":       round(anomaly_score, 6),
        "risk_level":          risk_level,
        "explanation":         explanation,
    }
    save_prediction_to_db(record)

    return jsonify({
        "prediction":    prediction,
        "anomaly_label": anomaly_label,
        "anomaly_score": round(anomaly_score, 6),
        "risk_level":    risk_level,
        "explanation":   explanation,
    })


@app.route("/history", methods=["GET"])
def history():
    """
    Return prediction history from SQLite (newest first).
    Uses get_prediction_history() from db_helper.
    Returns an empty JSON list if no history exists.
    """
    rows = get_prediction_history()
    return jsonify(rows)


@app.route("/stats", methods=["GET"])
def stats():
    """
    Aggregate statistics for the monitoring dashboard.

    Returns:
        total           — total predictions ever stored
        suspicious      — count of suspicious predictions
        normal          — count of normal predictions
        fraud_rate_pct  — suspicious / total × 100
        avg_score       — mean anomaly_score (all records)
        avg_score_sus   — mean anomaly_score (suspicious only)
        recent_24h      — counts for the last 24 hours
        hourly_counts   — suspicion count per hour-of-day (0–23)
    """
    with _get_db() as conn:
        totals = conn.execute("""
            SELECT
                COUNT(*)                                     AS total,
                SUM(CASE WHEN prediction='suspicious' THEN 1 ELSE 0 END) AS suspicious,
                SUM(CASE WHEN prediction='normal'     THEN 1 ELSE 0 END) AS normal,
                ROUND(AVG(anomaly_score), 4)                 AS avg_score,
                ROUND(AVG(CASE WHEN prediction='suspicious'
                               THEN anomaly_score END), 4)   AS avg_score_sus
            FROM prediction_history
        """).fetchone()

        recent = conn.execute("""
            SELECT
                COUNT(*)                                             AS total_24h,
                SUM(CASE WHEN prediction='suspicious' THEN 1 ELSE 0 END) AS suspicious_24h
            FROM prediction_history
            WHERE timestamp >= datetime('now', '-1 day')
        """).fetchone()

        hourly = conn.execute("""
            SELECT
                CAST(strftime('%H', timestamp) AS INTEGER) AS hour,
                SUM(CASE WHEN prediction='suspicious' THEN 1 ELSE 0 END) AS count
            FROM prediction_history
            GROUP BY hour
            ORDER BY hour
        """).fetchall()

    total = totals["total"] or 0
    sus   = totals["suspicious"] or 0

    return jsonify({
        "total":          total,
        "suspicious":     sus,
        "normal":         totals["normal"] or 0,
        "fraud_rate_pct": round(sus / total * 100, 2) if total else 0,
        "avg_score":      totals["avg_score"],
        "avg_score_sus":  totals["avg_score_sus"],
        "recent_24h": {
            "total":      recent["total_24h"]      or 0,
            "suspicious": recent["suspicious_24h"] or 0,
        },
        "hourly_counts": [{"hour": r["hour"], "count": r["count"]}
                          for r in hourly],
    })


@app.route("/export", methods=["GET"])
def export_csv():
    """
    Export the full prediction history as a downloadable CSV file.
    Useful for offline analysis and academic reporting.
    """
    with _get_db() as conn:
        rows = conn.execute("SELECT * FROM prediction_history ORDER BY id ASC").fetchall()

    if not rows:
        return jsonify({"error": "No predictions stored yet."}), 404

    columns = rows[0].keys()
    lines   = [",".join(columns)]
    for r in rows:
        lines.append(",".join(str(r[c]) if r[c] is not None else "" for c in columns))

    csv_text = "\n".join(lines)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=fraud_predictions.csv"},
    )


# ---------------------------------------------------------------------------
# Dev server entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("ML_PORT", 5001))
    print(f"  Fraud Detection API  →  http://localhost:{port}")
    print("  POST /predict        — analyse a transaction")
    print("  GET  /history        — full prediction log")
    print("  GET  /stats          — aggregate analytics")
    print("  GET  /export         — download CSV")
    print("  GET  /health         — health check\n")
    app.run(host="0.0.0.0", port=port, debug=True)

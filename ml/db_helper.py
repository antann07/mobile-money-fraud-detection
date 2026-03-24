"""
db_helper.py — SQLite helper for fraud prediction history
==========================================================
Provides simple functions used by predict_api.py, withdrawal_api.py,
and any other script that needs to read/write prediction history:

    init_db()                  — create the database and table
    save_prediction(record)    — insert one prediction record
    get_history(limit=None)    — fetch records as list of dicts (newest first)
    get_stats()                — return summary statistics

Backward-compatible aliases:
    save_prediction_to_db      — same as save_prediction
    get_prediction_history     — same as get_history

Database file : ml/data/fraud_monitor.db
Table         : prediction_history
"""

import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# Path to the database file
# ---------------------------------------------------------------------------

# Always place the database in the same   ml/data/   folder regardless of
# which directory the calling script is run from.
_BASE_DIR = Path(__file__).resolve().parent
DB_PATH   = _BASE_DIR / "data" / "fraud_monitor.db"


# ---------------------------------------------------------------------------
# 1.  init_db()
# ---------------------------------------------------------------------------

def init_db():
    """
    Create the database file and the prediction_history table
    if they do not already exist.

    Safe to call every time the server starts — it will never
    overwrite existing data.
    """
    # Make sure the data/ directory exists
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

    print(f"[db_helper] Database ready: {DB_PATH}")


# ---------------------------------------------------------------------------
# 2.  save_prediction(record)
# ---------------------------------------------------------------------------

def save_prediction(record: dict):
    """
    Insert one prediction record into the prediction_history table.

    Parameters
    ----------
    record : dict
        Must contain these keys:
            timestamp, amount, balance_before, balance_after,
            sim_swap_flag, txn_hour, amount_zscore, txn_time_deviation,
            balance_drain_ratio, is_new_device, is_new_location,
            velocity_1day, prediction, anomaly_label, anomaly_score,
            risk_level, explanation

    Example
    -------
        save_prediction_to_db({
            "timestamp":           "2026-03-23 14:05:00",
            "amount":              8000.0,
            "balance_before":      8500.0,
            "balance_after":       500.0,
            "sim_swap_flag":       1,
            "txn_hour":            2,
            "amount_zscore":       3.2,
            "txn_time_deviation":  9.5,
            "balance_drain_ratio": 0.94,
            "is_new_device":       1,
            "is_new_location":     1,
            "velocity_1day":       7,
            "prediction":          "suspicious",
            "anomaly_label":       1,
            "anomaly_score":       -0.183,
            "risk_level":          "HIGH RISK",
            "explanation":         "This withdrawal was flagged because ...",
        })
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


# Backward-compatible alias
save_prediction_to_db = save_prediction


# ---------------------------------------------------------------------------
# 3.  get_history(limit=None)
# ---------------------------------------------------------------------------

def get_history(limit=None) -> list[dict]:
    """
    Return rows from prediction_history as a list of plain dicts,
    ordered newest first (highest id first).

    Parameters
    ----------
    limit : int or None
        Maximum number of rows to return.  None means return all.

    Returns
    -------
    list[dict]
        Each dict has the same keys as the table columns, including 'id'.
        Returns an empty list if no records exist yet.

    Example
    -------
        rows = get_history(limit=50)
        for row in rows:
            print(row["timestamp"], row["prediction"], row["anomaly_score"])
    """
    query = "SELECT * FROM prediction_history ORDER BY id DESC"
    params = ()

    if limit is not None:
        query += " LIMIT ?"
        params = (int(limit),)

    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    return [dict(row) for row in rows]


# Backward-compatible alias
get_prediction_history = get_history


# ---------------------------------------------------------------------------
# 4.  get_stats()
# ---------------------------------------------------------------------------

def get_stats() -> dict:
    """
    Return a summary of all predictions stored in the database.

    Returns
    -------
    dict with keys:
        total_predictions  — number of rows
        suspicious_count   — rows where prediction == 'suspicious'
        normal_count       — rows where prediction != 'suspicious'
        fraud_rate         — suspicious_count / total  (0.0 if no rows)
        avg_anomaly_score  — average anomaly_score     (0.0 if no rows)
    """
    with sqlite3.connect(str(DB_PATH)) as conn:
        row = conn.execute("""
            SELECT
                COUNT(*)                                            AS total,
                SUM(CASE WHEN prediction = 'suspicious' THEN 1 ELSE 0 END) AS suspicious,
                AVG(anomaly_score)                                  AS avg_score
            FROM prediction_history
        """).fetchone()

    total      = row[0] or 0
    suspicious = row[1] or 0
    normal     = total - suspicious
    fraud_rate = round(suspicious / total, 4) if total > 0 else 0.0
    avg_score  = round(row[2], 6) if row[2] is not None else 0.0

    return {
        "total_predictions": total,
        "suspicious_count":  suspicious,
        "normal_count":      normal,
        "fraud_rate":        fraud_rate,
        "avg_anomaly_score": avg_score,
    }


# ---------------------------------------------------------------------------
# Quick self-test — run this file directly to verify everything works
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from datetime import datetime

    print("Running self-test ...")

    # 1. Initialise
    init_db()

    # 2. Insert a test record
    save_prediction({
        "timestamp":           datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "amount":              8000.0,
        "balance_before":      8500.0,
        "balance_after":       500.0,
        "sim_swap_flag":       1,
        "txn_hour":            2,
        "amount_zscore":       3.2,
        "txn_time_deviation":  9.5,
        "balance_drain_ratio": 0.94,
        "is_new_device":       1,
        "is_new_location":     1,
        "velocity_1day":       7,
        "prediction":          "suspicious",
        "anomaly_label":       1,
        "anomaly_score":       -0.183421,
        "risk_level":          "HIGH RISK",
        "explanation":         "This withdrawal was flagged because sim_swap_flag was unusually high.",
    })
    print("  Test record inserted.")

    # 3. Read back (with limit)
    history = get_history(limit=5)
    print(f"  Records returned: {len(history)}")
    print(f"  Latest record: {history[0]}")

    # 4. Stats
    stats = get_stats()
    print(f"  Stats: {stats}")
    print("Self-test passed.")

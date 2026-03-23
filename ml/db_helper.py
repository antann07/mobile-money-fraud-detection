"""
db_helper.py — SQLite helper for fraud prediction history
==========================================================
Provides three simple functions used by withdrawal_api.py
(and any other script that needs to read/write prediction history):

    init_db()                  — create the database and table
    save_prediction_to_db()    — insert one prediction record
    get_prediction_history()   — fetch all records (newest first)

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
# 2.  save_prediction_to_db(record)
# ---------------------------------------------------------------------------

def save_prediction_to_db(record: dict):
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


# ---------------------------------------------------------------------------
# 3.  get_prediction_history()
# ---------------------------------------------------------------------------

def get_prediction_history() -> list[dict]:
    """
    Return every row in prediction_history as a list of plain dicts,
    ordered newest first (highest id first).

    Returns
    -------
    list[dict]
        Each dict has the same keys as the table columns, including 'id'.
        Returns an empty list if no records exist yet.

    Example
    -------
        rows = get_prediction_history()
        for row in rows:
            print(row["timestamp"], row["prediction"], row["anomaly_score"])
    """
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row   # lets us convert rows to dicts easily
        rows = conn.execute(
            "SELECT * FROM prediction_history ORDER BY id DESC"
        ).fetchall()

    # Convert sqlite3.Row objects to plain Python dicts
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Quick self-test — run this file directly to verify everything works
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from datetime import datetime

    print("Running self-test ...")

    # 1. Initialise
    init_db()

    # 2. Insert a test record
    save_prediction_to_db({
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

    # 3. Read back
    history = get_prediction_history()
    print(f"  Records in database: {len(history)}")
    print(f"  Latest record: {history[0]}")
    print("Self-test passed.")

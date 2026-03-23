"""
behavioral_features.py — Behavioral Feature Engineering
=========================================================
Adds user-behavior deviation features to a transaction DataFrame for
detecting UNAUTHORISED WITHDRAWALS in Mobile Money.

Pipeline
--------
  1. load_from_mongodb()  — pull transactions from MongoDB Atlas
  2. add_behavioral_features()  — engineer all 8 deviation features

Expected input columns (from transactions collection)
------------------------------------------------------
  userId        : str / ObjectId — the account owner
  timestamp     : datetime-castable — when the transaction occurred
  amount        : float           — transaction value
  balanceBefore : float           — wallet balance before the transaction
  deviceId      : str             — device fingerprint / user-agent
  location      : str             — geographic region of the transaction
  sim_swap_flag : int (0/1)       — already present in source data

Usage
-----
    from behavioral_features import load_from_mongodb, add_behavioral_features

    df = load_from_mongodb()           # step 1 — load from database
    df = add_behavioral_features(df)   # step 2 — compute all features
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv


# ── Resolve .env (try ml/ then backend/) ────────────────────────────
def _load_env() -> None:
    """Load .env from the ml/ directory, falling back to backend/."""
    ml_env = Path(__file__).parent / ".env"
    backend_env = Path(__file__).parent.parent / "backend" / ".env"
    for path in (ml_env, backend_env):
        if path.exists():
            load_dotenv(path)
            return


_load_env()


# ── Database loader ───────────────────────────────────────────────────
def load_from_mongodb(
    mongo_uri: str | None = None,
    db_name: str = "momo_fraud",
    collection: str = "transactions",
    query: dict | None = None,
) -> pd.DataFrame:
    """
    Load transaction records from MongoDB Atlas into a pandas DataFrame.

    Parameters
    ----------
    mongo_uri   : MongoDB connection string.  Reads ``MONGO_URI`` from the
                  environment when *None* (default).
    db_name     : Database name inside the cluster.  Default: ``momo_fraud``.
    collection  : Collection to query.  Default: ``transactions``.
    query       : Optional pymongo filter dict, e.g.
                  ``{"transactionType": {"$in": ["cashout", "withdrawal"]}}``.
                  Omit (or pass *None*) to load all documents.

    Returns
    -------
    pd.DataFrame
        One row per transaction document with MongoDB ``_id`` converted to a
        string ``_id`` column.  Ready for :func:`add_behavioral_features`.
    """
    try:
        from pymongo import MongoClient  # deferred so the module loads without pymongo
    except ImportError as exc:
        raise ImportError(
            "pymongo is required to load data from MongoDB.  "
            "Install it with:  pip install pymongo==4.7.3"
        ) from exc

    uri = mongo_uri or os.environ.get("MONGO_URI")
    if not uri:
        raise ValueError(
            "No MongoDB URI provided.  Set MONGO_URI in your .env file or "
            "pass it as the mongo_uri argument."
        )

    client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    try:
        docs = list(client[db_name][collection].find(query or {}))
    finally:
        client.close()

    if not docs:
        print(f"  [load_from_mongodb] No documents found in {db_name}.{collection}")
        return pd.DataFrame()

    df = pd.DataFrame(docs)

    # Convert ObjectId columns to plain strings for portability
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str)

    print(
        f"  [load_from_mongodb] Loaded {len(df):,} rows from "
        f"{db_name}.{collection}"
    )
    return df


# ── public columns added by this module ──────────────────────────────
BEHAVIORAL_FEATURES = [
    "txn_hour",
    "amount_zscore",
    "txn_time_deviation",
    "balance_drain_ratio",
    "is_new_device",
    "is_new_location",
    "velocity_1day",
    "sim_swap_flag",   # must already exist in source; listed for completeness
]


def add_behavioral_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich *df* with behavioural deviation features grouped by userId.

    Parameters
    ----------
    df : pd.DataFrame
        Raw transaction records.  Must contain the columns listed in the
        module docstring.  Extra columns are preserved unchanged.

    Returns
    -------
    pd.DataFrame
        A **copy** of *df* with the engineered columns appended.
        Rows remain in their original order.
        The DataFrame is ready for ML model training.
    """
    df = df.copy()

    # ── Normalise column names (camelCase → snake_case alias map) ────
    _alias = {
        "user_id":      "userId",
        "device_id":    "deviceId",
        "balance_before": "balanceBefore",
    }
    for snake, camel in _alias.items():
        if snake in df.columns and camel not in df.columns:
            df.rename(columns={snake: camel}, inplace=True)
        elif camel in df.columns and snake not in df.columns:
            pass        # already have the camelCase version — nothing to do

    _require = ["userId", "timestamp", "amount"]
    for col in _require:
        if col not in df.columns:
            raise ValueError(
                f"add_behavioral_features: required column '{col}' is missing. "
                f"Available columns: {list(df.columns)}"
            )

    # ── 0. Sort by user then time (needed for velocity & new-X flags) ─
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df.sort_values(["userId", "timestamp"], inplace=True, ignore_index=True)

    # ── 1. txn_hour — hour-of-day extracted from timestamp ───────────
    df["txn_hour"] = df["timestamp"].dt.hour

    # ── 2. amount_zscore ─────────────────────────────────────────────
    #   (amount − user_mean_amount) / user_std_amount
    #   std == 0 (single transaction or identical amounts) → 0.0
    user_stats = df.groupby("userId")["amount"].agg(
        _u_mean="mean", _u_std="std"
    ).reset_index()
    df = df.merge(user_stats, on="userId", how="left")
    # std NaN (single row) → 0 so denominator never blows up
    df["_u_std"] = df["_u_std"].fillna(0)
    df["amount_zscore"] = np.where(
        df["_u_std"] > 0,
        (df["amount"] - df["_u_mean"]) / df["_u_std"],
        0.0,
    )
    df.drop(columns=["_u_mean", "_u_std"], inplace=True)

    # ── 3. txn_time_deviation ────────────────────────────────────────
    #   |txn_hour − user's average txn_hour|
    user_avg_hour = df.groupby("userId")["txn_hour"].transform("mean")
    df["txn_time_deviation"] = (df["txn_hour"] - user_avg_hour).abs()

    # ── 4. balance_drain_ratio ───────────────────────────────────────
    #   amount / balanceBefore  (0 when balance is 0 or column absent)
    if "balanceBefore" in df.columns:
        df["balanceBefore"] = pd.to_numeric(df["balanceBefore"], errors="coerce").fillna(0)
        df["balance_drain_ratio"] = np.where(
            df["balanceBefore"] > 0,
            df["amount"] / df["balanceBefore"],
            0.0,
        )
    else:
        df["balance_drain_ratio"] = 0.0

    # ── 5. is_new_device ─────────────────────────────────────────────
    #   1 if this deviceId has NOT appeared in ANY earlier row for this user
    if "deviceId" in df.columns:
        df["deviceId"] = df["deviceId"].fillna("unknown")
        # duplicated() marks all repeats True; first occurrence → False → NOT seen before → 1
        df["is_new_device"] = (
            ~df.duplicated(subset=["userId", "deviceId"], keep="first")
        ).astype(int)
        # Flip: first occurrence of a device is "new" (1), subsequent are not (0)
        df["is_new_device"] = df.groupby("userId")["deviceId"].transform(
            lambda s: (~s.duplicated(keep="first")).astype(int)
        )
    else:
        df["is_new_device"] = 0

    # ── 6. is_new_location ───────────────────────────────────────────
    #   1 if this region has NOT appeared in ANY earlier row for this user
    _loc_col = next((c for c in ("region", "location") if c in df.columns), None)
    if _loc_col:
        df[_loc_col] = df[_loc_col].fillna("unknown")
        df["is_new_location"] = df.groupby("userId")[_loc_col].transform(
            lambda s: (~s.duplicated(keep="first")).astype(int)
        )
    else:
        df["is_new_location"] = 0

    # ── 7. velocity_1day ─────────────────────────────────────────────
    #   Number of transactions by the same user in the 24 h BEFORE
    #   (and including) the current transaction.
    #   Uses a time-indexed rolling window per user.
    df = df.set_index("timestamp")
    df["velocity_1day"] = (
        df.groupby("userId")["amount"]
        .transform(lambda s: s.rolling("1D", min_periods=1).count())
        .astype(int)
    )
    df = df.reset_index()

    # ── 8. sim_swap_flag — must already exist; ensure int dtype ──────
    if "sim_swap_flag" in df.columns:
        df["sim_swap_flag"] = pd.to_numeric(df["sim_swap_flag"], errors="coerce").fillna(0).astype(int)
    else:
        # Not present → default to 0 (no swap detected)
        df["sim_swap_flag"] = 0

    # ── Re-sort to original timestamp order ──────────────────────────
    df.sort_values("timestamp", inplace=True, ignore_index=True)

    return df


# ── Entry point: full pipeline ───────────────────────────────────────
if __name__ == "__main__":
    import sys

    USE_DB = "--db" in sys.argv   # python behavioral_features.py --db

    if USE_DB:
        # ── Step 1: load data from database ─────────────────────────
        print("\n[1/3] Loading transaction data from MongoDB ...")
        df = load_from_mongodb(
            # Filter to withdrawal-type transactions only
            query={"transactionType": {"$in": ["cashout", "withdrawal", "transfer_out"]}},
        )
        if df.empty:
            print("  No withdrawal transactions found. Exiting.")
            sys.exit(0)
    else:
        # ── Step 1 (offline): use sample data for smoke-test ─────────
        print("\n[1/3] Using embedded sample data (pass --db to load from MongoDB) ...")
        df = pd.DataFrame(
            {
                "userId":          ["u1", "u1", "u1", "u2", "u2"],
                "timestamp":       [
                    "2024-01-10 09:00:00",
                    "2024-01-10 09:30:00",
                    "2024-01-11 02:00:00",
                    "2024-01-10 14:00:00",
                    "2024-01-10 23:00:00",
                ],
                "amount":          [500,   500,   8000,  200,  250],
                "balanceBefore":   [5000,  4500,  4000,  1000, 900],
                "deviceId":        ["d1",  "d1",  "d2",  "d3", "d3"],
                "location":        ["Accra", "Accra", "Kumasi", "Tema", "Tema"],
                "sim_swap_flag":   [0, 0, 1, 0, 0],
                "transactionType": ["cashout"] * 5,
                "label":           [0, 0, 1, 0, 0],
            }
        )

    # ── Step 2: compute txn_hour ─────────────────────────────────────
    # (handled inside add_behavioral_features; shown here for clarity)
    print(f"[2/3] Running behavioral feature engineering on {len(df):,} rows ...")
    df = add_behavioral_features(df)

    # ── Step 3: compute amount_zscore + velocity_1day are now present ─
    print("[3/3] Feature engineering complete.")

    display_cols = [
        c for c in [
            "userId", "timestamp", "amount",
            "txn_hour",           # step 2a — extracted from timestamp
            "amount_zscore",      # step 2b — (amount - user_mean) / user_std
            "txn_time_deviation",
            "balance_drain_ratio",
            "is_new_device",
            "is_new_location",
            "velocity_1day",      # step 2c — rolling 24-h count per user
            "sim_swap_flag",
        ]
        if c in df.columns
    ]
    print("\n── Behavioral Features Output ──────────────────────────────")
    print(df[display_cols].to_string(index=False))
    print(f"\nShape: {df.shape}  |  Columns: {list(df.columns)}")

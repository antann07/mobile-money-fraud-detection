"""
feature_engineering.py
=======================
Loads user + transaction data from a SQLite database and computes
behavioral features that help detect UNAUTHORISED WITHDRAWALS in
Mobile Money.

How to run
----------
    python feature_engineering.py

Requirements
------------
    pip install pandas numpy sqlalchemy
"""

import os
import numpy as np
import pandas as pd
from sqlalchemy import create_engine

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# DATABASE_URL can be overridden via an environment variable.
# Default: a local SQLite file called momo_fraud.db in the same folder.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///momo_fraud.db",
)


# ---------------------------------------------------------------------------
# Step 1 – Load data from the database
# ---------------------------------------------------------------------------

def load_transactions(database_url=None, engine=None) -> pd.DataFrame:
    """
    Load the `users` and `transactions` tables from the database,
    then merge them on `user_id`.

    Parameters
    ----------
    database_url : str, optional
        SQLAlchemy connection string.  Defaults to the module-level
        DATABASE_URL (reads DATABASE_URL env var or falls back to a
        local SQLite file).
    engine : sqlalchemy.Engine, optional
        A pre-built engine.  Takes precedence over *database_url*.
        Useful for testing with in-memory databases.

    Returns
    -------
    pd.DataFrame
        Merged table with one row per transaction, enriched with user info.
    """
    if engine is None:
        engine = create_engine(database_url or DATABASE_URL)

    # Read both tables straight into DataFrames
    users        = pd.read_sql("SELECT * FROM users",        engine)
    transactions = pd.read_sql("SELECT * FROM transactions", engine)

    # Merge on user_id (left join keeps all transactions even if user row is
    # missing for some reason)
    df = transactions.merge(users, on="user_id", how="left", suffixes=("", "_user"))

    print(f"  Loaded {len(transactions):,} transactions for "
          f"{users['user_id'].nunique():,} users.")
    return df


# ---------------------------------------------------------------------------
# Step 2 – Engineer behavioral features
# ---------------------------------------------------------------------------

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add behavioral deviation features to *df*.

    New columns added
    -----------------
    txn_hour            – hour of day the transaction occurred (0-23)
    amount_zscore       – how unusual the amount is for this user
    txn_time_deviation  – how far the hour is from the user's normal hour
    balance_drain_ratio – fraction of balance withdrawn (safe: 0 when balance=0)
    is_new_device       – 1 if this device_id is new for this user
    is_new_location     – 1 if this region is new for this user
    velocity_1day       – how many transactions the user made in the last 24 h

    Parameters
    ----------
    df : pd.DataFrame
        Merged transaction+user data from :func:`load_transactions`.
        Must contain: user_id, timestamp, amount.
        Optional but used when present: balance_before, device_id, region.

    Returns
    -------
    pd.DataFrame
        Clean DataFrame with original columns plus the 7 engineered features.
    """

    df = df.copy()

    # ── Convert timestamp to datetime ───────────────────────────────
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    # ── Sort so that "previous" rows are genuinely earlier ──────────
    df.sort_values(["user_id", "timestamp"], inplace=True, ignore_index=True)

    # ── 1. txn_hour ─────────────────────────────────────────────────
    # Extract the hour of day (0–23) from the timestamp.
    df["txn_hour"] = df["timestamp"].dt.hour

    # ── 2. amount_zscore ────────────────────────────────────────────
    # Measures how unusual this transaction amount is for this user.
    # Formula: (amount − user_mean) / user_std
    # When std == 0 (only one transaction, or all amounts identical)
    # we return 0.0 to avoid division by zero.
    user_mean = df.groupby("user_id")["amount"].transform("mean")
    user_std  = df.groupby("user_id")["amount"].transform("std").fillna(0)

    df["amount_zscore"] = np.where(
        user_std > 0,
        (df["amount"] - user_mean) / user_std,
        0.0,
    )

    # ── 3. txn_time_deviation ────────────────────────────────────────
    # How far the transaction hour is from this user's average hour.
    # A 3 AM withdrawal from a user who always transacts at noon is suspicious.
    user_avg_hour = df.groupby("user_id")["txn_hour"].transform("mean")
    df["txn_time_deviation"] = (df["txn_hour"] - user_avg_hour).abs()

    # ── 4a. balance_after ────────────────────────────────────────────
    # Ensure balance_after always exists.
    # If the source data already has it, keep it as-is.
    # Otherwise compute it from balance_before - amount and clip to 0.
    if "balance_after" in df.columns:
        df["balance_after"] = pd.to_numeric(df["balance_after"], errors="coerce").fillna(0)
        print("  balance_after: loaded directly from source data.")
    elif "balance_before" in df.columns:
        balance_before = pd.to_numeric(df["balance_before"], errors="coerce").fillna(0)
        amount         = pd.to_numeric(df["amount"],         errors="coerce").fillna(0)
        df["balance_after"] = (balance_before - amount).clip(lower=0)
        print("  balance_after: computed as balance_before - amount (clipped to 0).")
    else:
        df["balance_after"] = 0.0
        print("  balance_after: neither source column found — defaulting to 0.")

    # ── 4b. balance_drain_ratio ──────────────────────────────────────
    # What fraction of the user's balance was withdrawn.
    # Safe handling: returns 0.0 when balance_before is 0 or missing.
    if "balance_before" in df.columns:
        balance = pd.to_numeric(df["balance_before"], errors="coerce").fillna(0)
        df["balance_drain_ratio"] = np.where(
            balance > 0,
            df["amount"] / balance,
            0.0,
        )
    else:
        df["balance_drain_ratio"] = 0.0

    # ── 5. is_new_device ─────────────────────────────────────────────
    # 1 if this is the FIRST time the user transacted from this device_id.
    # Subsequent transactions from the same device get 0.
    if "device_id" in df.columns:
        df["device_id"] = df["device_id"].fillna("unknown")
        df["is_new_device"] = (
            df.groupby("user_id")["device_id"]
            .transform(lambda s: (~s.duplicated(keep="first")).astype(int))
        )
    else:
        df["is_new_device"] = 0

    # ── 6. is_new_location ───────────────────────────────────────────
    # 1 if this is the FIRST time the user transacted from this region.
    loc_col = next((c for c in ("region", "location") if c in df.columns), None)
    if loc_col:
        df[loc_col] = df[loc_col].fillna("unknown")
        df["is_new_location"] = (
            df.groupby("user_id")[loc_col]
            .transform(lambda s: (~s.duplicated(keep="first")).astype(int))
        )
    else:
        df["is_new_location"] = 0

    # ── 7. velocity_1day ─────────────────────────────────────────────
    # How many transactions has this user made in the last 24 hours
    # (including the current one)?  Flags rapid repeated withdrawals.
    df = df.set_index("timestamp")
    df["velocity_1day"] = (
        df.groupby("user_id")["amount"]
        .transform(lambda s: s.rolling("1D", min_periods=1).count())
        .astype(int)
    )
    df = df.reset_index()

    # ── Ensure sim_swap_flag is integer if it already exists ─────────
    if "sim_swap_flag" in df.columns:
        df["sim_swap_flag"] = (
            pd.to_numeric(df["sim_swap_flag"], errors="coerce").fillna(0).astype(int)
        )

    # ── Choose which columns to keep in the final output ─────────────
    important_cols = [
        # Identifiers
        "user_id", "timestamp",
        # Transaction core
        "amount", "transaction_type",
        # Optional raw fields (kept if present)
        "balance_before", "balance_after", "device_id", "region", "location", "sim_swap_flag",
        # Engineered features
        "txn_hour", "amount_zscore", "txn_time_deviation",
        "balance_drain_ratio", "is_new_device", "is_new_location",
        "velocity_1day",
        # Label (for supervised training)
        "label",
    ]
    keep = [c for c in important_cols if c in df.columns]
    # Also keep any column not in our list (preserve extra user/txn fields)
    extra = [c for c in df.columns if c not in keep]
    df = df[keep + extra]

    return df


# ---------------------------------------------------------------------------
# Step 3 – Save the engineered dataset to CSV
# ---------------------------------------------------------------------------

def save_engineered_data(df: pd.DataFrame, output_path: str = None) -> str:
    """
    Save the engineered DataFrame to a CSV file so that other scripts
    (e.g. isolation_forest.py) can load it directly without re-running
    the full feature engineering pipeline.

    Parameters
    ----------
    df          : pd.DataFrame — engineered feature DataFrame to save.
    output_path : str, optional — full path for the output CSV.
                  Defaults to  <ml_dir>/data/engineered_features.csv.

    Returns
    -------
    str
        The absolute path where the file was saved.
    """
    if output_path is None:
        ml_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(ml_dir, "data", "engineered_features.csv")

    # Create the output directory if it doesn't exist yet
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    df.to_csv(output_path, index=False)
    print(f"  Engineered features saved to '{output_path}'  "
          f"({len(df):,} rows × {len(df.columns)} columns).")
    return output_path


# ---------------------------------------------------------------------------
# __main__ – quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # ── Create a tiny in-memory SQLite DB for testing ───────────────
    # (so the script runs without needing a real database file)
    from sqlalchemy import text

    print("Building in-memory sample database ...")
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                user_id   TEXT PRIMARY KEY,
                full_name TEXT,
                phone     TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO users VALUES
                ('u1', 'Alice Mensah',  '+233201111111'),
                ('u2', 'Bob Asante',    '+233202222222')
        """))
        conn.execute(text("""
            CREATE TABLE transactions (
                txn_id          TEXT PRIMARY KEY,
                user_id         TEXT,
                timestamp       TEXT,
                amount          REAL,
                balance_before  REAL,
                device_id       TEXT,
                region          TEXT,
                sim_swap_flag   INTEGER,
                transaction_type TEXT,
                label           INTEGER
            )
        """))
        conn.execute(text("""
            INSERT INTO transactions VALUES
                ('t1','u1','2024-01-10 09:00:00',  500, 5000,'d1','Accra', 0,'cashout',0),
                ('t2','u1','2024-01-10 09:30:00',  500, 4500,'d1','Accra', 0,'cashout',0),
                ('t3','u1','2024-01-11 02:00:00', 8000, 4000,'d2','Kumasi',1,'withdrawal',1),
                ('t4','u2','2024-01-10 14:00:00',  200, 1000,'d3','Tema',  0,'cashout',0),
                ('t5','u2','2024-01-10 23:00:00',  250,  900,'d3','Tema',  0,'cashout',0)
        """))

    print("Loading transactions ...")

    # Step 1 – load from database (pass the shared engine so the in-memory
    # tables we just created above are visible)
    df_raw = load_transactions(engine=engine)

    # Step 2 – engineer features
    print("Engineering features ...")
    df_features = engineer_features(df_raw)

    # Step 3 – save to CSV so isolation_forest.py can load it directly
    print("Saving engineered features ...")
    save_engineered_data(df_features)

    # Step 4 – display results
    feature_cols = [
        "user_id", "timestamp", "amount",
        "txn_hour", "amount_zscore", "txn_time_deviation",
        "balance_drain_ratio", "is_new_device", "is_new_location",
        "velocity_1day", "sim_swap_flag", "label",
    ]
    print("\n── Engineered Features ─────────────────────────────────────")
    print(df_features[feature_cols].to_string(index=False))
    print(f"\nFinal shape : {df_features.shape}")
    print(f"All columns : {list(df_features.columns)}")
    sys.exit(0)

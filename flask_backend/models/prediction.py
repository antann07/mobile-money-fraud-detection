"""Fraud prediction model – CRUD helpers for the fraud_predictions table."""

from db import get_db, PH, IntegrityError, insert_returning_id, query


def create_prediction(
    transaction_id: int,
    prediction: str,
    anomaly_label: int,
    anomaly_score: float,
    risk_level: str,
    explanation: str = "",
    amount_zscore: float = 0,
    txn_time_deviation: float = 0,
    balance_drain_ratio: float = 0,
    is_new_device: int = 0,
    is_new_location: int = 0,
    velocity_1day: int = 0,
) -> dict | None:
    """Insert a fraud prediction row. Returns the created row or None on conflict."""
    conn = get_db()
    try:
        new_id = insert_returning_id(
            conn,
            f"""
            INSERT INTO fraud_predictions
                (transaction_id, prediction, anomaly_label, anomaly_score,
                 risk_level, explanation, amount_zscore, txn_time_deviation,
                 balance_drain_ratio, is_new_device, is_new_location, velocity_1day)
            VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH})
            """,
            (transaction_id, prediction, anomaly_label, anomaly_score,
             risk_level, explanation, amount_zscore, txn_time_deviation,
             balance_drain_ratio, is_new_device, is_new_location, velocity_1day),
        )
        conn.commit()
        return get_prediction_by_id(new_id)
    except IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_prediction_by_id(pred_id: int) -> dict | None:
    """Fetch a single prediction by primary key."""
    conn = get_db()
    try:
        row = query(conn, f"SELECT * FROM fraud_predictions WHERE id = {PH}", (pred_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_prediction_by_transaction(transaction_id: int) -> dict | None:
    """Fetch the prediction for a given transaction."""
    conn = get_db()
    try:
        row = query(
            conn,
            f"SELECT * FROM fraud_predictions WHERE transaction_id = {PH}",
            (transaction_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_predictions_by_transaction_ids(txn_ids: list[int]) -> list[dict]:
    """Return all predictions for a list of transaction IDs."""
    if not txn_ids:
        return []
    conn = get_db()
    try:
        placeholders = ",".join(PH for _ in txn_ids)
        rows = query(
            conn,
            f"""
            SELECT fp.*,
                   t.wallet_id,
                   t.amount,
                   t.transaction_type,
                   t.direction,
                   t.transaction_time
            FROM fraud_predictions fp
            JOIN transactions t ON fp.transaction_id = t.id
            WHERE fp.transaction_id IN ({placeholders})
            ORDER BY fp.created_at DESC
            """,
            txn_ids,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

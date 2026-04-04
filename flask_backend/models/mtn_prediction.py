"""
MTN Prediction model — CRUD helpers for the predictions table.

Each prediction is the ML/rule-based verdict for one message_check.
Relationship: one prediction per message_check (1:1).

Output labels: 'genuine' | 'suspicious' | 'likely_fraudulent'

Provides:
  create_mtn_prediction()           — insert a verdict for a message check
  get_prediction_by_check_id()      — fetch verdict for a specific check
  get_prediction_with_check()       — fetch verdict joined with message_check data
  get_predictions_by_user()         — all predictions for a user (newest first)
"""

from db import get_db, PH, IntegrityError, insert_returning_id, query


def create_mtn_prediction(
    message_check_id: int,
    predicted_label: str,
    confidence_score: float,
    explanation: str = None,
    format_risk_score: float = 0.0,
    behavior_risk_score: float = 0.0,
    balance_consistency_score: float = 0.0,
    sender_novelty_score: float = 0.0,
    model_version: str = "v1",
) -> dict | None:
    """
    Insert a prediction for a message check.

    Required: message_check_id, predicted_label, confidence_score.
    Returns the created row as a dict, or None on duplicate/failure.
    """
    conn = get_db()
    try:
        new_id = insert_returning_id(
            conn,
            f"""
            INSERT INTO predictions
                (message_check_id, predicted_label, confidence_score, explanation,
                 format_risk_score, behavior_risk_score,
                 balance_consistency_score, sender_novelty_score, model_version)
            VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH})
            """,
            (
                message_check_id, predicted_label, confidence_score, explanation,
                format_risk_score, behavior_risk_score,
                balance_consistency_score, sender_novelty_score, model_version,
            ),
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
        row = query(conn, f"SELECT * FROM predictions WHERE id = {PH}", (pred_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_prediction_by_check_id(message_check_id: int) -> dict | None:
    """Fetch the prediction for a given message check."""
    conn = get_db()
    try:
        row = query(
            conn,
            f"SELECT * FROM predictions WHERE message_check_id = {PH}",
            (message_check_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_prediction_with_check(message_check_id: int) -> dict | None:
    """
    Fetch prediction joined with its message_check data.
    Useful for showing the full result to the user.
    """
    conn = get_db()
    try:
        row = query(
            conn,
            f"""
            SELECT
                p.*,
                mc.source_channel,
                mc.raw_text,
                mc.amount,
                mc.counterparty_name,
                mc.counterparty_number,
                mc.transaction_type,
                mc.direction,
                mc.status       AS check_status,
                mc.provider,
                mc.created_at   AS check_created_at
            FROM predictions p
            JOIN message_checks mc ON p.message_check_id = mc.id
            WHERE p.message_check_id = {PH}
            """,
            (message_check_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_predictions_by_user(user_id: int, limit: int = 50) -> list[dict]:
    """Return all predictions for a user's message checks, newest first."""
    conn = get_db()
    try:
        rows = query(
            conn,
            f"""
            SELECT
                p.*,
                mc.source_channel,
                mc.raw_text,
                mc.amount,
                mc.counterparty_name,
                mc.status       AS check_status,
                mc.provider
            FROM predictions p
            JOIN message_checks mc ON p.message_check_id = mc.id
            WHERE mc.user_id = {PH}
            ORDER BY p.created_at DESC
            LIMIT {PH}
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

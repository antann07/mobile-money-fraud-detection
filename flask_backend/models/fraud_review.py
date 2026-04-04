"""
FraudReview model — CRUD helpers for the fraud_reviews table.

Admin/reviewer audit trail for message checks flagged by the ML engine.
Allows human override of automated predictions.

review_status values: 'pending' | 'confirmed_fraud' | 'confirmed_genuine' | 'escalated'
reviewer_label values: 'genuine' | 'suspicious' | 'likely_fraudulent' (or None if not yet reviewed)

Provides:
  create_review()            — queue a message check for human review
  get_review_by_id()         — fetch one review
  get_reviews_by_status()    — admin queue filtered by status
  update_review()            — submit reviewer verdict
  get_review_by_check_id()   — fetch review for a specific message check
"""

from db import get_db, PH, IntegrityError, insert_returning_id, query, execute


def create_review(
    message_check_id: int,
    predicted_label: str,
) -> dict | None:
    """
    Queue a message check for admin review (minimal — status 'pending').

    Called automatically when the ML engine flags a message as
    'suspicious' or 'likely_fraudulent'.

    Returns the created review row, or None on failure.
    """
    conn = get_db()
    try:
        new_id = insert_returning_id(
            conn,
            f"""
            INSERT INTO fraud_reviews
                (message_check_id, predicted_label, review_status)
            VALUES ({PH}, {PH}, 'pending')
            """,
            (message_check_id, predicted_label),
        )
        conn.commit()
        return get_review_by_id(new_id)
    except IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def create_full_review(
    message_check_id: int,
    predicted_label: str,
    reviewer_label: str,
    review_status: str,
    reviewed_by: int,
    notes: str = None,
) -> dict | None:
    """
    Create a review with all fields in a single INSERT.
    Avoids the two-step create-then-update pattern.

    Returns the created review row, or None on failure.
    """
    conn = get_db()
    try:
        new_id = insert_returning_id(
            conn,
            f"""
            INSERT INTO fraud_reviews
                (message_check_id, predicted_label, reviewer_label,
                 review_status, reviewed_by, notes, reviewed_at)
            VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, CURRENT_TIMESTAMP)
            """,
            (message_check_id, predicted_label, reviewer_label,
             review_status, reviewed_by, notes),
        )
        conn.commit()
        return get_review_by_id(new_id)
    except IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_review_by_id(review_id: int) -> dict | None:
    """Fetch a single review by primary key."""
    conn = get_db()
    try:
        row = query(
            conn, f"SELECT * FROM fraud_reviews WHERE id = {PH}", (review_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_review_by_check_id(message_check_id: int) -> dict | None:
    """Fetch the review for a specific message check (if one exists)."""
    conn = get_db()
    try:
        row = query(
            conn,
            f"SELECT * FROM fraud_reviews WHERE message_check_id = {PH}",
            (message_check_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_reviews_by_status(status: str = "pending", limit: int = 100) -> list[dict]:
    """
    Return reviews filtered by status, with message check + user info.
    Default: show the 'pending' queue for reviewers.
    """
    conn = get_db()
    try:
        rows = query(
            conn,
            f"""
            SELECT
                fr.*,
                mc.raw_text,
                mc.source_channel,
                mc.amount,
                mc.counterparty_name,
                mc.counterparty_number,
                mc.provider,
                u.full_name  AS submitter_name,
                u.email      AS submitter_email
            FROM fraud_reviews fr
            JOIN message_checks mc ON fr.message_check_id = mc.id
            JOIN users u           ON mc.user_id = u.id
            WHERE fr.review_status = {PH}
            ORDER BY fr.id DESC
            LIMIT {PH}
            """,
            (status, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_review(
    review_id: int,
    reviewer_label: str,
    review_status: str,
    reviewed_by: int,
    notes: str = None,
) -> dict | None:
    """
    Submit a reviewer's verdict on a flagged message.

    Args:
        review_id:      the fraud_reviews.id
        reviewer_label: 'genuine' | 'suspicious' | 'likely_fraudulent'
        review_status:  'confirmed_fraud' | 'confirmed_genuine' | 'escalated'
        reviewed_by:    user_id of the admin/reviewer
        notes:          optional reviewer comments

    Returns the updated review row, or None if not found.
    """
    conn = get_db()
    try:
        execute(
            conn,
            f"""
            UPDATE fraud_reviews
            SET reviewer_label = {PH},
                review_status  = {PH},
                reviewed_by    = {PH},
                notes          = {PH},
                reviewed_at    = CURRENT_TIMESTAMP
            WHERE id = {PH}
            """,
            (reviewer_label, review_status, reviewed_by, notes, review_id),
        )
        conn.commit()
        return get_review_by_id(review_id)
    finally:
        conn.close()

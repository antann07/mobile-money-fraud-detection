"""
Review Service — business logic for the admin review workflow.

Provides:
  get_flagged_checks()          — fetch message checks flagged as suspicious/likely_fraudulent
  get_review_detail()           — full detail for a single flagged check
  submit_review()               — create or update a fraud_review record
"""

import logging
from db import get_db, PH, query
from models.fraud_review import (
    get_review_by_check_id,
    create_full_review,
    update_review,
)

logger = logging.getLogger(__name__)

# Labels that trigger the review queue
_FLAGGED_LABELS = ("suspicious", "likely_fraudulent")

# Allowed values for reviewer input
_VALID_REVIEWER_LABELS = {"genuine", "suspicious", "likely_fraudulent"}
_VALID_REVIEW_STATUSES = {"pending", "confirmed_fraud", "confirmed_genuine", "escalated"}

# Safety limit for notes length
_MAX_NOTES_LENGTH = 2000


def get_flagged_checks(limit: int = 200) -> tuple[dict, int]:
    """
    Return message checks whose prediction label is suspicious or likely_fraudulent,
    joined with prediction summary and any existing review info.
    Newest first.

    Returns (response_body, http_status).
    """
    conn = get_db()
    try:
        rows = query(
            conn,
            f"""
            SELECT
                mc.id               AS message_check_id,
                mc.created_at,
                mc.source_channel,
                mc.counterparty_name,
                mc.counterparty_number,
                mc.amount,
                mc.currency,
                mc.status           AS check_status,
                p.predicted_label,
                p.confidence_score,
                p.explanation,
                fr.id               AS review_id,
                fr.review_status,
                fr.reviewer_label,
                fr.reviewed_at
            FROM message_checks mc
            JOIN predictions p ON p.message_check_id = mc.id
            LEFT JOIN fraud_reviews fr ON fr.message_check_id = mc.id
            WHERE p.predicted_label IN ({PH}, {PH})
            ORDER BY mc.created_at DESC
            LIMIT {PH}
            """,
            (*_FLAGGED_LABELS, limit),
        ).fetchall()

        items = []
        for r in rows:
            item = dict(r)
            # Phase-10: add sender_name alias so frontend column works
            item["sender_name"] = item.get("counterparty_name")
            items.append(item)

        return {
            "success": True,
            "count": len(items),
            "data": items,
        }, 200
    except Exception:
        logger.exception("Database error fetching flagged checks")
        return {
            "success": False,
            "errors": ["Failed to query flagged checks. Please try again."],
        }, 500
    finally:
        conn.close()


def get_review_detail(message_check_id: int) -> tuple[dict, int]:
    """
    Return full detail for one flagged message check, including:
      - message_check fields
      - prediction fields
      - existing fraud_review (if any)

    Uses a single DB connection for all three queries.

    Returns (response_body, http_status).
    """
    conn = get_db()
    try:
        # Fetch message check
        mc_row = query(
            conn,
            f"SELECT * FROM message_checks WHERE id = {PH}",
            (message_check_id,),
        ).fetchone()

        if not mc_row:
            return {"success": False, "errors": ["Message check not found."]}, 404

        mc = dict(mc_row)

        # Fetch prediction (same connection)
        pred_row = query(
            conn,
            f"SELECT * FROM predictions WHERE message_check_id = {PH}",
            (message_check_id,),
        ).fetchone()
        prediction = dict(pred_row) if pred_row else None

        # Fetch existing review (same connection)
        review_row = query(
            conn,
            f"SELECT * FROM fraud_reviews WHERE message_check_id = {PH}",
            (message_check_id,),
        ).fetchone()
        review = dict(review_row) if review_row else None

        return {
            "success": True,
            "data": {
                "message_check": mc,
                "prediction": prediction,
                "review": review,
            },
        }, 200
    except Exception:
        logger.exception("Database error fetching review detail for check_id=%s", message_check_id)
        return {
            "success": False,
            "errors": ["Failed to load review details. Please try again."],
        }, 500
    finally:
        conn.close()


def submit_review(
    message_check_id: int,
    reviewer_id: int,
    reviewer_label: str,
    review_status: str,
    notes: str = None,
) -> tuple[dict, int]:
    """
    Create or update a fraud_review for the given message check.

    Validates inputs, checks the message_check exists and grabs its
    predicted_label in a single connection, then either creates a new
    review or updates the existing one.

    Returns (response_body, http_status).
    """
    # ── Validate inputs ──
    if reviewer_label not in _VALID_REVIEWER_LABELS:
        return {
            "success": False,
            "errors": [f"reviewer_label must be one of: {', '.join(sorted(_VALID_REVIEWER_LABELS))}"],
        }, 400

    if review_status not in _VALID_REVIEW_STATUSES:
        return {
            "success": False,
            "errors": [f"review_status must be one of: {', '.join(sorted(_VALID_REVIEW_STATUSES))}"],
        }, 400

    if notes and len(notes) > _MAX_NOTES_LENGTH:
        return {
            "success": False,
            "errors": [f"notes must not exceed {_MAX_NOTES_LENGTH} characters."],
        }, 400

    # ── Check message_check exists + get predicted_label (single connection) ──
    conn = get_db()
    try:
        mc_row = query(
            conn,
            f"SELECT id FROM message_checks WHERE id = {PH}",
            (message_check_id,),
        ).fetchone()

        if not mc_row:
            return {"success": False, "errors": ["Message check not found."]}, 404

        pred_row = query(
            conn,
            f"SELECT predicted_label FROM predictions WHERE message_check_id = {PH}",
            (message_check_id,),
        ).fetchone()
    finally:
        conn.close()

    predicted_label = pred_row["predicted_label"] if pred_row else "unknown"

    # ── Create or update the review ──
    existing = get_review_by_check_id(message_check_id)

    if existing:
        # Update the existing review
        updated = update_review(
            review_id=existing["id"],
            reviewer_label=reviewer_label,
            review_status=review_status,
            reviewed_by=reviewer_id,
            notes=notes,
        )
        if updated:
            logger.info(
                "Review updated: review_id=%s check_id=%s status=%s by user_id=%s",
                existing["id"], message_check_id, review_status, reviewer_id,
            )
            return {
                "success": True,
                "message": "Review updated successfully.",
                "data": updated,
            }, 200
        else:
            return {"success": False, "errors": ["Failed to update review."]}, 500
    else:
        # Create a new review with all fields in one step
        new_review = create_full_review(
            message_check_id=message_check_id,
            predicted_label=predicted_label,
            reviewer_label=reviewer_label,
            review_status=review_status,
            reviewed_by=reviewer_id,
            notes=notes,
        )
        if new_review:
            logger.info(
                "Review created: review_id=%s check_id=%s status=%s by user_id=%s",
                new_review["id"], message_check_id, review_status, reviewer_id,
            )
            return {
                "success": True,
                "message": "Review created successfully.",
                "data": new_review,
            }, 201
        else:
            return {"success": False, "errors": ["Failed to create review."]}, 500

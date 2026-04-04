"""
MessageCheck model — CRUD helpers for the message_checks table.

This is the core table for the MTN Message Authenticity Detection system.
Each row represents one SMS or screenshot submitted by a user for verification.

Provides:
  create_message_check()         — insert a new submission
  get_message_check_by_id()      — fetch one by primary key
  get_checks_by_user()           — all checks for a user (newest first)
  update_message_check()         — update parsed fields after processing
  get_checks_by_status()         — filter by status (for admin views)
"""

from db import get_db, PH, IntegrityError, insert_returning_id, query, execute


def create_message_check(
    user_id: int,
    source_channel: str,
    wallet_id: int = None,
    raw_text: str = None,
    screenshot_path: str = None,
) -> dict | None:
    """
    Insert a new message check submission.

    Required: user_id, source_channel ('sms' or 'screenshot').
    At least one of raw_text or screenshot_path should be provided.
    Returns the created row as a dict, or None on failure.
    """
    conn = get_db()
    try:
        new_id = insert_returning_id(
            conn,
            f"""
            INSERT INTO message_checks
                (user_id, wallet_id, source_channel, raw_text, screenshot_path)
            VALUES ({PH}, {PH}, {PH}, {PH}, {PH})
            """,
            (user_id, wallet_id, source_channel, raw_text, screenshot_path),
        )
        conn.commit()
        return get_message_check_by_id(new_id)
    except IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_message_check_by_id(check_id: int) -> dict | None:
    """Fetch a single message check by primary key."""
    conn = get_db()
    try:
        row = query(conn, f"SELECT * FROM message_checks WHERE id = {PH}", (check_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_checks_by_user(user_id: int, limit: int = 50) -> list[dict]:
    """Return all message checks for a user, newest first."""
    conn = get_db()
    try:
        rows = query(
            conn,
            f"""
            SELECT * FROM message_checks
            WHERE user_id = {PH}
            ORDER BY created_at DESC
            LIMIT {PH}
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_message_check(check_id: int, **fields) -> dict | None:
    """
    Update one or more fields on a message_check row after parsing.

    Usage:
        update_message_check(42,
            extracted_text="You received 50,000 UGX...",
            amount=50000,
            counterparty_name="John Doe",
            status="parsed",
            parser_confidence=0.92,
        )

    Only columns listed in ALLOWED_FIELDS can be updated.
    Returns the updated row, or None if the check_id doesn't exist.
    """
    ALLOWED_FIELDS = {
        "extracted_text", "mtn_transaction_id", "transaction_reference",
        "transaction_datetime", "transaction_type", "transaction_category",
        "direction", "status", "counterparty_name", "counterparty_number",
        "amount", "fee", "tax", "total_amount", "currency",
        "balance_before", "balance_after", "available_balance",
        "provider", "parser_confidence",
    }

    # Filter to only allowed fields that have values
    updates = {k: v for k, v in fields.items() if k in ALLOWED_FIELDS}
    if not updates:
        return get_message_check_by_id(check_id)

    set_clause = ", ".join(f"{col} = {PH}" for col in updates)
    values = list(updates.values()) + [check_id]

    conn = get_db()
    try:
        execute(
            conn,
            f"UPDATE message_checks SET {set_clause} WHERE id = {PH}",
            values,
        )
        conn.commit()
        return get_message_check_by_id(check_id)
    finally:
        conn.close()


def get_checks_by_status(status: str, limit: int = 100) -> list[dict]:
    """Return message checks filtered by status (useful for admin review queue)."""
    conn = get_db()
    try:
        rows = query(
            conn,
            f"""
            SELECT mc.*, u.full_name, u.email
            FROM message_checks mc
            JOIN users u ON mc.user_id = u.id
            WHERE mc.status = {PH}
            ORDER BY mc.created_at DESC
            LIMIT {PH}
            """,
            (status, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

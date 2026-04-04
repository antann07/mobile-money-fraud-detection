"""Password reset token model — CRUD for the password_reset_tokens table."""

from db import get_db, PH, insert_returning_id, query, execute, is_pg


def create_reset_token(user_id: int, token_hash: str, expires_at: str) -> int | None:
    """Store a hashed reset token. Returns the new row id."""
    conn = get_db()
    try:
        new_id = insert_returning_id(
            conn,
            f"""
            INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
            VALUES ({PH}, {PH}, {PH})
            """,
            (user_id, token_hash, expires_at),
        )
        conn.commit()
        return new_id
    finally:
        conn.close()


def get_valid_tokens_for_user(user_id: int) -> list[dict]:
    """Return all unused tokens for a user (expiry filtering is done in the service layer)."""
    conn = get_db()
    try:
        rows = query(
            conn,
            f"SELECT * FROM password_reset_tokens WHERE user_id = {PH} AND used = 0",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_token_used(token_id: int) -> None:
    """Flag a token as used so it can't be reused."""
    conn = get_db()
    try:
        execute(conn, f"UPDATE password_reset_tokens SET used = 1 WHERE id = {PH}", (token_id,))
        conn.commit()
    finally:
        conn.close()


def invalidate_all_tokens(user_id: int) -> None:
    """Mark all tokens for a user as used (e.g. after successful reset)."""
    conn = get_db()
    try:
        execute(conn, f"UPDATE password_reset_tokens SET used = 1 WHERE user_id = {PH}", (user_id,))
        conn.commit()
    finally:
        conn.close()


def delete_expired_tokens() -> int:
    """Hard-delete tokens that are past their expiry date. Returns the number of rows removed.

    Call this from a scheduled job (e.g. daily) to keep the table small.
    The service layer rejects expired tokens regardless, so this is a
    housekeeping-only operation — safe to skip if no scheduler is configured.
    """
    conn = get_db()
    try:
        # ISO-format UTC strings sort lexicographically, so a plain string
        # comparison against datetime('now') works correctly for SQLite.
        # PostgreSQL: NOW() is used instead.
        if is_pg():
            cur = execute(conn, "DELETE FROM password_reset_tokens WHERE expires_at < NOW()", ())
        else:
            cur = execute(
                conn,
                "DELETE FROM password_reset_tokens WHERE expires_at < datetime('now')",
                (),
            )
        conn.commit()
        return cur.rowcount if hasattr(cur, "rowcount") else 0
    finally:
        conn.close()

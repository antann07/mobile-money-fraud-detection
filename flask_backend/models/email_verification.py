"""Email verification token model — CRUD for the email_verification_tokens table."""

from db import get_db, PH, insert_returning_id, query, execute


def create_verification_token(user_id: int, token_hash: str, expires_at: str) -> int | None:
    """Store a hashed verification token. Returns the new row id."""
    conn = get_db()
    try:
        new_id = insert_returning_id(
            conn,
            f"""
            INSERT INTO email_verification_tokens (user_id, token_hash, expires_at)
            VALUES ({PH}, {PH}, {PH})
            """,
            (user_id, token_hash, expires_at),
        )
        conn.commit()
        return new_id
    finally:
        conn.close()


def get_valid_verification_tokens(user_id: int) -> list[dict]:
    """Return all unused verification tokens for a user."""
    conn = get_db()
    try:
        rows = query(
            conn,
            f"SELECT * FROM email_verification_tokens WHERE user_id = {PH} AND used = 0",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def invalidate_all_verification_tokens(user_id: int) -> None:
    """Mark all verification tokens for a user as used."""
    conn = get_db()
    try:
        execute(
            conn,
            f"UPDATE email_verification_tokens SET used = 1 WHERE user_id = {PH}",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()

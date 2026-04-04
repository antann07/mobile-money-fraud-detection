"""Wallet model – CRUD helpers for the wallets table."""

from db import get_db, PH, IntegrityError, insert_returning_id, query, execute


def create_wallet(user_id: int, wallet_number: str, provider: str,
                  wallet_name: str, is_primary: bool = False) -> dict | None:
    """Insert a new wallet and return the created row.
    Returns None if the wallet_number+provider already exists."""
    conn = get_db()
    try:
        # If this wallet should be primary, unset any existing primary first
        if is_primary:
            execute(
                conn,
                f"UPDATE wallets SET is_primary = 0 WHERE user_id = {PH} AND is_primary = 1",
                (user_id,),
            )
        new_id = insert_returning_id(
            conn,
            f"""
            INSERT INTO wallets (user_id, wallet_number, provider, wallet_name, is_primary)
            VALUES ({PH}, {PH}, {PH}, {PH}, {PH})
            """,
            (user_id, wallet_number, provider, wallet_name, int(is_primary)),
        )
        conn.commit()
        return get_wallet_by_id(new_id)
    except IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_wallet_by_id(wallet_id: int) -> dict | None:
    """Fetch a single wallet by primary key."""
    conn = get_db()
    try:
        row = query(conn, f"SELECT * FROM wallets WHERE id = {PH}", (wallet_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_wallets_by_user(user_id: int) -> list[dict]:
    """Return all wallets belonging to a user."""
    conn = get_db()
    try:
        rows = query(
            conn,
            f"SELECT * FROM wallets WHERE user_id = {PH} ORDER BY is_primary DESC, created_at",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def wallet_exists(wallet_number: str, provider: str) -> bool:
    """Check if a wallet with the same number + provider already exists."""
    conn = get_db()
    try:
        row = query(
            conn,
            f"SELECT 1 FROM wallets WHERE wallet_number = {PH} AND provider = {PH}",
            (wallet_number, provider),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def delete_wallet(wallet_id: int, user_id: int) -> bool:
    """Delete a wallet owned by user_id. Returns True if a row was deleted."""
    conn = get_db()
    try:
        cursor = execute(
            conn,
            f"DELETE FROM wallets WHERE id = {PH} AND user_id = {PH}",
            (wallet_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def set_wallet_primary(wallet_id: int, user_id: int) -> bool:
    """Set the given wallet as primary for user_id, clearing any previous primary.
    Returns True if updated, False if the wallet_id doesn't belong to user_id."""
    conn = get_db()
    try:
        row = query(
            conn,
            f"SELECT id FROM wallets WHERE id = {PH} AND user_id = {PH}",
            (wallet_id, user_id),
        ).fetchone()
        if not row:
            return False
        execute(conn, f"UPDATE wallets SET is_primary = 0 WHERE user_id = {PH} AND is_primary = 1", (user_id,))
        execute(conn, f"UPDATE wallets SET is_primary = 1 WHERE id = {PH}", (wallet_id,))
        conn.commit()
        return True
    finally:
        conn.close()

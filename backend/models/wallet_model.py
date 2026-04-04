"""Wallet model – CRUD helpers for the wallets table."""

import sqlite3
from db import get_db


def create_wallet(user_id: int, wallet_number: str, provider: str,
                  wallet_name: str, is_primary: bool = False) -> dict | None:
    """Insert a new wallet and return the created row.
    Returns None on UNIQUE constraint violation."""
    conn = get_db()
    try:
        # If this wallet should be primary, unset any existing primary first
        if is_primary:
            conn.execute(
                "UPDATE wallets SET is_primary = 0 WHERE user_id = ? AND is_primary = 1",
                (user_id,),
            )
        cursor = conn.execute(
            """
            INSERT INTO wallets (user_id, wallet_number, provider, wallet_name, is_primary)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, wallet_number, provider, wallet_name, int(is_primary)),
        )
        conn.commit()
        # Fetch the new row using the same connection
        row = conn.execute(
            "SELECT * FROM wallets WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_wallet_by_id(wallet_id: int) -> dict | None:
    """Fetch a single wallet by primary key."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_wallets_by_user(user_id: int) -> list[dict]:
    """Return all wallets belonging to a user."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM wallets WHERE user_id = ? ORDER BY is_primary DESC, created_at",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def wallet_exists(user_id: int, wallet_number: str) -> bool:
    """Check if the user already has a wallet with this number."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT 1 FROM wallets WHERE user_id = ? AND wallet_number = ?",
            (user_id, wallet_number),
        ).fetchone()
        return row is not None
    finally:
        conn.close()

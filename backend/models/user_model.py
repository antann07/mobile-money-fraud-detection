"""User model – CRUD helpers for the users table."""

import sqlite3
from db import get_db


def create_user(full_name: str, email: str, phone_number: str,
                password_hash: str, role: str = "customer") -> dict | None:
    """Insert a new user and return the created row as a dict.
    Returns None if the email already exists (UNIQUE constraint)."""
    conn = get_db()
    try:
        cursor = conn.execute(
            """
            INSERT INTO users (full_name, email, phone_number, password_hash, role)
            VALUES (?, ?, ?, ?, ?)
            """,
            (full_name, email, phone_number, password_hash, role),
        )
        conn.commit()
        # Fetch the new row using the same connection
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    """Fetch a single user by primary key."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    """Fetch a single user by email address."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

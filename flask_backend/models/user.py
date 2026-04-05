"""User model – CRUD helpers for the users table."""

from db import get_db, PH, IntegrityError, insert_returning_id, query, execute


def create_user(full_name: str, email: str, phone_number: str,
                password_hash: str, role: str = "customer",
                username: str | None = None) -> dict | None:
    """Insert a new user and return the created row as a dict.
    Returns None if the email/username already exists (UNIQUE constraint)."""
    conn = get_db()
    try:
        new_id = insert_returning_id(
            conn,
            f"""
            INSERT INTO users (full_name, username, email, phone_number, password_hash, role)
            VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH})
            """,
            (full_name, username, email, phone_number, password_hash, role),
        )
        conn.commit()
        return get_user_by_id(new_id)
    except IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    """Fetch a single user by primary key."""
    conn = get_db()
    try:
        row = query(conn, f"SELECT * FROM users WHERE id = {PH}", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    """Fetch a single user by email address."""
    conn = get_db()
    try:
        row = query(conn, f"SELECT * FROM users WHERE email = {PH}", (email,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_username(username: str) -> dict | None:
    """Fetch a single user by username."""
    conn = get_db()
    try:
        row = query(conn, f"SELECT * FROM users WHERE username = {PH}", (username,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_email_or_username(identifier: str) -> dict | None:
    """Fetch a user by email or username (for flexible login)."""
    conn = get_db()
    try:
        row = query(
            conn,
            f"SELECT * FROM users WHERE email = {PH} OR username = {PH}",
            (identifier, identifier),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def increment_failed_logins(user_id: int) -> None:
    """Bump failed_login_attempts by 1."""
    conn = get_db()
    try:
        execute(conn, f"UPDATE users SET failed_login_attempts = failed_login_attempts + 1 WHERE id = {PH}", (user_id,))
        conn.commit()
    finally:
        conn.close()


def lock_account(user_id: int, until: str) -> None:
    """Set locked_until timestamp on the user."""
    conn = get_db()
    try:
        execute(conn, f"UPDATE users SET locked_until = {PH}, failed_login_attempts = 0 WHERE id = {PH}", (until, user_id))
        conn.commit()
    finally:
        conn.close()


def reset_failed_logins(user_id: int) -> None:
    """Clear failed login counter after successful login."""
    conn = get_db()
    try:
        execute(conn, f"UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE id = {PH}", (user_id,))
        conn.commit()
    finally:
        conn.close()


def update_password(user_id: int, password_hash: str) -> None:
    """Update a user's password hash (for reset flow)."""
    conn = get_db()
    try:
        execute(conn, f"UPDATE users SET password_hash = {PH} WHERE id = {PH}", (password_hash, user_id))
        conn.commit()
    finally:
        conn.close()


def set_email_verified(user_id: int) -> None:
    """Mark user's email as verified."""
    conn = get_db()
    try:
        execute(conn, f"UPDATE users SET email_verified = 1 WHERE id = {PH}", (user_id,))
        conn.commit()
    finally:
        conn.close()

"""Migration: add username, lockout columns to users + password_reset_tokens table.

Run once: python migrate_auth_upgrade.py
Safe to re-run — uses IF NOT EXISTS / try-except for idempotency.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from db import get_db, is_pg, query

def migrate():
    conn = get_db()
    cur = conn.cursor()

    if is_pg():
        # PostgreSQL: ADD COLUMN IF NOT EXISTS
        stmts = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT UNIQUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP",
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                token_hash TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ]
        for sql in stmts:
            cur.execute(sql)
    else:
        # SQLite: ALTER TABLE can't add UNIQUE columns — add without constraint
        # then enforce uniqueness via a partial index (NULL rows excluded).
        alter_stmts = [
            "ALTER TABLE users ADD COLUMN username TEXT",
            "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN locked_until TIMESTAMP",
        ]
        for sql in alter_stmts:
            try:
                cur.execute(sql)
            except Exception as e:
                msg = str(e).lower()
                if "duplicate column" in msg or "already exists" in msg:
                    pass
                else:
                    raise

        # Unique index replaces the UNIQUE column constraint for SQLite
        try:
            cur.execute(
                "CREATE UNIQUE INDEX idx_users_username ON users (username) "
                "WHERE username IS NOT NULL"
            )
        except Exception as e:
            if "already exists" in str(e).lower():
                pass
            else:
                raise

        cur.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

    conn.commit()
    conn.close()
    print("Migration complete: auth upgrade applied.")


if __name__ == "__main__":
    migrate()

"""Database migration — add email verification support.

Adds:
  - email_verified column to users table (default 0)
  - email_verification_tokens table

Safe to run multiple times (uses IF NOT EXISTS / catches errors).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from db import get_db, is_pg

def migrate():
    conn = get_db()
    cur = conn.cursor()

    # Add email_verified column to users table
    try:
        if is_pg():
            cur.execute("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS
                email_verified BOOLEAN NOT NULL DEFAULT FALSE
            """)
        else:
            cur.execute("""
                ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0
            """)
        print("[OK] Added email_verified column to users table")
    except Exception as e:
        if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
            print("[SKIP] email_verified column already exists")
        else:
            print(f"[WARN] Could not add email_verified column: {e}")

    # Create email_verification_tokens table
    if is_pg():
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_verification_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                token_hash TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_verification_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
    print("[OK] Created email_verification_tokens table")

    conn.commit()
    conn.close()
    print("[DONE] Email verification migration complete")


if __name__ == "__main__":
    migrate()

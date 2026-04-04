"""
Database migration: bring existing tables in line with schema.sql

Fixes:
  message_checks:
    - Rename transaction_id → mtn_transaction_id
    - Add currency column (TEXT DEFAULT 'GHS')

  predictions:
    - Add model_version column (TEXT DEFAULT 'v1')

  user_behavior_profiles:
    - Add total_checks_count column (INTEGER DEFAULT 0)
    - Add created_at column (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

Safe to run multiple times — every ALTER is wrapped in try/except.
"""
import sqlite3
import sys
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "fraud_detection.db")


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    migrations = [
        # ── message_checks ──
        (
            "Rename message_checks.transaction_id → mtn_transaction_id",
            "ALTER TABLE message_checks RENAME COLUMN transaction_id TO mtn_transaction_id",
        ),
        (
            "Add message_checks.currency",
            "ALTER TABLE message_checks ADD COLUMN currency TEXT DEFAULT 'GHS'",
        ),

        # ── predictions ──
        (
            "Add predictions.model_version",
            "ALTER TABLE predictions ADD COLUMN model_version TEXT DEFAULT 'v1'",
        ),

        # ── user_behavior_profiles ──
        (
            "Add user_behavior_profiles.total_checks_count",
            "ALTER TABLE user_behavior_profiles ADD COLUMN total_checks_count INTEGER DEFAULT 0",
        ),
        (
            "Add user_behavior_profiles.created_at",
            "ALTER TABLE user_behavior_profiles ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        ),
    ]

    print(f"Migrating database: {DB_PATH}\n")

    for description, sql in migrations:
        try:
            cursor.execute(sql)
            conn.commit()
            print(f"  OK  {description}")
        except sqlite3.OperationalError as e:
            # "duplicate column name" or "no such column" means already done
            print(f"  SKIP {description} ({e})")

    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()

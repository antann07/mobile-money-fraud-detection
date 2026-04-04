"""
Database connection and initialization module.

Uses SQLite for development. Switch DATABASE_URL in config.py
to PostgreSQL for production.
"""

import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "fraud_detection.db")


def get_db():
    """
    Create and return a new database connection.
    Enables foreign key support and returns rows as dictionaries.
    """
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row          # access columns by name
    conn.execute("PRAGMA foreign_keys = ON")  # enforce FK constraints
    return conn


def init_db():
    """
    Run schema.sql to create tables if they don't exist.
    Called once on application startup.
    """
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    conn = get_db()
    try:
        with open(schema_path, "r") as f:
            conn.executescript(f.read())
        conn.commit()
        logger.info("Database initialized successfully.")
    finally:
        conn.close()


def close_db(conn):
    """Close a database connection."""
    if conn:
        conn.close()

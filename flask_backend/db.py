"""
Database connection and initialization module.

Supports two backends:
  • SQLite   – default for local development (DATABASE_URL is a file path)
  • PostgreSQL – production (DATABASE_URL starts with postgresql:// or postgres://)

All model code should use the helpers exported here instead of importing
sqlite3 or psycopg2 directly:
  get_db()          – returns a connection (dict-row factory enabled)
  init_db()         – runs the appropriate schema file on startup
  close_db(conn)    – safely close a connection
  PH                – placeholder string: '?' for SQLite, '%s' for PostgreSQL
  IntegrityError    – the right exception class for the active backend
  is_pg()           – True when using PostgreSQL
  insert_returning_id(conn, sql, params, *, table)
                    – execute an INSERT and return the new row id
  check_db_health() – quick connectivity test for health endpoints
"""

import os
import sqlite3
import logging
from config import get_config

logger = logging.getLogger(__name__)

_cfg = get_config()

# ── Detect backend from DATABASE_URL ─────────────────────────────────
_USE_PG = _cfg.DATABASE_URL.startswith(("postgresql://", "postgres://"))

if _USE_PG:
    import psycopg2
    import psycopg2.extras          # RealDictCursor

# ── Public helpers ───────────────────────────────────────────────────
PH = "%s" if _USE_PG else "?"       # parameter placeholder


def is_pg() -> bool:
    """Return True when the active backend is PostgreSQL."""
    return _USE_PG


# Re-export the correct IntegrityError so models can catch it
IntegrityError: type = psycopg2.IntegrityError if _USE_PG else sqlite3.IntegrityError


# ── Connection ───────────────────────────────────────────────────────
def get_db():
    """
    Create and return a new database connection.
    • SQLite  – Row factory, PRAGMA foreign_keys = ON
    • PostgreSQL – RealDictCursor, autocommit OFF (default)

    Raises a clear error if the connection fails.
    """
    try:
        if _USE_PG:
            conn = psycopg2.connect(_cfg.DATABASE_URL, connect_timeout=5)
            return conn

        # SQLite path
        conn = sqlite3.connect(_cfg.DATABASE_URL, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except Exception as e:
        logger.error("Database connection failed: %s", e)
        raise


# ── INSERT helper (lastrowid vs RETURNING) ───────────────────────────
def insert_returning_id(conn, sql: str, params: tuple) -> int | None:
    """
    Execute an INSERT and return the new row's id.

    • SQLite  – uses cursor.lastrowid
    • PostgreSQL – appends RETURNING id to the SQL

    The *sql* must NOT already include a RETURNING clause.
    """
    if _USE_PG:
        sql = sql.rstrip().rstrip(";") + " RETURNING id"
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        row = cur.fetchone()
        return row["id"] if row else None

    cursor = conn.execute(sql, params)
    return cursor.lastrowid


# ── Schema initialization ────────────────────────────────────────────
def init_db():
    """
    Run the correct schema file to create tables if they don't exist.
    • SQLite     – schema.sql   (uses executescript)
    • PostgreSQL – schema_pg.sql (uses cursor.execute)
    """
    if _USE_PG:
        schema_path = os.path.join(os.path.dirname(__file__), "schema_pg.sql")
    else:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    conn = get_db()
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()

        if _USE_PG:
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            logger.info("Database initialized successfully (PostgreSQL)")
        else:
            conn.executescript(sql)
            conn.commit()
            logger.info("Database initialized successfully (SQLite: %s)", _cfg.DATABASE_URL)
    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        raise
    finally:
        conn.close()


def query(conn, sql: str, params: tuple = ()):
    """
    Execute *sql* with *params* and return a cursor-like object
    supporting .fetchone() and .fetchall().

    • SQLite     – conn.execute() returns a Cursor (rows as sqlite3.Row)
    • PostgreSQL – uses RealDictCursor so rows come back as dicts
    """
    try:
        if _USE_PG:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params)
            return cur
        return conn.execute(sql, params)
    except Exception as e:
        # Log with enough context to diagnose, but truncate SQL to avoid log bloat
        sql_preview = (sql.strip()[:120] + "...") if len(sql.strip()) > 120 else sql.strip()
        logger.error("DB query failed: %s | sql=%s", e, sql_preview)
        raise


def execute(conn, sql: str, params: tuple = ()):
    """
    Execute a non-returning statement (UPDATE / DELETE).
    Same as query() but makes intent clearer in model code.
    """
    return query(conn, sql, params)


def close_db(conn):
    """Close a database connection safely."""
    if conn:
        try:
            conn.close()
        except Exception as e:
            logger.debug("close_db: ignoring error on close: %s", e)


def check_db_health() -> bool:
    """
    Quick connectivity check for health endpoints.
    Returns True if a simple query succeeds, False otherwise.
    """
    try:
        conn = get_db()
        if _USE_PG:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
        else:
            conn.execute("SELECT 1")
        close_db(conn)
        return True
    except Exception as e:
        logger.warning("DB health check failed: %s", e)
        return False

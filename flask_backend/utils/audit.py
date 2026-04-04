"""
Audit logger — records important user actions for accountability.

Logs are written to:
  1. The console (via Python logging)
  2. A dedicated audit log file: flask_backend/logs/audit.log

Each audit entry includes:
  - timestamp
  - action (e.g. LOGIN, REGISTER, WALLET_ADD, TRANSACTION_ADD)
  - user_id (if known)
  - IP address
  - extra details

Usage:
    from utils.audit import audit_log
    audit_log("LOGIN", user_id=42, detail="email=user@example.com")
"""

import logging
import os
from datetime import datetime, timezone
from flask import request

# ── Create logs directory if missing ─────────────────────────────────
_log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(_log_dir, exist_ok=True)

# ── Configure a dedicated audit logger ───────────────────────────────
audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False  # don't duplicate into root logger

# File handler — append mode, one line per event
_file_handler = logging.FileHandler(
    os.path.join(_log_dir, "audit.log"), encoding="utf-8"
)
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
audit_logger.addHandler(_file_handler)

# Console handler — so devs see audit events during development
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(
    logging.Formatter("[AUDIT] %(message)s")
)
audit_logger.addHandler(_console_handler)


def audit_log(action: str, user_id: int | None = None, detail: str = "") -> None:
    """
    Write one audit entry.

    Parameters
    ----------
    action : str
        Short action name (e.g. LOGIN, REGISTER, WALLET_ADD, TRANSACTION_ADD).
    user_id : int | None
        The authenticated user's ID, or None for anonymous actions.
    detail : str
        Freeform extra info (keep it short, no sensitive data).
    """
    ip = _safe_ip()
    rid = _safe_request_id()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parts = [
        f"action={action}",
        f"user_id={user_id or 'anon'}",
        f"ip={ip}",
        f"rid={rid}",
        f"time={ts}",
    ]
    if detail:
        parts.append(f"detail={detail}")

    audit_logger.info(" | ".join(parts))


def _safe_ip() -> str:
    """Get the client IP from the Flask request context, or 'unknown'."""
    try:
        return request.remote_addr or "unknown"
    except RuntimeError:
        return "unknown"


def _safe_request_id() -> str:
    """Get the request ID from Flask g, or '-' if not in a request."""
    try:
        from flask import g
        return getattr(g, "request_id", "-")
    except RuntimeError:
        return "-"

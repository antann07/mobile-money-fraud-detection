"""
Request context middleware — assigns a unique request ID to every request.

Why this matters in production:
  - Every log line includes the request ID, so you can trace a single
    user request across all log entries (route → service → model → DB).
  - When a user reports "something went wrong", support can search logs
    by the request ID returned in the response header.

The request ID is:
  1. Read from X-Request-ID header (if a load balancer sets it), OR
  2. Generated as a short UUID.
  3. Stored in Flask's `g` object for the request lifetime.
  4. Injected into Python's logging via a filter.
  5. Returned in the X-Request-ID response header.
"""

import uuid
import logging
from flask import g, request


class RequestIDFilter(logging.Filter):
    """Inject request_id into every log record."""

    def filter(self, record):
        try:
            record.request_id = getattr(g, "request_id", "-")
        except RuntimeError:
            # Outside request context (e.g. during startup) — safe fallback
            record.request_id = "-"
        return True


def init_request_context(app):
    """Attach before/after hooks that manage the request ID lifecycle."""

    @app.before_request
    def _set_request_id():
        # Prefer an upstream-provided ID (e.g. from Nginx or a load balancer)
        rid = request.headers.get("X-Request-ID", "").strip()
        if not rid:
            rid = uuid.uuid4().hex[:12]
        g.request_id = rid

    @app.after_request
    def _echo_request_id(response):
        rid = getattr(g, "request_id", None)
        if rid:
            response.headers["X-Request-ID"] = rid
        return response

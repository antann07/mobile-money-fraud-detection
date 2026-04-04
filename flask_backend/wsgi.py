"""
WSGI entrypoint — used by Gunicorn (and any WSGI server) in production.

Usage:
  Development:  python app.py                        (uses Flask dev server)
  Production:   gunicorn wsgi:application             (uses Gunicorn)
  With options: gunicorn -w 4 -b 0.0.0.0:5001 wsgi:application

This file simply calls the app factory and exposes the result as `application`.
Gunicorn looks for a callable named `application` (or `app`) at the module level.
"""

import logging
from app import create_app

logger = logging.getLogger(__name__)

# Gunicorn expects a module-level WSGI callable.
# The variable MUST be called `application` (WSGI standard) or `app`.
application = create_app()

logger.info("WSGI application ready — PID %d", __import__("os").getpid())

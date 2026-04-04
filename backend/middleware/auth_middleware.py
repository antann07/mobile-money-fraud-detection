"""JWT authentication middleware."""

import logging
from functools import wraps
import jwt as pyjwt
from flask import request, jsonify
from services.auth_service import decode_token

logger = logging.getLogger(__name__)


def token_required(f):
    """
    Decorator that protects a route with JWT authentication.

    Usage:
        @app.route("/protected")
        @token_required
        def protected(current_user):
            ...

    The decoded token payload is passed as `current_user` dict with
    keys: user_id, role, exp, iat.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            logger.warning("Missing/malformed auth header: %s %s from %s", request.method, request.path, request.remote_addr)
            return jsonify({"success": False, "errors": ["Missing or malformed Authorization header."]}), 401

        token = auth_header.split(" ", 1)[1].strip()

        try:
            payload = decode_token(token)
        except pyjwt.ExpiredSignatureError:
            logger.warning("Expired token: %s %s from %s", request.method, request.path, request.remote_addr)
            return jsonify({"success": False, "errors": ["Token has expired. Please login again."]}), 401
        except pyjwt.InvalidTokenError:
            logger.warning("Invalid token: %s %s from %s", request.method, request.path, request.remote_addr)
            return jsonify({"success": False, "errors": ["Token is invalid."]}), 401

        return f(payload, *args, **kwargs)

    return decorated


def admin_required(f):
    """
    Decorator that requires the authenticated user to have the 'admin' role.
    Must be used AFTER @token_required.
    """

    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.get("role") != "admin":
            logger.warning("Admin access denied: user_id=%s path=%s", current_user.get("user_id"), request.path)
            return jsonify({"success": False, "errors": ["Admin access required."]}), 403
        return f(current_user, *args, **kwargs)

    return decorated

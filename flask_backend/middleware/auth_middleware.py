"""
JWT authentication middleware.

How token verification works:
  1. The frontend sends:  Authorization: Bearer <token>
  2. token_required() extracts the token after "Bearer ".
  3. auth_service.decode_token() verifies the token against
     the SECRET_KEY from config (loaded via get_config()).
  4. If valid → the decoded payload (user_id, role, exp, iat)
     is passed to the route handler as `current_user`.
  5. If expired → returns 401 with {"errors": ["Token has expired..."]}.
  6. If invalid → returns 401 with {"errors": ["Token is invalid."]}.
  7. If missing → returns 401 with {"errors": ["Missing or malformed..."]}.

Decorator stack order:
  @bp.route("/admin-only")
  @token_required          ← always first — verifies JWT and injects current_user
  @admin_required          ← (or @role_required("admin")) — role check
  def handler(current_user): ...

Response codes:
  401 — missing, expired, or invalid token (frontend should redirect to login)
  403 — valid token but insufficient permissions (e.g. not admin)

Extensibility:
  To add future roles (analyst, reviewer) use role_required:
    @token_required
    @role_required("admin", "analyst")
    def analyst_or_admin(current_user): ...
"""

import logging
from functools import wraps
import jwt as pyjwt
from flask import request, jsonify
from services.auth_service import decode_token

logger = logging.getLogger(__name__)

# Lazy import to avoid circular deps at import time; only used for denied-role audit events.
def _audit(action, user_id, detail):
    try:
        from utils.audit import audit_log
        audit_log(action, user_id=user_id, detail=detail)
    except Exception:
        pass  # never let audit failure break a request


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

        token = auth_header.split(" ", 1)[1]

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


def role_required(*allowed_roles):
    """
    Decorator factory that restricts a route to users whose role is in `allowed_roles`.
    Must be used AFTER @token_required.

    Extensible — accepts one or more role strings:
        @token_required
        @role_required("admin")               # single role
        @role_required("admin", "analyst")    # multiple roles (OR logic)
        def handler(current_user): ...

    On denial: logs a ROLE_DENIED audit event and returns 403.
    """
    allowed = frozenset(allowed_roles)

    def decorator(f):
        @wraps(f)
        def decorated(current_user, *args, **kwargs):
            user_role = current_user.get("role", "")
            if user_role not in allowed:
                logger.warning(
                    "Role denied: user_id=%s role=%s required=%s path=%s",
                    current_user.get("user_id"), user_role,
                    sorted(allowed), request.path,
                )
                _audit(
                    "ROLE_DENIED",
                    user_id=current_user.get("user_id"),
                    detail=f"role={user_role} required={sorted(allowed)} path={request.path}",
                )
                return jsonify({"success": False, "errors": ["You do not have permission to perform this action."]}), 403
            return f(current_user, *args, **kwargs)
        return decorated
    return decorator


def admin_required(f):
    """
    Convenience decorator: restricts a route to admin users only.
    Equivalent to @role_required("admin"). Must be used AFTER @token_required.

    Keeping this as a named export makes existing route files zero-change.
    """
    return role_required("admin")(f)

    return decorated

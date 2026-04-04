"""Authentication routes – register, login, password reset."""

import logging
from flask import Blueprint, request, jsonify
from services.auth_service import (
    register_user, login_user, generate_token,
    request_password_reset, reset_password,
)
from middleware.auth_middleware import token_required
from models.user import get_user_by_id
from utils.audit import audit_log

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "errors": ["Request body must be JSON."]}), 400

    email = data.get("email", "<missing>")
    logger.info("Register attempt for email=%s from %s", email, request.remote_addr)

    # Service call isolated — an exception here returns the error response immediately.
    try:
        body, status = register_user(data)
    except Exception:
        logger.exception("Registration error for email=%s", email)
        return jsonify({"success": False, "errors": ["Registration failed. Please try again."]}), 500

    # Audit log is separate — a logging failure must never hide a successful registration.
    try:
        if status == 201:
            audit_log("REGISTER", user_id=body.get("user", {}).get("id"), detail=f"email={email}")
    except Exception:
        logger.exception("Audit log failed after register for email=%s", email)

    return jsonify(body), status


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "errors": ["Request body must be JSON."]}), 400

    identifier = (data.get("email") or data.get("username") or "<missing>").strip()
    logger.info("Login attempt for identifier=%s from %s", identifier, request.remote_addr)

    # Service call isolated — an exception here returns the error response immediately.
    try:
        body, status = login_user(data)
    except Exception:
        logger.exception("Login error for identifier=%s", identifier)
        return jsonify({"success": False, "errors": ["Login failed. Please try again."]}), 500

    # Audit log is separate — a logging failure must never hide a successful login.
    try:
        if status == 200:
            audit_log("LOGIN", user_id=body.get("user", {}).get("id"), detail=f"identifier={identifier}")
        else:
            audit_log("LOGIN_FAILED", detail=f"identifier={identifier} status={status}")
    except Exception:
        logger.exception("Audit log failed after login for identifier=%s", identifier)

    return jsonify(body), status


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "errors": ["Request body must be JSON."]}), 400

    email = (data.get("email") or "").strip()
    if not email:
        return jsonify({"success": False, "errors": ["Email is required."]}), 400

    logger.info("Password reset requested for email=%s from %s", email, request.remote_addr)

    # Service call isolated.
    try:
        body, status = request_password_reset(email)
    except Exception:
        logger.exception("Password reset request error for email=%s", email)
        return jsonify({"success": False, "errors": ["Request failed. Please try again."]}), 500

    # Audit log separate.
    try:
        audit_log("PASSWORD_RESET_REQUEST", detail=f"email={email}")
    except Exception:
        logger.exception("Audit log failed after forgot-password for email=%s", email)

    return jsonify(body), status


@auth_bp.route("/reset-password", methods=["POST"])
def do_reset_password():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "errors": ["Request body must be JSON."]}), 400

    email = (data.get("email") or "").strip()
    # Strip whitespace from token — prevents copy-paste leading/trailing spaces
    # from breaking the bcrypt comparison.
    token = (data.get("token") or "").strip()
    new_password = data.get("new_password", "")

    if not email or not token or not new_password:
        return jsonify({"success": False, "errors": ["Email, token, and new_password are required."]}), 400

    logger.info("Password reset attempt for email=%s from %s", email, request.remote_addr)

    # Service call isolated.
    try:
        body, status = reset_password(email, token, new_password)
    except Exception:
        logger.exception("Password reset error for email=%s", email)
        return jsonify({
            "success": False,
            "errors": ["This reset link is invalid or has expired. Please request a new one."],
        }), 500

    # Audit log separate.
    try:
        if status == 200:
            audit_log("PASSWORD_RESET_SUCCESS", detail=f"email={email}")
        else:
            audit_log("PASSWORD_RESET_FAILED", detail=f"email={email}")
    except Exception:
        logger.exception("Audit log failed after reset-password for email=%s", email)

    return jsonify(body), status


@auth_bp.route("/me", methods=["GET"])
@token_required
def me(current_user):
    user = get_user_by_id(current_user["user_id"])
    if not user:
        return jsonify({"success": False, "errors": ["User not found."]}), 404

    user.pop("password_hash", None)
    user.pop("failed_login_attempts", None)
    user.pop("locked_until", None)
    return jsonify({
        "success": True,
        "token_role": current_user.get("role"),
        "db_role": user.get("role"),
        "user": user,
    }), 200


@auth_bp.route("/refresh", methods=["POST"])
@token_required
def refresh(current_user):
    user = get_user_by_id(current_user["user_id"])
    if not user:
        return jsonify({"success": False, "errors": ["User not found."]}), 404

    token = generate_token(user["id"], user["role"])
    user.pop("password_hash", None)
    user.pop("failed_login_attempts", None)
    user.pop("locked_until", None)
    return jsonify({
        "success": True,
        "token": token,
        "user": user,
    }), 200

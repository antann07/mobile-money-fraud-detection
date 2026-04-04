"""Authentication routes – register & login."""

import logging
from flask import Blueprint, request, jsonify
from services.auth_service import register_user, login_user

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    """
    POST /api/auth/register
    Body: { full_name, email, phone_number, password, role? }
    """
    data = request.get_json(silent=True)
    if not data:
        logger.warning("Register attempt with non-JSON body from %s", request.remote_addr)
        return jsonify({"success": False, "errors": ["Request body must be JSON."]}), 400

    email = data.get("email", "<missing>")
    logger.info("Register attempt for email=%s from %s", email, request.remote_addr)

    try:
        body, status = register_user(data)
        if status == 201:
            logger.info("Registration successful: email=%s", email)
        else:
            logger.warning("Registration rejected: email=%s status=%s errors=%s", email, status, body.get("errors"))
        return jsonify(body), status
    except Exception:
        logger.exception("Registration error for email=%s", email)
        return jsonify({"success": False, "errors": ["Registration failed. Please try again."]}), 500


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    POST /api/auth/login
    Body: { email, password }
    """
    data = request.get_json(silent=True)
    if not data:
        logger.warning("Login attempt with non-JSON body from %s", request.remote_addr)
        return jsonify({"success": False, "errors": ["Request body must be JSON."]}), 400

    email = data.get("email", "<missing>")
    logger.info("Login attempt for email=%s from %s", email, request.remote_addr)

    try:
        body, status = login_user(data)
        if status == 200:
            logger.info("Login successful: email=%s", email)
        else:
            logger.warning("Login failed: email=%s status=%s", email, status)
        return jsonify(body), status
    except Exception:
        logger.exception("Login error for email=%s", email)
        return jsonify({"success": False, "errors": ["Login failed. Please try again."]}), 500

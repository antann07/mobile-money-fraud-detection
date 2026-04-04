"""Wallet routes – add & list wallets (protected)."""

import logging
from flask import Blueprint, request, jsonify
from middleware.auth_middleware import token_required
from services.wallet_service import add_wallet, list_wallets

logger = logging.getLogger(__name__)

wallet_bp = Blueprint("wallet", __name__, url_prefix="/api/wallets")


@wallet_bp.route("", methods=["POST"])
@token_required
def add_wallet_route(current_user):
    """
    POST /api/wallets
    Headers: Authorization: Bearer <token>
    Body: { wallet_number, provider, wallet_name, is_primary? }
    """
    user_id = current_user["user_id"]
    data = request.get_json(silent=True)
    if not data:
        logger.warning("Add-wallet attempt with non-JSON body: user_id=%s", user_id)
        return jsonify({"success": False, "errors": ["Request body must be JSON."]}), 400

    wallet_number = data.get("wallet_number", "<missing>")
    provider = data.get("provider", "<missing>")
    logger.info("Add-wallet attempt: user_id=%s wallet=%s provider=%s", user_id, wallet_number, provider)

    try:
        body, status = add_wallet(user_id, data)
        if status == 201:
            logger.info("Wallet linked: user_id=%s wallet=%s provider=%s", user_id, wallet_number, provider)
        else:
            logger.warning("Wallet rejected: user_id=%s wallet=%s status=%s errors=%s", user_id, wallet_number, status, body.get("errors"))
        return jsonify(body), status
    except Exception:
        logger.exception("Add-wallet error: user_id=%s wallet=%s", user_id, wallet_number)
        return jsonify({"success": False, "errors": ["Failed to add wallet. Please try again."]}), 500


@wallet_bp.route("", methods=["GET"])
@token_required
def list_wallets_route(current_user):
    """
    GET /api/wallets
    Headers: Authorization: Bearer <token>
    Returns all wallets for the authenticated user.
    """
    user_id = current_user["user_id"]
    try:
        body, status = list_wallets(user_id)
        logger.info("List wallets: user_id=%s count=%s", user_id, body.get("count", 0))
        return jsonify(body), status
    except Exception:
        logger.exception("List-wallets error: user_id=%s", user_id)
        return jsonify({"success": False, "errors": ["Failed to retrieve wallets."]}), 500

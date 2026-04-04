"""
Wallet routes – add & list wallets (protected).

Both routes are protected by the @token_required decorator which:
  1. Reads the Authorization header.
  2. Expects the format:  Bearer <jwt_token>
  3. Decodes the JWT using the same SECRET_KEY and HS256 algorithm
     that auth_service.generate_token() used to sign it.
  4. Passes the decoded payload as `current_user` dict
     (keys: user_id, role, exp, iat) to the route handler.
  5. Returns 401 with a clear JSON error if the token is missing,
     malformed, expired, or invalid.

Route summary:
  POST /api/wallet/add  — link a new mobile money wallet
  GET  /api/wallet       — list all wallets for the logged-in user
"""

import logging
from flask import Blueprint, request, jsonify
from middleware.auth_middleware import token_required
from services.wallet_service import add_wallet, list_wallets, remove_wallet, set_primary_wallet
from utils.audit import audit_log

logger = logging.getLogger(__name__)

wallet_bp = Blueprint("wallet", __name__, url_prefix="/api/wallet")


@wallet_bp.route("/add", methods=["POST"])
@token_required
def add(current_user):
    """
    POST /api/wallet/add
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
            audit_log("WALLET_ADD", user_id=user_id, detail=f"wallet={wallet_number} provider={provider}")
        else:
            logger.warning("Wallet rejected: user_id=%s wallet=%s status=%s errors=%s", user_id, wallet_number, status, body.get("errors"))
        return jsonify(body), status
    except Exception:
        logger.exception("Add-wallet error: user_id=%s wallet=%s", user_id, wallet_number)
        return jsonify({"success": False, "errors": ["Failed to add wallet. Please try again."]}), 500


@wallet_bp.route("", methods=["GET"])
@token_required
def index(current_user):
    """
    GET /api/wallet
    Headers: Authorization: Bearer <token>
    Returns all wallets for the authenticated user.
    """
    user_id = current_user["user_id"]
    try:
        body, status = list_wallets(user_id)
        logger.debug("List wallets: user_id=%s count=%s", user_id, body.get("count", 0))
        return jsonify(body), status
    except Exception:
        logger.exception("List-wallets error: user_id=%s", user_id)
        return jsonify({"success": False, "errors": ["Failed to retrieve wallets."]}), 500


@wallet_bp.route("/<int:wallet_id>", methods=["DELETE"])
@token_required
def remove(current_user, wallet_id):
    """
    DELETE /api/wallet/<wallet_id>
    Remove a wallet owned by the authenticated user.
    """
    user_id = current_user["user_id"]
    try:
        body, status = remove_wallet(user_id, wallet_id)
        if status == 200:
            audit_log("WALLET_REMOVE", user_id=user_id, detail=f"wallet_id={wallet_id}")
        return jsonify(body), status
    except Exception:
        logger.exception("Remove-wallet error: user_id=%s wallet_id=%s", user_id, wallet_id)
        return jsonify({"success": False, "errors": ["Failed to remove wallet."]}), 500


@wallet_bp.route("/<int:wallet_id>/primary", methods=["PATCH"])
@token_required
def set_primary(current_user, wallet_id):
    """
    PATCH /api/wallet/<wallet_id>/primary
    Set the given wallet as the user's primary wallet.
    """
    user_id = current_user["user_id"]
    try:
        body, status = set_primary_wallet(user_id, wallet_id)
        if status == 200:
            audit_log("WALLET_SET_PRIMARY", user_id=user_id, detail=f"wallet_id={wallet_id}")
        return jsonify(body), status
    except Exception:
        logger.exception("Set-primary-wallet error: user_id=%s wallet_id=%s", user_id, wallet_id)
        return jsonify({"success": False, "errors": ["Failed to update primary wallet."]}), 500

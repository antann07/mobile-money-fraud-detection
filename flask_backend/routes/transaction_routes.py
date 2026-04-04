"""
Transaction routes – add and list transactions (JWT-protected).

Route summary:
  POST /api/transactions/add  — record a new transaction
  GET  /api/transactions      — list all transactions for the logged-in user
"""

import logging
from flask import Blueprint, request, jsonify
from middleware.auth_middleware import token_required
from services.transaction_service import add_transaction, list_transactions
from utils.audit import audit_log

logger = logging.getLogger(__name__)

transaction_bp = Blueprint("transactions", __name__, url_prefix="/api/transactions")


# -----------------------------------------------------------------
# POST /api/transactions/add
# -----------------------------------------------------------------

@transaction_bp.route("/add", methods=["POST"])
@token_required
def add(current_user):
    """
    Record a new transaction.

    Headers:  Authorization: Bearer <token>
    Body (JSON):
      {
        "wallet_id": 1,
        "transaction_reference": "TXN001",        (optional)
        "transaction_type": "withdrawal",
        "direction": "outgoing",
        "amount": 500,
        "balance_before": 1200,                    (optional)
        "balance_after": 700,                      (optional)
        "transaction_time": "2026-03-29T10:30:00",
        "location_info": "Kumasi",                 (optional)
        "device_info": "Samsung A14",              (optional)
        "source_channel": "manual",                (optional, default: manual)
        "raw_message": "Optional original message" (optional)
      }
    """
    user_id = current_user["user_id"]

    # Ensure the request body is valid JSON
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "errors": ["Request body must be JSON."]}), 400

    logger.info(
        "Add-transaction: user_id=%s wallet_id=%s type=%s amount=%s",
        user_id, data.get("wallet_id"), data.get("transaction_type"), data.get("amount"),
    )

    try:
        body, status = add_transaction(user_id, data)
        if status == 201:
            txn_id = body.get("transaction", {}).get("id", "?")
            audit_log("TRANSACTION_ADD", user_id=user_id, detail=f"txn_id={txn_id} wallet={data.get('wallet_id')} amount={data.get('amount')}")
        return jsonify(body), status
    except Exception:
        logger.exception("Add-transaction error: user_id=%s", user_id)
        return jsonify({"success": False, "errors": ["Failed to create transaction."]}), 500


# -----------------------------------------------------------------
# GET /api/transactions
# -----------------------------------------------------------------

@transaction_bp.route("", methods=["GET"])
@token_required
def list_all(current_user):
    """
    List all transactions for the logged-in user's wallets.

    Headers:  Authorization: Bearer <token>
    """
    user_id = current_user["user_id"]
    logger.debug("List-transactions: user_id=%s", user_id)

    try:
        body, status = list_transactions(user_id)
        return jsonify(body), status
    except Exception:
        logger.exception("List-transactions error: user_id=%s", user_id)
        return jsonify({"success": False, "errors": ["Failed to load transactions."]}), 500

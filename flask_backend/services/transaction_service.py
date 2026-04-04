"""
Transaction service – business logic for adding and listing transactions.

Handles:
  - Input validation (required fields, types, ownership)
  - Delegating to the transaction model for DB operations
  - Clean JSON error responses
"""

import logging
from datetime import datetime

from models.transaction import (
    create_transaction,
    get_transactions_by_wallet_ids,
)
from models.wallet import get_wallets_by_user
from models.prediction import create_prediction
from services.fraud_engine import score_transaction

logger = logging.getLogger(__name__)

# Accepted values for constrained fields
VALID_TYPES = ("deposit", "withdrawal", "transfer", "payment")
VALID_DIRECTIONS = ("incoming", "outgoing")
VALID_CHANNELS = ("manual", "ussd", "app", "api")


# -----------------------------------------------------------------
# Validation
# -----------------------------------------------------------------

def _validate_transaction(data: dict) -> list[str]:
    """
    Check the request body and return a list of error strings.
    An empty list means the data is valid.
    """
    errors = []

    # --- required fields ---
    required = ["wallet_id", "transaction_type", "direction", "amount", "transaction_time"]
    missing = [f for f in required if f not in data or data[f] is None]
    if missing:
        errors.append(f"Missing required fields: {', '.join(missing)}.")
        return errors          # no point checking further

    # --- wallet_id ---
    wallet_id = data.get("wallet_id")
    if not isinstance(wallet_id, int) or wallet_id < 1:
        errors.append("wallet_id must be a positive integer.")

    # --- transaction_type ---
    if data.get("transaction_type") not in VALID_TYPES:
        errors.append(f"transaction_type must be one of {list(VALID_TYPES)}.")

    # --- direction ---
    if data.get("direction") not in VALID_DIRECTIONS:
        errors.append(f"direction must be one of {list(VALID_DIRECTIONS)}.")

    # --- amount ---
    try:
        amount = float(data["amount"])
        if amount <= 0:
            errors.append("amount must be greater than 0.")
    except (TypeError, ValueError):
        errors.append("amount must be a number.")

    # --- balance_before / balance_after (optional but must be numbers) ---
    for field in ("balance_before", "balance_after"):
        val = data.get(field)
        if val is not None:
            try:
                float(val)
            except (TypeError, ValueError):
                errors.append(f"{field} must be a number if provided.")

    # --- source_channel (optional, defaults to 'manual') ---
    channel = data.get("source_channel", "manual")
    if channel not in VALID_CHANNELS:
        errors.append(f"source_channel must be one of {list(VALID_CHANNELS)}.")

    return errors


# -----------------------------------------------------------------
# Add transaction
# -----------------------------------------------------------------

def add_transaction(user_id: int, data: dict) -> tuple[dict, int]:
    """
    Validate input → verify wallet ownership → create transaction.
    Returns (response_body, http_status_code).
    """
    # 1. Validate fields
    errors = _validate_transaction(data)
    if errors:
        return {"success": False, "errors": errors}, 400

    # 2. Verify the wallet belongs to the logged-in user
    wallet_id = int(data["wallet_id"])
    user_wallets = get_wallets_by_user(user_id)
    user_wallet_ids = [w["id"] for w in user_wallets]

    if wallet_id not in user_wallet_ids:
        return {"success": False, "errors": ["Wallet does not belong to you."]}, 403

    # 3. Build clean field values
    amount = float(data["amount"])
    balance_before = float(data["balance_before"]) if data.get("balance_before") is not None else None
    balance_after = float(data["balance_after"]) if data.get("balance_after") is not None else None
    transaction_time = data["transaction_time"]
    transaction_reference = data.get("transaction_reference")
    location_info = data.get("location_info")
    device_info = data.get("device_info")
    source_channel = data.get("source_channel", "manual")
    raw_message = data.get("raw_message")

    # 4. Insert into the database
    txn = create_transaction(
        wallet_id=wallet_id,
        transaction_type=data["transaction_type"],
        direction=data["direction"],
        amount=amount,
        transaction_time=transaction_time,
        transaction_reference=transaction_reference,
        balance_before=balance_before,
        balance_after=balance_after,
        location_info=location_info,
        device_info=device_info,
        source_channel=source_channel,
        raw_message=raw_message,
    )

    if txn is None:
        return {"success": False, "errors": ["Failed to create transaction."]}, 500

    logger.info("Transaction created: id=%s wallet=%s amount=%s", txn["id"], wallet_id, amount)

    # 5. Auto-score the transaction for fraud and save to DB
    fraud_result = None
    saved_prediction = None
    try:
        fraud_result = score_transaction(txn)
        logger.info(
            "Fraud scored: txn=%s prediction=%s risk=%s",
            txn["id"], fraud_result["prediction"], fraud_result["risk_level"],
        )

        # 6. Persist the prediction into fraud_predictions table
        saved_prediction = create_prediction(
            transaction_id=txn["id"],
            prediction=fraud_result["prediction"],
            anomaly_label=fraud_result["anomaly_label"],
            anomaly_score=fraud_result["anomaly_score"],
            risk_level=fraud_result["risk_level"],
            explanation=fraud_result["explanation"],
            amount_zscore=fraud_result.get("amount_zscore", 0),
            txn_time_deviation=fraud_result.get("txn_time_deviation", 0),
            balance_drain_ratio=fraud_result.get("balance_drain_ratio", 0),
            is_new_device=fraud_result.get("is_new_device", 0),
            is_new_location=fraud_result.get("is_new_location", 0),
            velocity_1day=fraud_result.get("velocity_1day", 0),
        )
        logger.info("Prediction saved: id=%s", saved_prediction["id"] if saved_prediction else "NONE")
    except Exception:
        logger.exception("Fraud scoring failed for txn %s — transaction still saved", txn["id"])

    return {
        "success": True,
        "message": "Transaction added and scored successfully.",
        "transaction": txn,
        "prediction": saved_prediction,
    }, 201


# -----------------------------------------------------------------
# List transactions
# -----------------------------------------------------------------

def list_transactions(user_id: int) -> tuple[dict, int]:
    """Return all transactions for wallets owned by the logged-in user."""
    user_wallets = get_wallets_by_user(user_id)
    wallet_ids = [w["id"] for w in user_wallets]

    if not wallet_ids:
        return {"success": True, "count": 0, "transactions": []}, 200

    transactions = get_transactions_by_wallet_ids(wallet_ids)

    return {
        "success": True,
        "count": len(transactions),
        "transactions": transactions,
    }, 200

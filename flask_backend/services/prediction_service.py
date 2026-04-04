"""Prediction service — business logic for listing fraud predictions."""

import logging
from models.transaction import get_transactions_by_wallet_ids
from models.prediction import get_predictions_by_transaction_ids
from models.wallet import get_wallets_by_user

logger = logging.getLogger(__name__)


def list_predictions(user_id: int) -> tuple[dict, int]:
    """Return all fraud predictions for the logged-in user's transactions."""
    user_wallets = get_wallets_by_user(user_id)
    wallet_ids = [w["id"] for w in user_wallets]

    if not wallet_ids:
        return {"success": True, "predictions": []}, 200

    transactions = get_transactions_by_wallet_ids(wallet_ids)
    txn_ids = [t["id"] for t in transactions]

    if not txn_ids:
        return {"success": True, "predictions": []}, 200

    predictions = get_predictions_by_transaction_ids(txn_ids)

    return {"success": True, "count": len(predictions), "predictions": predictions}, 200

"""
Prediction routes – list fraud predictions (protected).

Route summary:
  GET  /api/predictions  — list all fraud predictions for the logged-in user
"""

import logging
from flask import Blueprint, jsonify
from middleware.auth_middleware import token_required
from services.prediction_service import list_predictions

logger = logging.getLogger(__name__)

prediction_bp = Blueprint("predictions", __name__, url_prefix="/api/predictions")


@prediction_bp.route("", methods=["GET"])
@token_required
def list_all(current_user):
    """
    GET /api/predictions
    Headers: Authorization: Bearer <token>
    Returns all fraud predictions for the logged-in user's transactions.
    """
    user_id = current_user["user_id"]
    logger.debug("List-predictions: user_id=%s", user_id)

    try:
        body, status = list_predictions(user_id)
        return jsonify(body), status
    except Exception:
        logger.exception("List-predictions error: user_id=%s", user_id)
        return jsonify({"success": False, "errors": ["Failed to load predictions."]}), 500

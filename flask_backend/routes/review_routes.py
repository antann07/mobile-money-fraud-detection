"""
Review routes — Admin review workflow for flagged message checks.

Protected routes (JWT + admin role required):
  GET  /api/reviews/flagged               — list all flagged message checks
  GET  /api/reviews/<message_check_id>    — full review detail for one check
  POST /api/reviews/<message_check_id>    — create or update a fraud review
"""

import logging
from flask import Blueprint, request, jsonify
from middleware.auth_middleware import token_required, admin_required
from services.review_service import (
    get_flagged_checks,
    get_review_detail,
    submit_review,
)
from utils.audit import audit_log

logger = logging.getLogger(__name__)

review_bp = Blueprint("review", __name__, url_prefix="/api/reviews")

# Phase-10: route-level whitelist so invalid values are rejected before
# they reach the service layer, reducing avoidable 500s
_VALID_REVIEWER_LABELS = {"genuine", "suspicious", "likely_fraudulent"}
_VALID_REVIEW_STATUSES = {"pending", "confirmed_fraud", "confirmed_genuine", "escalated"}


# ═══════════════════════════════════════════════
# GET /api/reviews/flagged
# ═══════════════════════════════════════════════

@review_bp.route("/flagged", methods=["GET"])
@token_required
@admin_required
def flagged_list(current_user):
    """
    Return all message checks whose prediction label is
    'suspicious' or 'likely_fraudulent', with joined prediction summary.

    Headers: Authorization: Bearer <token>  (admin only)
    Query params:
        limit — max results (default 200)
    """
    limit = request.args.get("limit", 200, type=int)
    limit = max(1, min(limit, 500))

    try:
        body, status = get_flagged_checks(limit=limit)
        logger.info("Flagged list: admin_id=%s count=%s", current_user["user_id"], body.get("count", 0))
        return jsonify(body), status
    except Exception:
        logger.exception("Flagged list error: admin_id=%s", current_user["user_id"])
        return jsonify({"success": False, "errors": ["Failed to retrieve flagged checks."]}), 500


# ═══════════════════════════════════════════════
# GET /api/reviews/<message_check_id>
# ═══════════════════════════════════════════════

@review_bp.route("/<int:message_check_id>", methods=["GET"])
@token_required
@admin_required
def review_detail(current_user, message_check_id):
    """
    Return full review detail for a single flagged message check.

    Headers: Authorization: Bearer <token>  (admin only)
    """
    try:
        body, status = get_review_detail(message_check_id)
        return jsonify(body), status
    except Exception:
        logger.exception("Review detail error: admin_id=%s check_id=%s",
                         current_user["user_id"], message_check_id)
        return jsonify({"success": False, "errors": ["Failed to retrieve review detail."]}), 500


# ═══════════════════════════════════════════════
# POST /api/reviews/<message_check_id>
# ═══════════════════════════════════════════════

@review_bp.route("/<int:message_check_id>", methods=["POST"])
@token_required
@admin_required
def submit_review_route(current_user, message_check_id):
    """
    Create or update a fraud review for a flagged message check.

    Headers: Authorization: Bearer <token>  (admin only)
    Body: {
        "reviewer_label": "genuine" | "suspicious" | "likely_fraudulent",
        "review_status": "pending" | "confirmed_fraud" | "confirmed_genuine" | "escalated",
        "notes": "..."  (optional)
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "errors": ["Request body must be JSON."]}), 400

    reviewer_label = data.get("reviewer_label", "").strip() if isinstance(data.get("reviewer_label"), str) else ""
    review_status = data.get("review_status", "").strip() if isinstance(data.get("review_status"), str) else ""
    notes = data.get("notes", "").strip() if isinstance(data.get("notes"), str) else ""

    if not reviewer_label:
        return jsonify({"success": False, "errors": ["reviewer_label is required."]}), 400
    if not review_status:
        return jsonify({"success": False, "errors": ["review_status is required."]}), 400
    # Phase-10: reject invalid values early with a clear message
    if reviewer_label not in _VALID_REVIEWER_LABELS:
        return jsonify({
            "success": False,
            "errors": [f"reviewer_label must be one of: {', '.join(sorted(_VALID_REVIEWER_LABELS))}"],
        }), 400
    if review_status not in _VALID_REVIEW_STATUSES:
        return jsonify({
            "success": False,
            "errors": [f"review_status must be one of: {', '.join(sorted(_VALID_REVIEW_STATUSES))}"],
        }), 400
    if len(notes) > 2000:
        return jsonify({"success": False, "errors": ["notes must not exceed 2000 characters."]}), 400

    try:
        body, status = submit_review(
            message_check_id=message_check_id,
            reviewer_id=current_user["user_id"],
            reviewer_label=reviewer_label,
            review_status=review_status,
            notes=notes or None,
        )

        if status in (200, 201):
            audit_log(
                "REVIEW_SUBMIT",
                user_id=current_user["user_id"],
                detail=f"check_id={message_check_id} label={reviewer_label} status={review_status}",
            )

        return jsonify(body), status
    except Exception:
        logger.exception("Submit review error: admin_id=%s check_id=%s",
                         current_user["user_id"], message_check_id)
        return jsonify({"success": False, "errors": ["Failed to submit review."]}), 500

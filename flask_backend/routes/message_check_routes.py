"""
Message Check routes — SMS and screenshot verification endpoints.

Protected routes (JWT required):
  POST /api/message-checks/sms-check         — submit an SMS for verification
  POST /api/message-checks/upload-screenshot  — upload a screenshot for verification
  GET  /api/message-checks/history            — get user's check history
  GET  /api/message-checks/<id>               — get a single check detail
"""

import os
import logging
from uuid import uuid4
from flask import Blueprint, request, jsonify
from middleware.auth_middleware import token_required
from services.message_check_service import (
    check_sms,
    check_screenshot,
    get_user_history,
    get_check_detail,
)
from services.ocr_service import extract_text as ocr_extract_text, is_available as ocr_is_available
from utils.audit import audit_log
from config import get_config

logger = logging.getLogger(__name__)

message_check_bp = Blueprint("message_check", __name__, url_prefix="/api/message-checks")

# Upload directory for screenshots — reads from config (UPLOAD_DIR env var)
_cfg = get_config()
_UPLOAD_DIR = _cfg.UPLOAD_DIR
os.makedirs(_UPLOAD_DIR, exist_ok=True)

# Allowed screenshot file extensions
_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Phase-8 refinement: magic-byte signatures to verify actual image content
# (prevents renamed .exe / .php being accepted just because extension is .png)
_MAGIC_BYTES = {
    b"\x89PNG":   ".png",
    b"\xff\xd8\xff": ".jpg",   # covers .jpg and .jpeg
    b"RIFF":     ".webp",      # WebP starts with RIFF....WEBP
}


def _allowed_file(filename: str) -> bool:
    """Check if the uploaded file has an allowed extension."""
    _, ext = os.path.splitext(filename)
    return ext.lower() in _ALLOWED_EXTENSIONS


def _verify_magic_bytes(file_obj) -> bool:
    """Read the first 12 bytes to confirm the file is actually an image.
    Returns True if magic bytes match a known image format."""
    header = file_obj.read(12)
    file_obj.seek(0)  # always rewind
    if len(header) < 4:
        return False
    for magic, _ in _MAGIC_BYTES.items():
        if header[:len(magic)] == magic:
            return True
    return False


# ═══════════════════════════════════════════════
# POST /api/message-checks/sms-check
# ═══════════════════════════════════════════════

@message_check_bp.route("/sms-check", methods=["POST"])
@token_required
def sms_check(current_user):
    """
    Submit an SMS message for MTN MoMo authenticity verification.

    Headers: Authorization: Bearer <token>
    Body: {
        "raw_text": "You have received GHS 50.00 from ...",
        "wallet_id": 1  (optional)
    }
    """
    user_id = current_user["user_id"]
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"success": False, "errors": ["Request body must be JSON."]}), 400

    raw_text = data.get("raw_text", "").strip() if isinstance(data.get("raw_text"), str) else ""
    if not raw_text:
        return jsonify({"success": False, "errors": ["raw_text is required and cannot be empty."]}), 400

    if len(raw_text) > 2000:
        return jsonify({"success": False, "errors": ["raw_text must not exceed 2000 characters."]}), 400

    wallet_id = data.get("wallet_id")
    if wallet_id is not None:
        if not isinstance(wallet_id, int) or wallet_id <= 0:
            return jsonify({"success": False, "errors": ["wallet_id must be a positive integer."]}), 400

    logger.info("SMS check request: user_id=%s text_length=%d wallet_id=%s",
                user_id, len(raw_text), wallet_id)

    try:
        body, status = check_sms(user_id, raw_text, wallet_id)
        if status == 201:
            label = body.get("data", {}).get("prediction", {}).get("predicted_label", "unknown")
            conf = body.get("data", {}).get("prediction", {}).get("confidence_score", 0)
            audit_log("SMS_CHECK", user_id=user_id,
                      detail=f"label={label} confidence={conf} text_len={len(raw_text)}")
            logger.info("SMS check success: user_id=%s label=%s confidence=%s", user_id, label, conf)
        else:
            logger.warning("SMS check returned non-201: user_id=%s status=%s body=%s",
                           user_id, status, body)
        return jsonify(body), status
    except Exception:
        logger.exception("SMS check unhandled error: user_id=%s", user_id)
        return jsonify({"success": False, "errors": ["Failed to analyze SMS. Please try again."]}), 500


# ═══════════════════════════════════════════════
# POST /api/message-checks/upload-screenshot
# ═══════════════════════════════════════════════

@message_check_bp.route("/upload-screenshot", methods=["POST"])
@token_required
def upload_screenshot(current_user):
    """
    Upload a screenshot of an MTN MoMo notification for verification.

    Headers: Authorization: Bearer <token>
    Body: multipart/form-data with:
        file       — the screenshot image (png, jpg, jpeg, webp; max 5 MB)
        wallet_id  — optional integer
    """
    user_id = current_user["user_id"]
    logger.info("[UPLOAD] Step 1 — request received: user_id=%s content_type=%s",
                user_id, request.content_type)

    # -- Step 1: Ensure the request is multipart/form-data --
    if not request.content_type or "multipart/form-data" not in request.content_type:
        logger.warning("[UPLOAD] Bad content type: user_id=%s ct=%s", user_id, request.content_type)
        return jsonify({"success": False, "errors": ["Request must be multipart/form-data."]}), 400

    # -- Step 2: Validate file presence --
    # Accept both field names for flexibility ('file' is canonical)
    file = request.files.get("file") or request.files.get("screenshot")
    if file is None:
        logger.warning("[UPLOAD] No file field in request: user_id=%s", user_id)
        return jsonify({"success": False, "errors": ["No file uploaded. Please attach a screenshot."]}), 400

    if file.filename == "":
        return jsonify({"success": False, "errors": ["No file selected."]}), 400

    # -- Step 3: Validate extension --
    if not _allowed_file(file.filename):
        # Log only the extension, not the full user-supplied filename (safety)
        _, bad_ext = os.path.splitext(file.filename)
        logger.warning("[UPLOAD] Rejected extension: user_id=%s ext=%s", user_id, bad_ext)
        return jsonify({
            "success": False,
            "errors": [f"File type not allowed. Accepted: {', '.join(sorted(_ALLOWED_EXTENSIONS))}."],
        }), 400

    # -- Step 4: Validate file size --
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size == 0:
        return jsonify({"success": False, "errors": ["File is empty."]}), 400
    if size > _MAX_FILE_SIZE:
        logger.warning("[UPLOAD] File too large: user_id=%s size=%d", user_id, size)
        return jsonify({"success": False, "errors": ["File too large. Maximum size is 5 MB."]}), 400

    # -- Step 5: Verify magic bytes — confirm file is actually an image --
    # Phase-8 refinement: prevents renamed malicious files from being accepted
    if not _verify_magic_bytes(file):
        logger.warning("[UPLOAD] Magic-byte check failed: user_id=%s — file content does not match an image", user_id)
        return jsonify({"success": False, "errors": ["File does not appear to be a valid image."]}), 400

    # -- Step 6: Validate optional wallet_id BEFORE saving file --
    # Phase-8 refinement: moved before save so bad requests don't leave orphan files
    wallet_id = request.form.get("wallet_id")
    if wallet_id is not None and wallet_id != "":
        try:
            wallet_id = int(wallet_id)
            if wallet_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "errors": ["wallet_id must be a positive integer."]}), 400
    else:
        wallet_id = None

    # -- Step 7: Save with unique filename --
    _, ext = os.path.splitext(file.filename)
    safe_filename = f"{user_id}_{uuid4().hex[:12]}{ext.lower()}"
    save_path = os.path.join(_UPLOAD_DIR, safe_filename)
    os.makedirs(_UPLOAD_DIR, exist_ok=True)  # ensure dir exists at save time
    file.save(save_path)
    logger.info("[UPLOAD] Step 7 — file saved: user_id=%s name=%s size=%d", user_id, safe_filename, size)

    # -- Step 8: OCR text extraction --
    # Phase-8 Part 2 refined: attempt OCR, use usability gate, handle crashes gracefully
    extracted_text = None
    ocr_confidence = 0.0
    ocr_low_confidence = False
    ocr_usable = False
    ocr_error = None
    scam_detected = False                                # Phase 9
    context_flags: list = []                               # v6.5
    contradictory_context: bool = False                    # v6.5

    if ocr_is_available():
        logger.info("[UPLOAD] Step 8 — OCR: starting extraction. user_id=%s file=%s", user_id, safe_filename)
        try:
            ocr_result = ocr_extract_text(save_path)
            ocr_confidence = ocr_result.get("confidence", 0.0)
            ocr_low_confidence = ocr_result.get("low_confidence", False)
            ocr_usable = ocr_result.get("usable", False)
            scam_detected = ocr_result.get("scam_detected", False)  # Phase 9
            context_flags = ocr_result.get("context_flags", [])          # v6.5
            contradictory_context = ocr_result.get("contradictory_context", False)  # v6.5

            if ocr_result["success"]:
                extracted_text = ocr_result["extracted_text"]
                logger.info("[UPLOAD] Step 8 — OCR succeeded: %d chars, conf=%.2f, usable=%s",
                            len(extracted_text or ""), ocr_confidence, ocr_usable)
            else:
                ocr_error = ocr_result.get("error", "Unknown OCR failure")
                logger.warning("[UPLOAD] Step 8 — OCR failed: error=%s", ocr_error)
                # Partial recovery: if OCR returned some text despite "failure",
                # still capture it for display (but only analyze if usable)
                partial = ocr_result.get("extracted_text") or ""
                if len(partial.strip()) >= 10:
                    extracted_text = partial.strip()
                    ocr_low_confidence = True
                    logger.info("[UPLOAD] Step 8 — Partial OCR recovery: %d chars, usable=%s",
                                len(extracted_text), ocr_usable)
        except Exception:
            logger.exception("[UPLOAD] Step 8 — OCR crashed unexpectedly: user_id=%s", user_id)
            ocr_error = "OCR engine encountered an error. Your screenshot was still saved."
    else:
        logger.warning("[UPLOAD] Step 8 — OCR: Tesseract not installed, skipping. user_id=%s", user_id)
        ocr_error = "OCR is not available. Please install Tesseract OCR to enable screenshot text extraction."

    # -- Step 9: Create message_check + optional analysis --
    # Pass text to analysis if OCR deemed it usable OR scam signals found.
    # Phase 9: scam-detected text bypasses the normal MoMo-keyword gate
    # so the authenticity engine can score it for scam-specific language.
    analysis_text = extracted_text if (ocr_usable or scam_detected) else None
    try:
        body, status = check_screenshot(
            user_id, save_path, wallet_id,
            extracted_text=analysis_text,
            display_text=extracted_text,       # always store for frontend display
            ocr_confidence=ocr_confidence,
        )

        # Merge OCR metadata into the standardized response
        body["ocr_confidence"] = round(ocr_confidence, 2)
        body["ocr_low_confidence"] = ocr_low_confidence
        body["ocr_usable"] = ocr_usable
        body["scam_detected"] = scam_detected               # Phase 9
        body["context_flags"] = context_flags                 # v6.5: multi-message scam context

        # Append OCR-level warnings into the standard warnings array
        # so the frontend only needs to check one field
        if "warnings" not in body:
            body["warnings"] = []
        if ocr_error:
            body["warnings"].append(ocr_error)
        if ocr_low_confidence and not ocr_error:
            body["warnings"].append("OCR confidence is low — extracted text may contain errors.")
        # Phase 9: warn when scam language triggered analysis on non-MoMo text
        if scam_detected and not ocr_usable:
            body["warnings"].append(
                "Scam-like language was detected in the screenshot. "
                "The text did not match a standard MoMo format but was "
                "analyzed for fraud indicators."
            )
        # v6.5: warn when screenshot shows contradictory multi-message scam context
        if contradictory_context:
            body["warnings"].append(
                "Screenshot appears to contain multiple messages with contradictory content "
                "(a payment claim combined with a reversal demand or account suspension threat). "
                "This pattern is a known MTN MoMo scam. The payment shown has NOT been verified."
            )

        # Always include extracted text at top level for frontend
        if extracted_text:
            body["extracted_text"] = extracted_text

        ocr_note = f"ocr_conf={ocr_confidence:.2f} usable={ocr_usable}" if extracted_text else f"ocr_fail={ocr_error or 'pending'}"
        audit_log("SCREENSHOT_UPLOAD", user_id=user_id,
                  detail=f"file={safe_filename} size={size} {ocr_note}")
        logger.info("[UPLOAD] Step 9 — complete: user_id=%s http_status=%s ocr_usable=%s",
                    user_id, status, ocr_usable)
        return jsonify(body), status
    except Exception:
        logger.exception("[UPLOAD] Screenshot check error: user_id=%s", user_id)
        return jsonify({"success": False, "errors": ["Failed to process screenshot. Please try again."]}), 500


# ═══════════════════════════════════════════════
# GET /api/message-checks/history
# ═══════════════════════════════════════════════

@message_check_bp.route("/history", methods=["GET"])
@token_required
def history(current_user):
    """
    Get the logged-in user's message check history with prediction summaries.

    Headers: Authorization: Bearer <token>
    Query params:
        limit — max results (default 50, max 200)
    """
    user_id = current_user["user_id"]

    limit = request.args.get("limit", 50, type=int)
    limit = max(1, min(limit, 200))

    try:
        body, status = get_user_history(user_id, limit=limit)
        logger.debug("History: user_id=%s count=%s", user_id, body.get("count", 0))
        return jsonify(body), status
    except Exception:
        logger.exception("History error: user_id=%s", user_id)
        return jsonify({"success": False, "errors": ["Failed to retrieve history."]}), 500


# ═══════════════════════════════════════════════
# GET /api/message-checks/<id>
# ═══════════════════════════════════════════════

@message_check_bp.route("/<int:check_id>", methods=["GET"])
@token_required
def detail(current_user, check_id):
    """
    Get a single message check with full prediction detail.
    Only accessible if the check belongs to the logged-in user.

    Headers: Authorization: Bearer <token>
    """
    user_id = current_user["user_id"]

    try:
        body, status = get_check_detail(check_id, user_id)
        return jsonify(body), status
    except Exception:
        logger.exception("Detail error: user_id=%s check_id=%s", user_id, check_id)
        return jsonify({"success": False, "errors": ["Failed to retrieve message check."]}), 500

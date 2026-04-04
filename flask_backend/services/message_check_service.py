"""
Message Check Service — orchestrates the full SMS/screenshot verification flow.

This is the main entry point called by the route handlers.
It coordinates:
  1. Parsing (sms_parser)
  2. Authenticity analysis (authenticity_engine)
  3. Database writes (message_checks, predictions, user_behavior_profiles)

Public functions:
  check_sms()            — full flow for a pasted SMS
  check_screenshot()     — scaffold for screenshot upload
  get_user_history()     — fetch user's check history with predictions
  get_check_detail()     — fetch a single check with full prediction detail
"""

import os
import logging
from models.message_check import (
    create_message_check,
    get_message_check_by_id,
    get_checks_by_user,
    update_message_check,
)
from models.mtn_prediction import (
    create_mtn_prediction,
    get_prediction_by_check_id,
)
from models.behavior_profile import (
    get_or_create_profile,
    update_profile,
)
from services.sms_parser import parse_sms, is_in_scope
from services.authenticity_engine import analyze_message
from services.ml_scorer import score_message as ml_score_message

logger = logging.getLogger(__name__)

# Status mapping: engine label → message_check status
_LABEL_TO_STATUS = {
    "genuine":            "verified",
    "suspicious":         "flagged",
    "likely_fraudulent":  "flagged",
    "out_of_scope":       "out_of_scope",
}


# ═══════════════════════════════════════════════
# Shared internal helpers
# ═══════════════════════════════════════════════

# Human-readable transaction-type labels used in out-of-scope explanations.
_TXN_TYPE_LABEL = {
    "payment":    "outgoing payment",
    "withdrawal": "cash withdrawal",
    "transfer":   "outgoing transfer",
    "airtime":    "airtime purchase",
    "bill":       "bill payment",
    "deposit":    "deposit",
}


def _build_out_of_scope_result(parsed: dict, reason: str) -> dict:
    """
    Build a synthetic prediction-like dict for an out-of-scope message.

    This is returned instead of running the fraud model so the frontend
    can display a clean, informative neutral card.
    """
    direction = parsed.get("direction", "unknown")
    txn_type = parsed.get("transaction_type")
    amount = parsed.get("amount")
    amount_str = f" of GHS {amount:,.2f}" if amount is not None else ""

    # Build a readable label for the transaction type
    if direction == "unknown" or txn_type is None:
        txn_label = "message"
        explanation = (
            "This message could not be identified as an incoming MTN MoMo "
            "credit alert. The fraud detector only analyses incoming transfer, "
            "payment received, and cash-in notifications. No fraud analysis "
            "was run on this message."
        )
    else:
        txn_label = _TXN_TYPE_LABEL.get(txn_type, "transaction")
        explanation = (
            f"This is an {txn_label} confirmation{amount_str}. "
            "The fraud detector is scoped to incoming credit alerts "
            "(transfers received, cash-in, deposits). "
            "No fraud analysis was run — outgoing and airtime messages are "
            "normal confirmation notifications."
        )

    return {
        "predicted_label":           "out_of_scope",
        "confidence_score":          1.0,
        "explanation":               explanation,
        "format_risk_score":         0.0,
        "behavior_risk_score":       0.0,
        "balance_consistency_score": 0.0,
        "sender_novelty_score":      0.0,
        "model_version":             "out-of-scope",
        "ml_available":              False,
        "ml_label":                  None,
        "ml_confidence":             0.0,
        "ml_agrees":                 None,
        "scope_reason":              reason,
    }


def _save_parsed_fields(check_id: int, parsed: dict) -> bool:
    """Write all parser-extracted fields onto an existing message_check row.
    Returns True on success, False on failure."""
    try:
        update_message_check(
            check_id,
            extracted_text=parsed.get("extracted_text"),
            mtn_transaction_id=parsed.get("mtn_transaction_id"),
            transaction_reference=parsed.get("transaction_reference"),
            transaction_datetime=parsed.get("transaction_datetime"),
            transaction_type=parsed.get("transaction_type"),
            transaction_category=parsed.get("transaction_category"),
            direction=parsed.get("direction"),
            counterparty_name=parsed.get("counterparty_name"),
            counterparty_number=parsed.get("counterparty_number"),
            amount=parsed.get("amount"),
            fee=parsed.get("fee"),
            tax=parsed.get("tax"),
            total_amount=parsed.get("total_amount"),
            balance_after=parsed.get("balance_after"),
            available_balance=parsed.get("available_balance"),
            provider=parsed.get("provider"),
            parser_confidence=parsed.get("parser_confidence"),
            status="parsed",
        )
        logger.info("Parsed fields saved: check_id=%s mtn_txn_id=%s amount=%s",
                    check_id, parsed.get("mtn_transaction_id"), parsed.get("amount"))
        return True
    except Exception:
        logger.exception("Failed to save parsed fields: check_id=%s", check_id)
        return False


def _run_analysis(
    check_id: int, user_id: int, text: str, parsed: dict,
    input_method: str = "sms_paste",
) -> dict:
    """
    Run the rule engine + ML model, combine results, save prediction.

    Phase 10 Part 3 — Hybrid strategy:
      1. Rule engine is PRIMARY (proven, explainable).
      2. ML model is SECONDARY (advisory, logged alongside).
      3. When they agree → confidence gets a small boost.
      4. When they disagree:
         - If ML says fraudulent with high confidence (≥0.85) but
           rules say genuine → escalate to suspicious (safety net).
         - Otherwise → trust the rule engine.
      5. ML result is always attached to the response so the frontend
         can display it as a supplementary signal.

    Returns the combined result dict.  Raises on engine failure.
    """
    # Load or create user behavior profile
    logger.debug("Loading behavior profile: user_id=%s", user_id)
    profile = get_or_create_profile(user_id)
    logger.debug("Profile loaded: user_id=%s checks_count=%s",
                 user_id, profile.get("total_checks_count"))

    # ── Step A: Rule engine (primary) ──
    result = analyze_message(text, parsed, profile, input_method=input_method)
    logger.info(
        "Engine verdict: check_id=%s label=%s confidence=%.2f "
        "format=%.2f behavior=%.2f balance=%.2f sender=%.2f",
        check_id, result["predicted_label"], result["confidence_score"],
        result["format_risk_score"], result["behavior_risk_score"],
        result["balance_consistency_score"], result["sender_novelty_score"],
    )

    # ── Step B: ML model (secondary — never crashes the request) ──
    ml_result = {"ml_available": False, "ml_label": None, "ml_confidence": 0.0}
    try:
        ml_result = ml_score_message(text, parsed)
        logger.info(
            "ML verdict: check_id=%s available=%s label=%s confidence=%.4f",
            check_id, ml_result["ml_available"],
            ml_result.get("ml_label"), ml_result.get("ml_confidence", 0),
        )
    except Exception:
        logger.exception("ML scorer crashed — continuing with rules only: check_id=%s",
                         check_id)

    # ── Step C: Hybrid combiner ──
    result = _combine_verdicts(result, ml_result)
    logger.info(
        "Hybrid verdict: check_id=%s final_label=%s final_conf=%.2f ml_agree=%s",
        check_id, result["predicted_label"], result["confidence_score"],
        result.get("ml_agrees"),
    )

    # Save prediction
    prediction = create_mtn_prediction(
        message_check_id=check_id,
        predicted_label=result["predicted_label"],
        confidence_score=result["confidence_score"],
        explanation=result["explanation"],
        format_risk_score=result["format_risk_score"],
        behavior_risk_score=result["behavior_risk_score"],
        balance_consistency_score=result["balance_consistency_score"],
        sender_novelty_score=result["sender_novelty_score"],
        model_version=result["model_version"],
    )
    if prediction:
        logger.info("Prediction saved: check_id=%s prediction_id=%s",
                    check_id, prediction["id"])
    else:
        logger.error("Failed to save prediction (duplicate or DB error): check_id=%s",
                     check_id)

    # Update message_check status
    final_status = _LABEL_TO_STATUS.get(result["predicted_label"], "parsed")
    update_message_check(check_id, status=final_status)
    logger.info("Check status updated: check_id=%s status=%s", check_id, final_status)

    # Update user behavior profile (non-critical — don't fail the request)
    try:
        _update_behavior_profile(user_id, parsed)
        logger.info("Behavior profile updated: user_id=%s", user_id)
    except Exception:
        logger.exception("Failed to update behavior profile: user_id=%s", user_id)

    return result


# ═══════════════════════════════════════════════
# Hybrid verdict combiner
# ═══════════════════════════════════════════════

# Map ML 2-class labels to the 3-class engine labels
_ML_TO_ENGINE_LABEL = {
    "genuine": "genuine",
    "fraudulent": "likely_fraudulent",
}


def _combine_verdicts(rule_result: dict, ml_result: dict) -> dict:
    """
    Combine rule-engine and ML verdicts into a single hybrid result.

    Rules:
      - Rule engine is always the primary decision-maker.
      - ML is advisory — its label and confidence are attached to
        the response for transparency.
      - AGREEMENT: confidence gets a small boost (+0.05, capped at 0.99).
      - DISAGREEMENT — ML says fraudulent with ≥0.85 confidence but
        rules say genuine: escalate to suspicious as a safety net.
      - All other disagreements: trust the rule engine.
      - The explanation is always from the rule engine; a short ML
        note is appended when relevant.
    """
    # Start with a copy of the rule result
    combined = dict(rule_result)

    # Attach ML metadata so serializers can include it
    ml_available = ml_result.get("ml_available", False)
    ml_label_raw = ml_result.get("ml_label")           # "genuine" or "fraudulent"
    ml_conf = ml_result.get("ml_confidence", 0.0)

    combined["ml_available"] = ml_available
    combined["ml_label"] = ml_label_raw
    combined["ml_confidence"] = round(ml_conf, 4)

    if not ml_available or ml_label_raw is None:
        # No ML signal — return rule result unchanged
        combined["ml_agrees"] = None
        return combined

    # Map ML label to the engine's 3-class space for comparison
    ml_label_mapped = _ML_TO_ENGINE_LABEL.get(ml_label_raw, ml_label_raw)
    rule_label = combined["predicted_label"]

    # Check agreement:  genuine==genuine, or both are non-genuine
    rule_is_genuine = rule_label == "genuine"
    ml_is_genuine = ml_label_mapped == "genuine"
    agree = (rule_is_genuine == ml_is_genuine)
    combined["ml_agrees"] = agree

    if agree:
        # Both agree — small confidence boost
        boosted = min(combined["confidence_score"] + 0.05, 0.99)
        combined["confidence_score"] = round(boosted, 2)
        combined["model_version"] += "+ml"
        logger.debug("Rule+ML agree → confidence boosted to %.2f", boosted)

    else:
        # Disagreement — ML says fraud but rules say genuine?
        if not ml_is_genuine and rule_is_genuine and ml_conf >= 0.85:
            # Safety-net escalation: promote to suspicious
            combined["predicted_label"] = "suspicious"
            combined["confidence_score"] = round(
                max(combined["confidence_score"] - 0.10, 0.40), 2
            )
            combined["explanation"] += (
                " Note: our ML model flagged potential concerns with "
                f"this message ({int(ml_conf * 100)}% confidence). "
                "We recommend verifying through your MTN MoMo app."
            )
            combined["model_version"] += "+ml-escalated"
            logger.info(
                "ML escalation: rule=genuine → suspicious (ml_conf=%.2f)",
                ml_conf,
            )
        else:
            # All other disagreements — trust the rule engine
            combined["model_version"] += "+ml"
            logger.debug(
                "Rule+ML disagree (rule=%s, ml=%s conf=%.2f) — trusting rules",
                rule_label, ml_label_mapped, ml_conf,
            )

    return combined


def _build_success_response(check_id: int, result: dict, message: str,
                            warnings: list | None = None) -> dict:
    """Build the standard success response body for an analyzed check.

    Every response includes: success, message, warnings, data.
    This ensures the frontend can always check the same keys."""
    updated_check = get_message_check_by_id(check_id)
    return {
        "success": True,
        "message": message,
        "warnings": warnings or [],
        "data": {
            "message_check": _serialize_check(updated_check),
            "prediction": _serialize_prediction(result),
        },
    }


# ═══════════════════════════════════════════════
# Behavior profile updater
# ═══════════════════════════════════════════════

def _update_behavior_profile(user_id: int, parsed: dict) -> None:
    """
    Update the user's behavior profile with data from the latest check.

    Recalculates:
      - total_checks_count (increment)
      - avg_incoming_amount (running average)
      - max_incoming_amount (running max)
      - usual_senders (append new senders, keep last 50)
      - usual_transaction_types (append new types, dedupe)
    """
    profile = get_or_create_profile(user_id)

    count = profile.get("total_checks_count") or 0
    new_count = count + 1

    # Update amount stats
    amount = parsed.get("amount")
    avg = profile.get("avg_incoming_amount") or 0.0
    max_amt = profile.get("max_incoming_amount") or 0.0

    if amount is not None and amount > 0:
        # Running average: new_avg = (old_avg * count + new_amount) / new_count
        new_avg = round((avg * count + amount) / new_count, 2)
        new_max = max(max_amt, amount)
    else:
        new_avg = avg
        new_max = max_amt

    # Update usual senders (keep last 50 unique)
    usual_senders = list(profile.get("usual_senders", []))
    counterparty = parsed.get("counterparty_number")
    if counterparty and counterparty not in usual_senders:
        usual_senders.append(counterparty)
        usual_senders = usual_senders[-50:]  # keep most recent 50

    # Update usual transaction types (unique set)
    usual_types = list(profile.get("usual_transaction_types", []))
    txn_type = parsed.get("transaction_type")
    if txn_type and txn_type not in usual_types:
        usual_types.append(txn_type)

    update_profile(
        user_id,
        total_checks_count=new_count,
        avg_incoming_amount=new_avg,
        max_incoming_amount=new_max,
        usual_senders=usual_senders,
        usual_transaction_types=usual_types,
    )


# ═══════════════════════════════════════════════
# SMS Check Flow
# ═══════════════════════════════════════════════

def check_sms(user_id: int, raw_text: str, wallet_id: int | None = None) -> tuple[dict, int]:
    """
    Full verification flow for a pasted SMS message.

    Steps:
      1. Parse the SMS to extract structured fields
      2. Save a message_check row (status='pending')
      3. Write parsed fields onto the row
      4. Run authenticity engine → save prediction → update profile
      5. Return the result

    Returns (response_dict, http_status_code).
    """
    # 1. Parse the SMS
    logger.info("[SMS] Step 1 — Parsing: user_id=%s text_length=%d", user_id, len(raw_text))
    try:
        parsed = parse_sms(raw_text)
    except Exception:
        logger.exception("Parser crashed: user_id=%s", user_id)
        return {"success": False, "errors": ["Failed to parse SMS text."]}, 500

    # Phase-10: safe .get() on parser_confidence to prevent KeyError
    parser_conf = parsed.get("parser_confidence", 0.0)
    logger.info(
        "[SMS] Parsed OK: user_id=%s confidence=%.2f type=%s amount=%s mtn_txn_id=%s",
        user_id, parser_conf,
        parsed.get("transaction_type"), parsed.get("amount"),
        parsed.get("mtn_transaction_id"),
    )

    # 1b. Scope gate — skip fraud model for out-of-scope messages
    in_scope, scope_reason = is_in_scope(parsed)
    if not in_scope:
        logger.info(
            "[SMS] Out-of-scope: user_id=%s type=%s direction=%s reason=%r",
            user_id, parsed.get("transaction_type"), parsed.get("direction"), scope_reason,
        )
        # Still persist the check so the user has a history record
        check = create_message_check(
            user_id=user_id,
            source_channel="sms",
            wallet_id=wallet_id,
            raw_text=raw_text,
        )
        if not check:
            return {"success": False, "errors": ["Failed to save message check."]}, 500
        check_id = check["id"]
        _save_parsed_fields(check_id, parsed)
        update_message_check(check_id, status="out_of_scope")

        oos_result = _build_out_of_scope_result(parsed, scope_reason)
        updated_check = get_message_check_by_id(check_id)
        return {
            "success": True,
            "message": "Message saved. This transaction type is outside the fraud detection scope.",
            "warnings": [],
            "data": {
                "message_check": _serialize_check(updated_check),
                "prediction":    _serialize_prediction(oos_result),
            },
        }, 201

    # 2. Insert message_check row (status='pending')
    logger.info("[SMS] Step 2 — Inserting message_check: user_id=%s wallet_id=%s", user_id, wallet_id)
    check = create_message_check(
        user_id=user_id,
        source_channel="sms",
        wallet_id=wallet_id,
        raw_text=raw_text,
    )
    if not check:
        logger.error("[SMS] message_check INSERT failed: user_id=%s", user_id)
        return {"success": False, "errors": ["Failed to save message check."]}, 500

    check_id = check["id"]
    logger.info("[SMS] message_check created: check_id=%s", check_id)

    # 3. Write parsed fields onto the row
    logger.info("[SMS] Step 3 — Saving parsed fields: check_id=%s", check_id)
    _save_parsed_fields(check_id, parsed)

    # 4. Analyze → predict → update profile
    logger.info("[SMS] Step 4 — Running analysis: check_id=%s", check_id)
    try:
        result = _run_analysis(check_id, user_id, raw_text, parsed,
                               input_method="sms_paste")
    except Exception:
        logger.exception("[SMS] Analysis failed: check_id=%s user_id=%s", check_id, user_id)
        return {"success": False, "errors": ["Analysis engine failed. Please try again."]}, 500

    # 5. Build and return response
    logger.info("[SMS] Step 5 — Building response: check_id=%s label=%s",
                check_id, result["predicted_label"])

    # Collect any warnings for the frontend
    warnings = []
    if parser_conf < 0.4:
        warnings.append("Parser confidence is low — some extracted fields may be inaccurate.")

    body = _build_success_response(check_id, result, "SMS analyzed successfully.",
                                   warnings=warnings)
    return body, 201


# ═══════════════════════════════════════════════
# Screenshot Check Flow (scaffold)
# ═══════════════════════════════════════════════

def check_screenshot(
    user_id: int,
    screenshot_path: str,
    wallet_id: int | None = None,
    extracted_text: str | None = None,
    display_text: str | None = None,
    ocr_confidence: float = 0.0,
) -> tuple[dict, int]:
    """
    Screenshot-based verification flow.

    Args:
        extracted_text: OCR text that passed the usability gate — if provided,
                        runs the full parser + authenticity engine pipeline.
        display_text:   Raw OCR text (may not be usable for analysis) — always
                        stored on the row so the frontend can show it.
        ocr_confidence: OCR confidence score from the OCR service (0.0–1.0).

    If extracted_text is None, saves the check with status 'pending'.
    """
    logger.info("[SCREENSHOT] Step 1 — Creating message_check: user_id=%s wallet_id=%s",
                user_id, wallet_id)

    # 1. Create message_check row
    check = create_message_check(
        user_id=user_id,
        source_channel="screenshot",
        wallet_id=wallet_id,
        screenshot_path=screenshot_path,
    )
    if not check:
        logger.error("[SCREENSHOT] message_check INSERT failed: user_id=%s", user_id)
        return {"success": False, "errors": ["Failed to save message check."]}, 500

    check_id = check["id"]
    logger.info("[SCREENSHOT] message_check created: check_id=%s", check_id)

    # Always store display_text (or extracted_text) so the frontend can show it
    store_text = display_text or extracted_text
    if store_text:
        update_message_check(check_id, extracted_text=store_text, raw_text=store_text)
        logger.info("[SCREENSHOT] Stored OCR text on row: check_id=%s chars=%d",
                    check_id, len(store_text))

    # 2. If usable OCR text is available, run the full analysis pipeline
    if extracted_text and extracted_text.strip():
        logger.info("[SCREENSHOT] Step 2 — Usable OCR text (%d chars, conf=%.2f), running analysis: check_id=%s",
                    len(extracted_text), ocr_confidence, check_id)

        # Parse — if parser crashes, still return the saved record with the text
        try:
            parsed = parse_sms(extracted_text)
        except Exception:
            logger.exception("[SCREENSHOT] Parser crashed on OCR text: check_id=%s", check_id)
            updated_check = get_message_check_by_id(check_id)
            return {
                "success": True,
                "message": "Screenshot saved but text could not be parsed.",
                "warnings": ["The extracted text could not be parsed. Try the SMS tab to paste the message directly."],
                "data": {
                    "message_check": _serialize_check(updated_check),
                    "prediction": None,
                    "extracted_text": store_text,
                },
            }, 201

        _save_parsed_fields(check_id, parsed)
        logger.info("[SCREENSHOT] Parsed fields saved: check_id=%s", check_id)

        # Scope gate — same rule as SMS: only run analysis for incoming-credit alerts
        in_scope, scope_reason = is_in_scope(parsed)
        if not in_scope:
            logger.info("[SCREENSHOT] Out-of-scope: check_id=%s type=%s direction=%s",
                        check_id, parsed.get("transaction_type"), parsed.get("direction"))
            update_message_check(check_id, status="out_of_scope")
            oos_result = _build_out_of_scope_result(parsed, scope_reason)
            updated_check = get_message_check_by_id(check_id)
            body = {
                "success": True,
                "message": "Screenshot saved. This transaction type is outside the fraud detection scope.",
                "warnings": [],
                "data": {
                    "message_check": _serialize_check(updated_check),
                    "prediction":    _serialize_prediction(oos_result),
                    "extracted_text": store_text,
                    "ocr_confidence": round(ocr_confidence, 2),
                },
            }
            return body, 201

        # Run analysis — if engine crashes, still return parsed record
        try:
            result = _run_analysis(check_id, user_id, extracted_text, parsed,
                                   input_method="screenshot_ocr")
        except Exception:
            logger.exception("[SCREENSHOT] Analysis failed: check_id=%s", check_id)
            updated_check = get_message_check_by_id(check_id)
            return {
                "success": True,
                "message": "Screenshot saved and parsed, but analysis could not complete.",
                "warnings": ["The analysis engine encountered an error. Your message was still saved."],
                "data": {
                    "message_check": _serialize_check(updated_check),
                    "prediction": None,
                    "extracted_text": store_text,
                },
            }, 201

        logger.info("[SCREENSHOT] Analysis complete: check_id=%s label=%s conf=%.2f",
                    check_id, result["predicted_label"], ocr_confidence)

        body = _build_success_response(check_id, result, "Screenshot analyzed successfully.")
        body["data"]["extracted_text"] = store_text
        body["data"]["ocr_confidence"] = round(ocr_confidence, 2)
        # For uncertain screenshots whose verdict is only "suspicious",
        # surface a review suggestion so the UI can prompt the user
        # to manually verify rather than treating it like a confirmed fraud flag.
        if result.get("predicted_label") == "suspicious" and ocr_confidence < 0.60:
            body["data"]["ocr_review_suggested"] = True
        return body, 201

    # 3. No usable OCR text — save as pending for later processing
    # (display_text may still exist and is already stored on the row)
    logger.info("[SCREENSHOT] Step 2 — No usable OCR text, saving as pending: check_id=%s", check_id)
    updated_check = get_message_check_by_id(check_id)

    saved_name = os.path.basename(screenshot_path) if screenshot_path else None

    # Build a clear, actionable message based on what happened
    warnings = []
    if store_text:
        warnings.append("Text was extracted but does not appear to be an MTN MoMo message. Try the SMS tab to paste it directly.")
        msg = "Screenshot uploaded. Text extracted but not recognized as MoMo."
    else:
        warnings.append("No text could be extracted. Try a clearer image or paste the message in the SMS tab.")
        msg = "Screenshot uploaded. OCR could not extract text."

    return {
        "success": True,
        "message": msg,
        "warnings": warnings,
        "data": {
            "message_check": _serialize_check(updated_check),
            "prediction": None,
            "saved_filename": saved_name,
            "extracted_text": store_text,
        },
    }, 202


# ═══════════════════════════════════════════════
# History & Detail
# ═══════════════════════════════════════════════

def get_user_history(user_id: int, limit: int = 50) -> tuple[dict, int]:
    """
    Get all message checks for a user with prediction summaries.
    Returns newest first.
    """
    checks = get_checks_by_user(user_id, limit=limit)

    items = []
    for check in checks:
        # Phase-10: wrap each prediction fetch so one bad row
        # doesn't crash the entire history list
        try:
            prediction = get_prediction_by_check_id(check["id"])
        except Exception:
            logger.exception("Failed to load prediction for check_id=%s", check["id"])
            prediction = None

        items.append({
            "message_check": _serialize_check(check),
            "prediction_summary": {
                "predicted_label": prediction["predicted_label"],
                "confidence_score": prediction["confidence_score"],
                "model_version": prediction.get("model_version"),
            } if prediction else None,
        })

    return {
        "success": True,
        "count": len(items),
        "data": items,
    }, 200


def get_check_detail(check_id: int, user_id: int) -> tuple[dict, int]:
    """
    Get a single message check with full prediction detail.
    Only returns the check if it belongs to the requesting user.
    """
    check = get_message_check_by_id(check_id)
    if not check:
        return {"success": False, "errors": ["Message check not found."]}, 404

    if check["user_id"] != user_id:
        return {"success": False, "errors": ["Access denied."]}, 403

    prediction = get_prediction_by_check_id(check_id)

    return {
        "success": True,
        "data": {
            "message_check": _serialize_check(check),
            "prediction": _serialize_prediction_full(prediction) if prediction else None,
        },
    }, 200


# ═══════════════════════════════════════════════
# Serializers
# ═══════════════════════════════════════════════

def _serialize_check(check: dict | None) -> dict | None:
    """
    Convert a message_check row to a clean JSON-safe dict.
    Intentionally excludes screenshot_path (server internal).
    """
    if not check:
        return None
    return {
        "id": check["id"],
        "user_id": check["user_id"],
        "wallet_id": check.get("wallet_id"),
        "source_channel": check.get("source_channel"),
        "raw_text": check.get("raw_text"),
        "extracted_text": check.get("extracted_text"),
        "mtn_transaction_id": check.get("mtn_transaction_id"),
        "transaction_reference": check.get("transaction_reference"),
        "transaction_datetime": check.get("transaction_datetime"),
        "transaction_type": check.get("transaction_type"),
        "transaction_category": check.get("transaction_category"),
        "direction": check.get("direction"),
        "status": check.get("status"),
        "counterparty_name": check.get("counterparty_name"),
        "counterparty_number": check.get("counterparty_number"),
        # Phase-10: frontend-compatible aliases so sender column isn't always "—"
        "sender_name": check.get("counterparty_name"),
        "sender_number": check.get("counterparty_number"),
        "amount": check.get("amount"),
        "fee": check.get("fee"),
        "tax": check.get("tax"),
        "total_amount": check.get("total_amount"),
        "currency": check.get("currency"),
        "balance_before": check.get("balance_before"),
        "balance_after": check.get("balance_after"),
        "available_balance": check.get("available_balance"),
        "provider": check.get("provider"),
        "parser_confidence": check.get("parser_confidence"),
        "created_at": check.get("created_at"),
    }


def _serialize_prediction(result: dict) -> dict:
    """Serialize an engine result dict for the API response."""
    return {
        "predicted_label": result["predicted_label"],
        "confidence_score": result["confidence_score"],
        "explanation": result["explanation"],
        "format_risk_score": result["format_risk_score"],
        "behavior_risk_score": result["behavior_risk_score"],
        "balance_consistency_score": result["balance_consistency_score"],
        "sender_novelty_score": result["sender_novelty_score"],
        "model_version": result["model_version"],
        # Phase 10.3: ML model supplementary signal
        "ml_available": result.get("ml_available", False),
        "ml_label": result.get("ml_label"),
        "ml_confidence": result.get("ml_confidence", 0.0),
        "ml_agrees": result.get("ml_agrees"),
    }


def _serialize_prediction_full(prediction: dict) -> dict:
    """Serialize a DB prediction row for the detail endpoint."""
    base = {
        "id": prediction["id"],
        "message_check_id": prediction["message_check_id"],
        "predicted_label": prediction["predicted_label"],
        "confidence_score": prediction["confidence_score"],
        "explanation": prediction.get("explanation"),
        "format_risk_score": prediction.get("format_risk_score"),
        "behavior_risk_score": prediction.get("behavior_risk_score"),
        "balance_consistency_score": prediction.get("balance_consistency_score"),
        "sender_novelty_score": prediction.get("sender_novelty_score"),
        "model_version": prediction.get("model_version"),
        "created_at": prediction.get("created_at"),
    }
    # Phase 10.3: ML fields are in model_version string for DB rows
    # (not stored separately), so derive availability from version tag
    mv = prediction.get("model_version") or ""
    base["ml_available"] = "+ml" in mv
    base["ml_agrees"] = "+ml-escalated" not in mv if "+ml" in mv else None
    return base

"""
ML Scorer — loads the trained SMS authenticity model and scores messages.

Phase 10 Part 3: safe ML integration.

The trained model (fraud_model.pkl + tfidf.pkl) was built by
ml/train_model.py using:
  - TF-IDF on raw_text (max_features=500, bigrams)
  - 12 structured binary/numeric features

It outputs a 2-class prediction: "genuine" or "fraudulent".
This module wraps that model behind a simple score_message() API
that the message_check_service can call alongside the rule engine.

Design decisions:
  - Lazy-load model on first call (avoids slowing app startup if
    the .pkl files are not present yet).
  - If model files are missing or broken, return None — the caller
    falls back to the rule engine alone.
  - Returns a dict with ml_label, ml_confidence, and ml_available
    so the hybrid combiner always knows what happened.
"""

import os
import logging
import numpy as np
from config import get_config

logger = logging.getLogger(__name__)

# ── Paths to the trained model artifacts ─────────────────────────────
_cfg = get_config()
_ML_DIR = _cfg.MODEL_DIR
_MODEL_PATH = os.path.join(_ML_DIR, "fraud_model.pkl")
_TFIDF_PATH = os.path.join(_ML_DIR, "tfidf.pkl")

# ── Structured features (must match train_model.py exactly) ─────────
_STRUCTURED_FEATURES = [
    "amount",
    "fee",
    "balance_after",
    "available_balance",
    "has_valid_mtn_format",
    "has_balance_info",
    "has_fee_info",
    "has_transaction_id",
    "has_sender_name",
    "has_character_anomaly",
    "has_spacing_anomaly",
    "has_urgency_language",
]

# ── Lazy-loaded singletons ───────────────────────────────────────────
_model = None
_tfidf = None
_load_attempted = False


def _load_model():
    """Load model + vectorizer from disk.  Called once on first score."""
    global _model, _tfidf, _load_attempted
    _load_attempted = True

    if not os.path.exists(_MODEL_PATH) or not os.path.exists(_TFIDF_PATH):
        logger.warning(
            "ML model files not found (%s, %s). ML scoring disabled.",
            _MODEL_PATH, _TFIDF_PATH,
        )
        return False

    try:
        import joblib
        _model = joblib.load(_MODEL_PATH)
        _tfidf = joblib.load(_TFIDF_PATH)
        # Log model metadata for operational visibility
        model_size_kb = os.path.getsize(_MODEL_PATH) // 1024
        tfidf_size_kb = os.path.getsize(_TFIDF_PATH) // 1024
        model_mtime = os.path.getmtime(_MODEL_PATH)
        from datetime import datetime, timezone
        model_date = datetime.fromtimestamp(model_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        logger.info(
            "ML model loaded: %s (%dKB, trained=%s, tfidf=%dKB, classes=%s)",
            _MODEL_PATH, model_size_kb, model_date, tfidf_size_kb,
            list(getattr(_model, 'classes_', [])),
        )
        return True
    except Exception:
        logger.exception("Failed to load ML model — ML scoring disabled.")
        _model = None
        _tfidf = None
        return False


def _extract_structured_features(parsed: dict, raw_text: str) -> list[float]:
    """
    Build the 12-element structured feature vector from parsed fields
    and raw text, matching the columns in fraud_training_data.csv.
    """
    text_lower = raw_text.lower() if raw_text else ""

    amount = float(parsed.get("amount") or 0)
    fee = float(parsed.get("fee") or 0)
    balance_after = float(parsed.get("balance_after") or 0)
    available_balance = float(parsed.get("available_balance") or 0)

    # Binary flags — derived the same way the CSV was built
    has_valid_mtn_format = 1 if parsed.get("transaction_type") else 0
    has_balance_info = 1 if parsed.get("balance_after") is not None else 0
    has_fee_info = 1 if parsed.get("fee") is not None else 0
    has_transaction_id = 1 if parsed.get("mtn_transaction_id") else 0
    has_sender_name = 1 if parsed.get("counterparty_name") else 0

    # Character anomaly: mixed-case words that look like homoglyphs
    import re
    has_character_anomaly = 0
    for word in re.findall(r"\b[A-Za-z]{4,}\b", raw_text or ""):
        uppers = sum(1 for c in word if c.isupper())
        lowers = sum(1 for c in word if c.islower())
        if uppers >= 3 and 0 < lowers <= 2:
            has_character_anomaly = 1
            break

    # Spacing anomaly: tabs or excessive double-spaces
    has_spacing_anomaly = 1 if "\t" in (raw_text or "") else 0

    # Urgency language
    _URGENCY_WORDS = [
        "immediately", "urgent", "urgently", "expire", "act now",
        "within 24", "within 48", "will be blocked", "suspended",
    ]
    has_urgency_language = 0
    for word in _URGENCY_WORDS:
        if word in text_lower:
            has_urgency_language = 1
            break

    return [
        amount, fee, balance_after, available_balance,
        has_valid_mtn_format, has_balance_info, has_fee_info,
        has_transaction_id, has_sender_name,
        has_character_anomaly, has_spacing_anomaly, has_urgency_language,
    ]


# ═════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════

def score_message(raw_text: str, parsed: dict) -> dict:
    """
    Score a message using the trained ML model.

    Returns a dict:
        ml_available    bool   — whether the model produced a result
        ml_label        str    — "genuine" or "fraudulent" (or None)
        ml_confidence   float  — probability of the predicted class (or 0)

    If the model is not available, returns ml_available=False and the
    caller should rely on the rule engine alone.
    """
    # Lazy-load model on first call
    global _model, _tfidf, _load_attempted
    if not _load_attempted:
        _load_model()

    if _model is None or _tfidf is None:
        return {"ml_available": False, "ml_label": None, "ml_confidence": 0.0}

    try:
        from scipy.sparse import hstack, csr_matrix

        # Build TF-IDF features from raw text
        X_text = _tfidf.transform([raw_text or ""])

        # Build structured features
        struct = _extract_structured_features(parsed, raw_text)
        X_struct = csr_matrix([struct])

        # Combine
        X = hstack([X_text, X_struct])

        # Predict
        pred_label = _model.predict(X)[0]             # "genuine" or "fraudulent"
        pred_proba = _model.predict_proba(X)[0]       # [p_genuine, p_fraudulent]

        # Get the probability corresponding to the predicted class
        classes = list(_model.classes_)
        pred_idx = classes.index(pred_label)
        confidence = round(float(pred_proba[pred_idx]), 4)

        logger.info(
            "ML score: label=%s confidence=%.4f classes=%s proba=%s",
            pred_label, confidence, classes, pred_proba.tolist(),
        )

        return {
            "ml_available": True,
            "ml_label": pred_label,
            "ml_confidence": confidence,
        }

    except Exception:
        logger.exception("ML scoring failed — falling back to rule engine.")
        return {"ml_available": False, "ml_label": None, "ml_confidence": 0.0}

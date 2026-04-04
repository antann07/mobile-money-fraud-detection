"""
Fraud Engine – scores each transaction and returns a fraud prediction.

How it works (Phase 2 – rule-based):
  1. Extract features from the raw transaction data.
  2. Apply simple rules to flag suspicious patterns.
  3. Combine flags into a risk_level and anomaly_score.
  4. Return a prediction dict ready to be stored in fraud_predictions.

When a trained model (fraud_model.pkl) is available later,
swap _rule_based_score() for _ml_score() — the public API stays the same.
"""

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Path where a future ML model will live ───────────────────────────
MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "ml" / "model"
MODEL_PATH = MODEL_DIR / "fraud_model.pkl"

# ── Thresholds (tune these as you collect more data) ─────────────────
HIGH_AMOUNT_THRESHOLD = 5000       # amounts above this are considered large
BALANCE_DRAIN_THRESHOLD = 0.7      # draining ≥70% of balance is risky
UNUSUAL_HOUR_START = 23            # late-night window start
UNUSUAL_HOUR_END = 5               # late-night window end
HIGH_VELOCITY_THRESHOLD = 5        # >5 txns in 24 h is suspicious


# =====================================================================
# Feature extraction
# =====================================================================

def _extract_features(txn: dict) -> dict:
    """
    Pull the six scoring features from the raw transaction dict.

    Expected keys in `txn`:
      amount, balance_before, balance_after, transaction_time,
      direction, device_info, location_info
    """
    amount = float(txn.get("amount", 0))
    balance_before = float(txn.get("balance_before", 0) or 0)
    balance_after = float(txn.get("balance_after", 0) or 0)

    # ── balance_drain_ratio ──────────────────────────────────────────
    if balance_before > 0:
        balance_drain_ratio = round(amount / balance_before, 4)
    else:
        balance_drain_ratio = 0.0

    # ── amount_zscore (simplified: how far from a fixed average) ─────
    #    Replace 500 / 300 with real user stats once you have enough data.
    assumed_mean = 500.0
    assumed_std = 300.0
    amount_zscore = round((amount - assumed_mean) / assumed_std, 4)

    # ── txn_hour & txn_time_deviation ────────────────────────────────
    try:
        dt = datetime.fromisoformat(
            str(txn.get("transaction_time", "")).replace("Z", "+00:00")
        )
        txn_hour = dt.hour
    except (ValueError, AttributeError):
        txn_hour = 12                       # default to noon if unparseable

    # deviation from a "normal" midday hour (12)
    txn_time_deviation = round(abs(txn_hour - 12), 4)

    # ── is_new_device / is_new_location (simple presence check) ──────
    is_new_device = 1 if txn.get("device_info") else 0
    is_new_location = 1 if txn.get("location_info") else 0

    # ── velocity_1day (placeholder — wire to a real DB count later) ──
    velocity_1day = int(txn.get("velocity_1day", 0))

    return {
        "amount_zscore": amount_zscore,
        "txn_time_deviation": txn_time_deviation,
        "balance_drain_ratio": balance_drain_ratio,
        "is_new_device": is_new_device,
        "is_new_location": is_new_location,
        "velocity_1day": velocity_1day,
        # keep raw values for the rules below
        "_amount": amount,
        "_txn_hour": txn_hour,
        "_direction": txn.get("direction", ""),
    }


# =====================================================================
# Rule-based scoring
# =====================================================================

def _rule_based_score(features: dict) -> dict:
    """
    Apply simple rules and return a prediction dict.

    Rules checked:
      1. High amount + outgoing + large balance drain → suspicious
      2. Transaction during unusual hours (23:00–05:00) → suspicious
      3. New device or new location → raise risk
      4. High velocity (>5 txns/day) → suspicious
    """
    flags = []                       # human-readable reasons
    risk_points = 0                  # accumulator (0 = clean, ≥3 = high)

    amount = features["_amount"]
    direction = features["_direction"]
    txn_hour = features["_txn_hour"]

    # Rule 1 — large outgoing drain
    if (amount >= HIGH_AMOUNT_THRESHOLD
            and direction == "outgoing"
            and features["balance_drain_ratio"] >= BALANCE_DRAIN_THRESHOLD):
        risk_points += 3
        flags.append(
            f"Large outgoing transfer of GHS {amount:,.2f} uses "
            f"{features['balance_drain_ratio'] * 100:.0f}% of your balance"
        )

    # Rule 2 — unusual transaction hour
    if txn_hour >= UNUSUAL_HOUR_START or txn_hour <= UNUSUAL_HOUR_END:
        risk_points += 1
        flags.append(
            f"This transaction was made at {txn_hour}:00, "
            "outside normal hours"
        )

    # Rule 3 — new device
    if features["is_new_device"]:
        risk_points += 1
        flags.append(
            "The transaction came from a device we haven't seen before"
        )

    # Rule 4 — new location
    if features["is_new_location"]:
        risk_points += 1
        flags.append(
            "The transaction came from a location we haven't seen before"
        )

    # Rule 5 — high velocity
    if features["velocity_1day"] > HIGH_VELOCITY_THRESHOLD:
        risk_points += 2
        flags.append(
            f"{features['velocity_1day']} transactions in the last "
            "24 hours is higher than usual"
        )

    # ── Derive final labels ──────────────────────────────────────────
    if risk_points >= 3:
        risk_level = "high"
        prediction = "suspicious"
    elif risk_points >= 1:
        risk_level = "medium"
        prediction = "suspicious"
    else:
        risk_level = "low"
        prediction = "normal"

    # anomaly_label: 1 = anomaly (suspicious), -1 = normal
    anomaly_label = 1 if prediction == "suspicious" else -1

    # anomaly_score: negative = more anomalous (mimics Isolation Forest)
    anomaly_score = round(-0.1 * risk_points, 6)

    # Phase 10.2: build a clear, user-friendly explanation
    if not flags:
        explanation = "No unusual activity detected for this transaction."
    elif risk_level == "high":
        explanation = (
            "This transaction has several risk indicators: "
            + "; ".join(flags)
            + ". We recommend reviewing it carefully."
        )
    else:
        explanation = (
            "We found a minor note about this transaction: "
            + "; ".join(flags)
            + "."
        )

    return {
        "prediction": prediction,
        "anomaly_label": anomaly_label,
        "anomaly_score": anomaly_score,
        "risk_level": risk_level,
        "explanation": explanation,
    }


# =====================================================================
# (Future) ML-based scoring — uncomment when fraud_model.pkl is ready
# =====================================================================

# def _ml_score(features: dict) -> dict:
#     """Score using a trained sklearn model."""
#     import joblib
#     model = joblib.load(str(MODEL_PATH))
#     # Build a feature array matching training order, then:
#     # pred = model.predict([feature_array])[0]
#     # score = model.decision_function([feature_array])[0]
#     # ...
#     pass


# =====================================================================
# Public API
# =====================================================================

def score_transaction(transaction_data: dict) -> dict:
    """
    Score a single transaction and return the fraud prediction result.

    Parameters
    ----------
    transaction_data : dict
        Raw transaction fields — at minimum:
          amount, balance_before, balance_after, transaction_time,
          direction, device_info, location_info

    Returns
    -------
    dict with keys:
        prediction          "normal" or "suspicious"
        anomaly_label       1 (suspicious) or -1 (normal)
        anomaly_score       float (negative = more anomalous)
        risk_level          "low" / "medium" / "high"
        explanation          human-readable reason string
        amount_zscore        float
        txn_time_deviation   float
        balance_drain_ratio  float
        is_new_device        0 or 1
        is_new_location      0 or 1
        velocity_1day        int
    """
    # 1. Extract features
    features = _extract_features(transaction_data)

    # 2. Score (swap to _ml_score later)
    result = _rule_based_score(features)

    # 3. Attach computed feature values to the result
    result["amount_zscore"] = features["amount_zscore"]
    result["txn_time_deviation"] = features["txn_time_deviation"]
    result["balance_drain_ratio"] = features["balance_drain_ratio"]
    result["is_new_device"] = features["is_new_device"]
    result["is_new_location"] = features["is_new_location"]
    result["velocity_1day"] = features["velocity_1day"]

    logger.info(
        "Fraud score: prediction=%s risk=%s score=%.4f",
        result["prediction"], result["risk_level"], result["anomaly_score"],
    )

    return result

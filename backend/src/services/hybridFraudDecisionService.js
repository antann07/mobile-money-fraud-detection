/**
 * hybridFraudDecisionService.js — Hybrid fraud decision logic
 * ============================================================
 * Combines the rule-based risk score and the ML risk score into
 * one final decision: block, review, or allow.
 *
 * Weights: 60 % rules + 40 % ML.
 *
 * Decision logic:
 *   - HIGH risk (>= 70) + outgoing → block the transaction
 *   - MEDIUM risk (>= 30)          → mark as under review
 *   - LOW risk (< 30)              → allow the transaction
 */

// ── Outgoing transaction types (money leaving the wallet) ───────────
const OUTGOING_TYPES = ['transfer_out', 'cashout', 'withdrawal'];

// ── Score blending weights ──────────────────────────────────────────
const RULE_WEIGHT = 0.6;
const ML_WEIGHT   = 0.4;

// ── Risk thresholds ─────────────────────────────────────────────────
const HIGH_RISK_THRESHOLD   = 70;
const MEDIUM_RISK_THRESHOLD = 30;

/**
 * Evaluate the combined fraud decision.
 *
 * @param {Object}  params
 * @param {number}  params.ruleRiskScore   — 0–100 from the rule engine
 * @param {number}  params.mlRiskScore     — 0–100 from the ML model
 * @param {string}  params.transactionType — e.g. 'transfer_out', 'deposit'
 * @param {boolean} params.ruleSuspicious  — true if rules flagged it
 *
 * @returns {Object}
 *   { combinedRiskScore, finalDecision, trustLevel, blocked, blockReason, recommendedAction }
 */
const evaluate = ({ ruleRiskScore, mlRiskScore, transactionType, ruleSuspicious }) => {
  // ── 1. Blend the two scores ───────────────────────────────────────
  const combinedRiskScore = Math.min(100, Math.max(0,
    Math.round((ruleRiskScore * RULE_WEIGHT) + (mlRiskScore * ML_WEIGHT))
  ));

  const isOutgoing = OUTGOING_TYPES.includes(transactionType);

  // ── 2. Decision logic ─────────────────────────────────────────────
  let finalDecision     = 'allow';
  let trustLevel        = 'trusted';
  let blocked           = false;
  let blockReason       = '';
  let recommendedAction = 'No action required — transaction verified';

  if (combinedRiskScore >= HIGH_RISK_THRESHOLD && isOutgoing) {
    // HIGH risk + outgoing → block
    finalDecision     = 'block';
    trustLevel        = 'high_risk';
    blocked           = true;
    blockReason       = `Blocked: high-risk ${transactionType} (combined risk score ${combinedRiskScore}). AI-assisted fraud detection flagged this transaction.`;
    recommendedAction = 'Keep transaction blocked and escalate to analyst/admin for immediate review';

  } else if (combinedRiskScore >= MEDIUM_RISK_THRESHOLD) {
    // MEDIUM risk → under review
    finalDecision     = 'review';
    trustLevel        = 'warning';
    blocked           = false;
    blockReason       = '';
    recommendedAction = 'Review transaction within hold window and verify with customer';
  }
  // LOW risk → allow (defaults above)

  return {
    combinedRiskScore,
    finalDecision,
    trustLevel,
    blocked,
    blockReason,
    recommendedAction
  };
};

module.exports = { evaluate };

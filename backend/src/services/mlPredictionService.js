/**
 * mlPredictionService.js — Calls the Python ML microservice
 * ============================================================
 * Non-breaking: if the ML API is unreachable the caller receives
 * a safe fallback object and the system continues with rules only.
 */

const axios = require('axios');

const ML_API_URL = process.env.ML_API_URL || 'http://localhost:5001';
const ML_TIMEOUT_MS = 3000; // 3-second timeout so it never stalls the request

// Safe fallback when the ML API is unreachable — the backend never crashes
const FALLBACK_RESULT = {
  prediction:   0,
  label:        'legitimate',
  riskScore:    0,
  confidence:   0,
  modelVersion: 'fallback'
};

/**
 * Ask the Python ML API to classify a transaction.
 *
 * @param {Object} params
 * @param {number} params.amount
 * @param {string} params.transactionType
 * @param {string} params.transactionDirection
 * @param {number} params.hourOfDay
 * @param {number} params.isWeekend
 * @param {string} params.verificationStatus
 * @param {string} params.trustLevel
 * @param {number} params.availableForUse       (0 or 1)
 * @param {number} params.blocked               (0 or 1)
 * @param {number} params.hasLinkedSource        (0 or 1)
 *
 * @returns {Object} { prediction, label, riskScore, confidence, modelVersion }
 */
const predict = async (params) => {
  try {
    const response = await axios.post(`${ML_API_URL}/predict`, params, {
      timeout: ML_TIMEOUT_MS,
      headers: { 'Content-Type': 'application/json' }
    });
    return response.data;
  } catch (err) {
    // Log but never crash — return safe fallback and let rules handle it
    console.warn(`[mlPredictionService] ML API unavailable — using safe fallback. ${err.message}`);
    return FALLBACK_RESULT;
  }
};

/**
 * Build the feature payload the ML API expects from raw transaction data.
 */
const buildFeatures = ({ amount, transactionType, transactionDirection, timestamp, verificationStatus, trustLevel, availableForUse, blocked, linkedSourceTransaction }) => {
  const date = new Date(timestamp);
  return {
    amount,
    transactionType,
    transactionDirection,
    hourOfDay: date.getHours(),
    isWeekend: (date.getDay() === 0 || date.getDay() === 6) ? 1 : 0,
    verificationStatus,
    trustLevel,
    availableForUse: availableForUse ? 1 : 0,
    blocked: blocked ? 1 : 0,
    hasLinkedSource: linkedSourceTransaction ? 1 : 0
  };
};

module.exports = { predict, buildFeatures };

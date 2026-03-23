const Transaction = require('../models/Transaction');
const FraudAlert = require('../models/FraudAlert');
const FraudCase = require('../models/FraudCase');
const fraudDetectionService = require('../services/fraudDetectionService');
const mlPredictionService = require('../services/mlPredictionService');
const hybridFraudDecisionService = require('../services/hybridFraudDecisionService');

const HIGH_RISK_THRESHOLD = 70;
const MEDIUM_RISK_THRESHOLD = 30;

// ── MoMo transaction type classification ────────────────────────────
// These lists decide whether money is entering or leaving the wallet.
// The legacy 'transfer' type is treated as outgoing for safety.
const OUTGOING_TYPES = ['transfer_out', 'cashout', 'withdrawal', 'transfer'];
const INCOMING_TYPES = ['deposit', 'cashin', 'transfer_in'];

// ── Determine direction from transaction type ───────────────────────
// Returns 'incoming' or 'outgoing' based on the transaction type.
const getTransactionDirection = (transactionType) => {
  if (OUTGOING_TYPES.includes(transactionType)) return 'outgoing';
  return 'incoming';
};

// ── Deposit trust classification ────────────────────────────────────
// Rule-based trust classification (no ML). Uses riskScore to decide:
//
//   riskScore 0–29  → verified   + trusted    → funds available immediately
//   riskScore 30–69 → unverified + warning    → funds held 4 hours
//   riskScore 70+   → suspicious + high_risk  → funds held 24 hours
//
// For outgoing transactions trust fields still apply, but holds only
// make sense on incoming money so readonlyUntil is only set for those.
const classifyTrust = ({ riskScore, transactionDirection, timestamp }) => {
  // Default: clean transaction, fully trusted
  const result = {
    verificationStatus: 'verified',
    trustLevel: 'trusted',
    availableForUse: true,
    readonlyUntil: null,
    expiresAt: null
  };

  if (riskScore >= HIGH_RISK_THRESHOLD) {
    // ── High risk: suspicious ───────────────────────────────────
    result.verificationStatus = 'suspicious';
    result.trustLevel = 'high_risk';
    result.availableForUse = false;

    if (transactionDirection === 'incoming') {
      // Hold incoming funds for 24 hours; expire in 48 if never verified
      const holdUntil = new Date(timestamp);
      holdUntil.setHours(holdUntil.getHours() + 24);
      result.readonlyUntil = holdUntil;

      const expiry = new Date(timestamp);
      expiry.setHours(expiry.getHours() + 48);
      result.expiresAt = expiry;
    }
  } else if (riskScore >= MEDIUM_RISK_THRESHOLD) {
    // ── Medium risk: unverified ─────────────────────────────────
    result.verificationStatus = 'unverified';
    result.trustLevel = 'warning';
    result.availableForUse = false;

    if (transactionDirection === 'incoming') {
      // Short 4-hour hold for medium-risk incoming deposits
      const holdUntil = new Date(timestamp);
      holdUntil.setHours(holdUntil.getHours() + 4);
      result.readonlyUntil = holdUntil;
    }
  }
  // riskScore 0–29 keeps the defaults (verified, trusted, available)

  return result;
};

// ── Customer warning messages ───────────────────────────────────────
// Simple, plain-language messages for Ghanaian MoMo users
const getCustomerWarning = ({ transactionDirection, shouldBlockTransaction, isSuspicious, amount }) => {
  const formatted = `GHS ${Number(amount).toFixed(2)}`;

  if (shouldBlockTransaction && transactionDirection === 'outgoing') {
    return `We stopped your transaction of ${formatted} because a recent deposit ` +
      'has not been verified yet. This is for your protection. ' +
      'If someone asked you to return this money, it may be a scam. Do not send it.';
  }

  if (isSuspicious && transactionDirection === 'incoming') {
    return `You received ${formatted}. This money is being checked and ` +
      'will be available after verification. If someone calls you and asks ' +
      'you to return this money, DO NOT send it. It may be a scam. Your own money is safe.';
  }

  return '';
};

// ── Fraud explanation builder ───────────────────────────────────────
// Generates a human-readable explanation for analysts
const buildFraudExplanation = ({ transactionDirection, transactionType, amount, riskScore, fraudReason, followsSuspiciousDeposit, trustLevel }) => {
  if (!fraudReason && riskScore < MEDIUM_RISK_THRESHOLD) {
    return 'No suspicious pattern detected';
  }

  const parts = [];
  const formatted = `GHS ${Number(amount).toFixed(2)}`;

  if (transactionDirection === 'incoming' && riskScore >= MEDIUM_RISK_THRESHOLD) {
    parts.push(`Incoming ${transactionType} of ${formatted} flagged with risk score ${riskScore}.`);
    parts.push(`Trust level set to ${trustLevel.toUpperCase()}.`);
    if (riskScore >= HIGH_RISK_THRESHOLD) {
      parts.push('Funds frozen and placed on 24-hour hold pending verification.');
    } else {
      parts.push('Funds held for 4 hours pending review.');
    }
  }

  if (followsSuspiciousDeposit) {
    parts.push(`Outgoing ${transactionType} of ${formatted} follows an unverified suspicious deposit.`);
    parts.push('This matches the pattern of a MoMo reversal scam.');
  }

  if (fraudReason) {
    parts.push(`Detection reasons: ${fraudReason}.`);
  }

  return parts.join(' ') || 'No suspicious pattern detected';
};

// ── Recommended action builder ──────────────────────────────────────
// Plain-language next-step for analysts
const getRecommendedAction = ({ shouldBlockTransaction, isOutgoing, verificationStatus }) => {
  if (shouldBlockTransaction) {
    return 'Keep transaction blocked and escalate to analyst/admin for immediate review';
  }

  if (verificationStatus === 'suspicious') {
    return 'Hold funds, contact customer, and verify deposit source before releasing';
  }

  if (verificationStatus === 'unverified') {
    return 'Review transaction within hold window and verify with customer';
  }

  if (isOutgoing) {
    return 'Review outgoing transaction quickly and verify customer intent';
  }

  return 'No action required — transaction verified';
};

const evaluateTransactionWithFallback = async (transactionData) => {
  if (fraudDetectionService && typeof fraudDetectionService.evaluateTransaction === 'function') {
    return fraudDetectionService.evaluateTransaction(transactionData);
  }

  return {
    isSuspicious: false,
    fraudReason: '',
    riskScore: 0
  };
};

const getFraudPattern = ({ transactionType, followsSuspiciousDeposit, fraudReason }) => {
  const reason = (fraudReason || '').toLowerCase();

  if (transactionType === 'deposit' && reason.includes('deposit')) {
    return 'Suspicious deposit';
  }

  // Any outgoing type following a suspicious deposit is a potential scam chain
  if (followsSuspiciousDeposit && OUTGOING_TYPES.includes(transactionType)) {
    return `Suspicious ${transactionType} after suspicious deposit`;
  }

  if (reason.includes('repeated small transfers')) {
    return 'Repeated small transfers';
  }

  if (reason.includes('unusual hour')) {
    return 'Abnormal transaction time';
  }

  return 'Suspicious linked mobile money activity';
};

const isFraudPatternMatch = ({ transactionType, followsSuspiciousDeposit, fraudReason }) => {
  const reason = (fraudReason || '').toLowerCase();

  // Any outgoing type following a suspicious deposit is a pattern match
  if (followsSuspiciousDeposit && OUTGOING_TYPES.includes(transactionType)) {
    return true;
  }

  if (transactionType === 'deposit' && reason.includes('deposit')) {
    return true;
  }

  if (reason.includes('repeated small transfers')) {
    return true;
  }

  if (reason.includes('multiple withdrawals')) {
    return true;
  }

  if (reason.includes('unusual hour') || reason.includes('unusual login/device') || reason.includes('location differs')) {
    return true;
  }

  return false;
};


const createTransaction = async (req, res) => {
  try {
    const { userId, fullName, phoneNumber, transactionType, amount, location, deviceId, agentId } = req.body;
    const normalizedTransactionType = (transactionType || '').toLowerCase();
    const timestamp = new Date();

    // ── Step 1: Direction ───────────────────────────────────────────
    // Automatically assign "incoming" or "outgoing" from the type.
    const transactionDirection = getTransactionDirection(normalizedTransactionType);
    const isOutgoing = transactionDirection === 'outgoing';

    // ── Step 2: Fraud evaluation ────────────────────────────────────
    // Ask the fraud detection service for a risk score (falls back to
    // safe defaults if the service is not available).
    const fraudResult = await evaluateTransactionWithFallback({
      userId,
      amount,
      transactionType: normalizedTransactionType,
      location,
      timestamp,
      deviceId,
      agentId
    });

    let riskScore = Number(fraudResult.riskScore) || 0;
    let fraudReason = fraudResult.fraudReason || '';
    const serviceMarkedSuspicious = Boolean(fraudResult.isSuspicious);

    // ── Step 3: Check for recent suspicious deposits ────────────────
    // If the user received a suspicious deposit in the last 24 hours
    // and is now trying to send money out, boost the risk score.
    const oneDayAgo = new Date(timestamp);
    oneDayAgo.setHours(oneDayAgo.getHours() - 24);

    const suspiciousDeposit = await Transaction.findOne({
      userId,
      transactionType: { $in: INCOMING_TYPES },
      isSuspicious: true,
      timestamp: { $gte: oneDayAgo }
    }).sort({ timestamp: -1 });

    const followsSuspiciousDeposit = Boolean(suspiciousDeposit && isOutgoing);

    if (followsSuspiciousDeposit) {
      riskScore = Math.min(100, riskScore + 35);
      fraudReason = fraudReason
        ? `${fraudReason}; Outgoing transaction follows suspicious deposit`
        : 'Outgoing transaction follows suspicious deposit';
    }

    // ── Step 4: ML prediction ───────────────────────────────────────
    // Build features from the transaction data and call the Python ML
    // microservice. If the ML API is down, a safe fallback is returned
    // (prediction: 0, riskScore: 0) so the system continues with rules.
    const mlFeatures = mlPredictionService.buildFeatures({
      amount,
      transactionType: normalizedTransactionType,
      transactionDirection,
      timestamp,
      verificationStatus: 'unverified',
      trustLevel: 'warning',
      availableForUse: true,
      blocked: false,
      linkedSourceTransaction: followsSuspiciousDeposit ? suspiciousDeposit : null
    });

    const mlResult = await mlPredictionService.predict(mlFeatures);

    // ── Step 5: Hybrid fraud decision (rules + ML) ──────────────────
    // Combine the rule-based risk score and the ML risk score into a
    // single decision: block, review, or allow.
    const hybridDecision = hybridFraudDecisionService.evaluate({
      ruleRiskScore: riskScore,
      mlRiskScore: mlResult.riskScore,
      transactionType: normalizedTransactionType,
      ruleSuspicious: serviceMarkedSuspicious || followsSuspiciousDeposit
    });

    // Apply the hybrid result to the transaction variables
    riskScore = hybridDecision.combinedRiskScore;
    const shouldBlockTransaction = hybridDecision.blocked;
    const blockReason = hybridDecision.blockReason;

    // Determine if the transaction is suspicious
    let isSuspicious = serviceMarkedSuspicious || followsSuspiciousDeposit;
    if (mlResult.prediction === 1 && !isSuspicious) {
      isSuspicious = true;
      const pct = (mlResult.confidence * 100).toFixed(1);
      fraudReason = fraudReason
        ? `${fraudReason}; ML model flagged as suspicious (confidence ${pct}%)`
        : `ML model flagged as suspicious (confidence ${pct}%)`;
    }

    // Store ML prediction values for the database
    const mlPrediction   = mlResult.prediction;
    const mlRiskScore    = mlResult.riskScore;
    const mlConfidence   = mlResult.confidence;
    const mlModelVersion = mlResult.modelVersion || '';

    // Derive fraud-pattern flags (unchanged logic)
    const fraudPattern = getFraudPattern({
      transactionType: normalizedTransactionType,
      followsSuspiciousDeposit,
      fraudReason
    });
    const matchesFraudPattern = isSuspicious && isFraudPatternMatch({
      transactionType: normalizedTransactionType,
      followsSuspiciousDeposit,
      fraudReason
    });

    // ── Step 5b: Trust classification (uses blended score) ──────────
    const trustFields = classifyTrust({
      riskScore,
      transactionDirection,
      timestamp
    });
    // Override trustLevel with the hybrid decision value
    trustFields.trustLevel = hybridDecision.trustLevel;

    // ── Step 6: Recommended action & fraud explanation ──────────────
    // Use the hybrid decision's recommended action (AI-assisted)
    const recommendedAction = hybridDecision.recommendedAction;

    let fraudExplanation = buildFraudExplanation({
      transactionDirection,
      transactionType: normalizedTransactionType,
      amount,
      riskScore,
      fraudReason,
      followsSuspiciousDeposit,
      trustLevel: trustFields.trustLevel
    });

    // Enhance explanation to mention AI-assisted review when ML was used
    if (mlResult.modelVersion !== 'fallback') {
      fraudExplanation += ' [AI-assisted review applied]';
    }

    // ── Step 7: Customer-facing warning ─────────────────────────────
    const customerWarning = getCustomerWarning({
      transactionDirection,
      shouldBlockTransaction,
      isSuspicious,
      amount
    });

    // ── Step 8: Save to database ────────────────────────────────────
    const transaction = await Transaction.create({
      // Core fields
      userId,
      fullName,
      phoneNumber,
      transactionType: normalizedTransactionType,
      transactionDirection,
      amount,
      location,
      deviceId,
      agentId,
      timestamp,
      // Fraud flags
      isSuspicious,
      fraudReason,
      riskScore,
      fraudExplanation,
      recommendedAction,
      // Block flags
      blocked: shouldBlockTransaction,
      blockReason,
      status: shouldBlockTransaction ? 'blocked' : 'completed',
      // Trust classification
      verificationStatus: trustFields.verificationStatus,
      trustLevel: trustFields.trustLevel,
      availableForUse: trustFields.availableForUse,
      readonlyUntil: trustFields.readonlyUntil,
      expiresAt: trustFields.expiresAt,
      // Linking
      linkedSourceTransaction: followsSuspiciousDeposit ? suspiciousDeposit._id : null,
      // ML prediction fields
      mlPrediction,
      mlRiskScore,
      mlConfidence,
      mlModelVersion
    });

    // ── Step 9: Create FraudAlert if suspicious ─────────────────────
    let createdAlert = null;

    if (isSuspicious) {
      createdAlert = await FraudAlert.create({
        transactionId: transaction._id,
        userId: String(userId),
        alertType: 'Suspicious Transaction',
        severity: riskScore >= HIGH_RISK_THRESHOLD ? 'High' : 'Medium',
        description: fraudReason || 'Suspicious transaction detected',
        recommendedAction,
        status: 'new',
        riskScore
      });
    }

    // ── Step 10: Create or link FraudCase if pattern matches ────────
    let fraudCase = null;

    if (matchesFraudPattern) {
      const triggerTransaction = followsSuspiciousDeposit ? suspiciousDeposit : transaction;

      fraudCase = await FraudCase.findOne({
        triggerTransaction: triggerTransaction._id,
        status: { $in: ['new', 'under_review'] }
      });

      if (!fraudCase) {
        fraudCase = await FraudCase.create({
          customerName: fullName,
          phoneNumber,
          linkedTransactions: [triggerTransaction._id],
          triggerTransaction: triggerTransaction._id,
          fraudPattern,
          explanation: fraudReason || 'Potential fraud chain detected based on transaction behavior',
          riskScore,
          status: shouldBlockTransaction ? 'under_review' : 'new',
          recommendedAction
        });
      }

      const alreadyLinkedCurrent = fraudCase.linkedTransactions.some(
        (linkedId) => linkedId.toString() === transaction._id.toString()
      );

      if (!alreadyLinkedCurrent) {
        fraudCase.linkedTransactions.push(transaction._id);
      }

      fraudCase.fraudPattern = fraudPattern || fraudCase.fraudPattern;
      fraudCase.explanation = fraudReason || fraudCase.explanation;
      fraudCase.riskScore = Math.max(fraudCase.riskScore || 0, riskScore);

      if (shouldBlockTransaction) {
        fraudCase.status = 'under_review';
      }

      if (!fraudCase.recommendedAction) {
        fraudCase.recommendedAction = recommendedAction;
      }

      await fraudCase.save();

      transaction.linkedCaseId = fraudCase._id;
      await transaction.save();

      if (followsSuspiciousDeposit && !suspiciousDeposit.linkedCaseId) {
        suspiciousDeposit.linkedCaseId = fraudCase._id;
        await suspiciousDeposit.save();
      }
    }

    // ── Step 11: Send response ──────────────────────────────────────
    const responseBody = {
      transaction,
      riskScore,
      mlPrediction: mlResult.modelVersion !== 'fallback'
        ? { prediction: mlPrediction, riskScore: mlRiskScore, confidence: mlConfidence, modelVersion: mlModelVersion }
        : null,
      alert: createdAlert,
      fraudCase,
      message: shouldBlockTransaction
        ? 'Transaction created and blocked for fraud review'
        : 'Transaction created successfully'
    };

    if (customerWarning) {
      responseBody.customerWarning = customerWarning;
    }

    res.status(201).json(responseBody);
  } catch (error) {
    res.status(400).json({ message: error.message });
  }
};

const getTransactions = async (req, res) => {
  try {
    const transactions = await Transaction.find({});
    res.json(transactions);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

const getTransactionById = async (req, res) => {
  try {
    const transaction = await Transaction.findById(req.params.id);

    if (transaction) {
      res.json(transaction);
    } else {
      res.status(404).json({ message: 'Transaction not found' });
    }
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

module.exports = { createTransaction, getTransactions, getTransactionById };
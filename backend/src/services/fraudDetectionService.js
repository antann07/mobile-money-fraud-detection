const Transaction = require('../models/Transaction');

// ── MoMo transaction type categories ────────────────────────────────
// Money entering the wallet
const INCOMING_TYPES = ['deposit', 'cashin', 'transfer_in'];
// Money leaving the wallet
const OUTGOING_TYPES = ['transfer_out', 'cashout', 'withdrawal'];

const fraudDetectionService = {
  /**
   * Rule-based fraud detection for MoMo transactions.
   *
   * Accepts the raw transaction data and returns:
   *   { isSuspicious, fraudReason, riskScore }
   *
   * The controller passes `timestamp` (the model's date field).
   */
  evaluateTransaction: async (transactionData) => {
    let isSuspicious = false;
    let fraudReasons = [];
    let riskScore = 0;

    const { userId, amount, transactionType, location, timestamp, deviceId, agentId } = transactionData;

    // ── Rule 1: Unusually high amount ───────────────────────────────
    // Any single transaction above GHS 500 gets flagged.
    if (amount > 500) {
      isSuspicious = true;
      fraudReasons.push('Unusually high transaction amount');
      riskScore += 30;
    }

    // ── Rule 2: Suspicious deposit / cashin ─────────────────────────
    // Large deposits (>= GHS 1000) or deposits without an agent ID
    // could indicate a fake or fraudulent deposit.
    if ((transactionType === 'deposit' || transactionType === 'cashin') && (amount >= 1000 || !agentId)) {
      isSuspicious = true;
      fraudReasons.push('Possible fake or suspicious deposit pattern');
      riskScore += 35;
    }

    // ── Rule 3: Unusual time (midnight – 5 AM) ─────────────────────
    const hour = new Date(timestamp).getHours();
    if (hour >= 0 && hour <= 5) {
      isSuspicious = true;
      fraudReasons.push('Transaction at unusual hour');
      riskScore += 20;
    }

    // ── Rule 4: Repeated withdrawals / cashouts ─────────────────────
    // 3+ withdrawals or cashouts by the same user in the last hour.
    if (transactionType === 'withdrawal' || transactionType === 'cashout') {
      const oneHourAgo = new Date(timestamp);
      oneHourAgo.setHours(oneHourAgo.getHours() - 1);

      const recentOutgoing = await Transaction.countDocuments({
        userId,
        transactionType: { $in: ['withdrawal', 'cashout'] },
        timestamp: { $gte: oneHourAgo }
      });

      if (recentOutgoing >= 3) {
        isSuspicious = true;
        fraudReasons.push('Multiple withdrawals/cashouts in short period');
        riskScore += 40;
      }
    }

    // ── Rule 5: Repeated small transfer_out ─────────────────────────
    // 4+ small outgoing transfers (<= GHS 50) in the last hour is a
    // common money-laundering / structuring pattern.
    if (transactionType === 'transfer_out' && amount <= 50) {
      const oneHourAgo = new Date(timestamp);
      oneHourAgo.setHours(oneHourAgo.getHours() - 1);

      const recentSmallTransfers = await Transaction.countDocuments({
        userId,
        transactionType: 'transfer_out',
        amount: { $lte: 50 },
        timestamp: { $gte: oneHourAgo }
      });

      if (recentSmallTransfers >= 4) {
        isSuspicious = true;
        fraudReasons.push('Repeated small transfer_out in short period');
        riskScore += 30;
      }
    }

    // ── Rule 6: Suspicious outgoing after suspicious deposit ────────
    // If the user received a suspicious incoming transaction in the
    // last 24 hours and is now sending money out, raise the score.
    if (OUTGOING_TYPES.includes(transactionType)) {
      const oneDayAgo = new Date(timestamp);
      oneDayAgo.setHours(oneDayAgo.getHours() - 24);

      const recentSuspiciousDeposit = await Transaction.findOne({
        userId,
        transactionType: { $in: INCOMING_TYPES },
        isSuspicious: true,
        timestamp: { $gte: oneDayAgo }
      });

      if (recentSuspiciousDeposit) {
        isSuspicious = true;
        fraudReasons.push('Outgoing transaction follows a recent suspicious deposit');
        riskScore += 35;
      }
    }

    // ── Rule 7: Unusual device ──────────────────────────────────────
    // If this device has never been used by this user before, flag it.
    if (deviceId) {
      const knownDevices = await Transaction.distinct('deviceId', {
        userId,
        deviceId: { $ne: '' }
      });

      if (knownDevices.length > 0 && !knownDevices.includes(deviceId)) {
        isSuspicious = true;
        fraudReasons.push('Unusual login/device activity detected');
        riskScore += 20;
      }
    }

    // ── Rule 8: Unusual location ────────────────────────────────────
    // Compare this location to the user's most common recent location.
    const recentTransactions = await Transaction.find({ userId })
      .sort({ timestamp: -1 })
      .limit(5);

    const locationCounts = {};
    recentTransactions.forEach(tx => {
      if (tx.location) {
        locationCounts[tx.location] = (locationCounts[tx.location] || 0) + 1;
      }
    });

    const mostCommonLocation = Object.keys(locationCounts).reduce(
      (a, b) => (locationCounts[a] > locationCounts[b] ? a : b),
      null
    );

    if (mostCommonLocation && location !== mostCommonLocation) {
      isSuspicious = true;
      fraudReasons.push('Location differs from normal pattern');
      riskScore += 10;
    }

    // ── Cap & return ────────────────────────────────────────────────
    riskScore = Math.min(riskScore, 100);

    return {
      isSuspicious,
      fraudReason: fraudReasons.join('; '),
      riskScore
    };
  }
};

module.exports = fraudDetectionService;

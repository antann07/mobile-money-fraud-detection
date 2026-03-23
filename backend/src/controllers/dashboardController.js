const Transaction = require('../models/Transaction');
const FraudAlert = require('../models/FraudAlert');
const FraudCase = require('../models/FraudCase');

const getDashboardSummary = async (req, res) => {
  try {
    const totalTransactions = await Transaction.countDocuments({});
    const suspiciousTransactions = await Transaction.countDocuments({ isSuspicious: true });
    const totalFraudAlerts = await FraudAlert.countDocuments({});
    const resolvedAlerts = await FraudAlert.countDocuments({ status: 'resolved' });
    const totalFraudCases = await FraudCase.countDocuments({});
    const escalatedFraudCases = await FraudCase.countDocuments({ isEscalated: true });

    const totalAmount = await Transaction.aggregate([
      {
        $group: {
          _id: null,
          total: { $sum: '$amount' }
        }
      }
    ]);

    const recentTransactions = await Transaction.find({})
      .sort({ createdAt: -1 })
      .limit(5);

    const recentFraudAlerts = await FraudAlert.find({})
      .sort({ createdAt: -1 })
      .limit(5);

    const recentFraudCases = await FraudCase.find({})
      .populate('triggerTransaction')
      .sort({ createdAt: -1 })
      .limit(5);

    const summaryData = {
      totalTransactions,
      suspiciousTransactions,
      totalFraudAlerts,
      resolvedAlerts,
      totalFraudCases,
      escalatedFraudCases,
      recentTransactions,
      recentFraudAlerts,
      recentFraudCases,
      totalAmount: totalAmount.length > 0 ? totalAmount[0].total : 0
    };

    res.json(summaryData);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

const getRecentTransactions = async (req, res) => {
  try {
    const recentTransactions = await Transaction.find({})
      .sort({ createdAt: -1 })
      .limit(10);
    res.json(recentTransactions);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

const getRecentAlerts = async (req, res) => {
  try {
    const recentAlerts = await FraudAlert.find({})
      .sort({ createdAt: -1 })
      .limit(10);
    res.json(recentAlerts);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

module.exports = {
  getDashboardSummary,
  getRecentTransactions,
  getRecentAlerts
};

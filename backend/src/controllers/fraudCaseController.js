const FraudCase = require('../models/FraudCase');

const getFraudCases = async (req, res) => {
  try {
    const fraudCases = await FraudCase.find({})
      .populate('triggerTransaction')
      .populate('linkedTransactions')
      .sort({ createdAt: -1 });

    res.json(fraudCases);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

const getFraudCaseById = async (req, res) => {
  try {
    const fraudCase = await FraudCase.findById(req.params.id)
      .populate('triggerTransaction')
      .populate('linkedTransactions');

    if (!fraudCase) {
      return res.status(404).json({ message: 'Fraud case not found' });
    }

    res.json(fraudCase);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

module.exports = {
  getFraudCases,
  getFraudCaseById
};
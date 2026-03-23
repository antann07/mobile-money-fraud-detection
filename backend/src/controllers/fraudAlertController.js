const FraudAlert = require('../models/FraudAlert');

const createFraudAlert = async (req, res) => {
  try {
    const { transactionId, userId, alertType, severity, description, recommendedAction } = req.body;

    const fraudAlert = await FraudAlert.create({
      transactionId,
      userId,
      alertType,
      severity,
      description,
      recommendedAction,
      status: 'pending'
    });

    res.status(201).json(fraudAlert);
  } catch (error) {
    res.status(400).json({ message: error.message });
  }
};

const getFraudAlerts = async (req, res) => {
  try {
    const fraudAlerts = await FraudAlert.find({});
    res.json(fraudAlerts);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

const getFraudAlertById = async (req, res) => {
  try {
    const fraudAlert = await FraudAlert.findById(req.params.id);

    if (fraudAlert) {
      res.json(fraudAlert);
    } else {
      res.status(404).json({ message: 'Fraud alert not found' });
    }
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

const getAlertsByUserId = async (req, res) => {
  try {
    const fraudAlerts = await FraudAlert.find({ userId: req.params.userId });
    res.json(fraudAlerts);
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

const updateAlertStatus = async (req, res) => {
  try {
    const { status } = req.body;

    const fraudAlert = await FraudAlert.findByIdAndUpdate(
      req.params.id,
      { status },
      { new: true }
    );

    if (fraudAlert) {
      res.json(fraudAlert);
    } else {
      res.status(404).json({ message: 'Fraud alert not found' });
    }
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

module.exports = {
  createFraudAlert,
  getFraudAlerts,
  getFraudAlertById,
  getAlertsByUserId,
  updateAlertStatus
};

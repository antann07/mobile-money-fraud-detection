const mongoose = require('mongoose');

const fraudAlertSchema = new mongoose.Schema({
  transactionId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Transaction',
    required: true
  },
  userId: {
    type: String,
    required: true
  },
  alertType: {
    type: String,
    required: true
  },
  severity: {
    type: String,
    enum: ['Low', 'Medium', 'High'],
    default: 'Medium'
  },
  description: {
    type: String,
    required: true
  },
  recommendedAction: {
    type: String,
    required: true
  },
  status: {
    type: String,
    enum: ['new', 'pending', 'resolved'],
    default: 'new'
  },
  riskScore: {
    type: Number,
    min: 0,
    max: 100,
    default: 0
  }
}, {
  timestamps: true
});

module.exports = mongoose.model('FraudAlert', fraudAlertSchema);

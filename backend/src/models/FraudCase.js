const mongoose = require('mongoose');

const fraudCaseSchema = new mongoose.Schema({
  customerName: {
    type: String,
    required: true,
    trim: true
  },
  phoneNumber: {
    type: String,
    required: true,
    trim: true
  },
  linkedTransactions: [{
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Transaction'
  }],
  triggerTransaction: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Transaction',
    required: true
  },
  fraudPattern: {
    type: String,
    required: true
  },
  explanation: {
    type: String,
    required: true
  },
  riskScore: {
    type: Number,
    required: true,
    min: 0,
    max: 100
  },
  status: {
    type: String,
    enum: ['new', 'under_review', 'resolved', 'confirmed_fraud'],
    default: 'new'
  },
  recommendedAction: {
    type: String,
    default: ''
  }
}, {
  timestamps: true
});

module.exports = mongoose.model('FraudCase', fraudCaseSchema);
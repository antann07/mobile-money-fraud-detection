const mongoose = require('mongoose');

const transactionSchema = new mongoose.Schema({
  // ── Core identity ──────────────────────────────────────────────
  userId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  fullName: {
    type: String,
    required: true,
    trim: true
  },
  phoneNumber: {
    type: String,
    required: true,
    trim: true
  },

  // ── Transaction details ────────────────────────────────────────
  // Expanded to cover realistic MoMo flows:
  //   deposit   – cash handed to agent, credited to wallet
  //   cashin    – electronic top-up (bank → wallet, merchant credit)
  //   transfer_in  – money received from another MoMo user
  //   transfer_out – money sent to another MoMo user
  //   cashout   – wallet balance converted to cash at an agent
  //   withdrawal – ATM or bank-account withdrawal
  //   transfer  – (legacy) kept for backward compatibility
  transactionType: {
    type: String,
    enum: [
      'deposit',
      'cashin',
      'transfer_in',
      'transfer_out',
      'cashout',
      'withdrawal',
      'transfer'       // kept so existing data still validates
    ],
    required: true
  },
  // Whether money is coming in or going out of the wallet
  transactionDirection: {
    type: String,
    enum: ['incoming', 'outgoing'],
    default: 'incoming'
  },
  amount: {
    type: Number,
    required: true,
    min: 0
  },
  timestamp: {
    type: Date,
    required: true,
    default: Date.now
  },
  location: {
    type: String,
    required: true,
    trim: true
  },
  deviceId: {
    type: String,
    default: ''
  },
  agentId: {
    type: String,
    default: ''
  },

  // ── Transaction status ─────────────────────────────────────────
  status: {
    type: String,
    enum: ['pending', 'completed', 'failed', 'blocked'],
    default: 'pending'
  },

  // ── Fraud / risk flags ─────────────────────────────────────────
  isBlocked: {
    type: Boolean,
    default: false
  },
  blocked: {
    type: Boolean,
    default: false
  },
  blockReason: {
    type: String,
    default: ''
  },
  isSuspicious: {
    type: Boolean,
    default: false
  },
  riskScore: {
    type: Number,
    default: 0,
    min: 0,
    max: 100
  },
  fraudReason: {
    type: String,
    default: ''
  },
  fraudExplanation: {
    type: String,
    default: ''
  },
  recommendedAction: {
    type: String,
    default: ''
  },

  // ── Verification & trust ───────────────────────────────────────
  // Has the system verified this transaction's legitimacy?
  verificationStatus: {
    type: String,
    enum: ['verified', 'unverified', 'suspicious'],
    default: 'unverified'
  },
  // How much the system trusts this transaction (set by fraud engine)
  trustLevel: {
    type: String,
    enum: ['trusted', 'warning', 'high_risk'],
    default: 'warning'
  },

  // ── Hold / availability rules ──────────────────────────────────
  // Funds are read-only (non-withdrawable) until this date
  readonlyUntil: {
    type: Date,
    default: null
  },
  // Whether the funds can be spent right now (false = held/frozen)
  availableForUse: {
    type: Boolean,
    default: true
  },
  // Transaction record expires / auto-archives after this date
  expiresAt: {
    type: Date,
    default: null
  },

  // ── Linking ────────────────────────────────────────────────────
  // The inbound transaction that originally funded this outbound one
  linkedSourceTransaction: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Transaction',
    default: null
  },
  linkedFraudCaseId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'FraudCase',
    default: null
  },
  linkedCaseId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'FraudCase',
    default: null
  },

  // ── ML prediction fields ───────────────────────────────────────
  mlPrediction: {
    type: Number,
    enum: [0, 1],
    default: null
  },
  mlRiskScore: {
    type: Number,
    default: null,
    min: 0,
    max: 100
  },
  mlConfidence: {
    type: Number,
    default: null,
    min: 0,
    max: 1
  },
  mlModelVersion: {
    type: String,
    default: ''
  }
}, {
  timestamps: true
});

module.exports = mongoose.model('Transaction', transactionSchema);
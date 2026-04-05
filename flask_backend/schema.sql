-- ============================================
-- MTN Mobile Money Fraud Detection
-- Database Schema (SQLite)
-- ============================================
-- Phase 1: users, wallets
-- Phase 2: transactions, fraud_predictions (legacy)
-- Phase 6: message_checks, predictions, user_behavior_profiles, fraud_reviews
-- ============================================


-- ════════════════════════════════════════════
-- PHASE 1 — Auth & Wallets (unchanged)
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    username TEXT UNIQUE,                         -- optional unique login alias
    email TEXT UNIQUE NOT NULL,
    phone_number TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'customer',       -- 'customer' | 'admin' | 'reviewer'
    email_verified INTEGER NOT NULL DEFAULT 0,   -- 1 = email confirmed
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMP,                      -- NULL = not locked
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL,                    -- bcrypt hash of the reset token
    expires_at TIMESTAMP NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL,                    -- bcrypt hash of the verification token
    expires_at TIMESTAMP NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    wallet_number TEXT NOT NULL,
    provider TEXT NOT NULL,
    wallet_name TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);


-- ════════════════════════════════════════════
-- PHASE 2 — Legacy transaction tables (kept for backward compat)
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id INTEGER NOT NULL,
    transaction_reference TEXT,
    transaction_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    amount REAL NOT NULL,
    balance_before REAL,
    balance_after REAL,
    transaction_time TEXT NOT NULL,
    location_info TEXT,
    device_info TEXT,
    source_channel TEXT DEFAULT 'manual',
    raw_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (wallet_id) REFERENCES wallets(id)
);

CREATE TABLE IF NOT EXISTS fraud_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL,
    prediction TEXT NOT NULL,
    anomaly_label INTEGER NOT NULL,
    anomaly_score REAL NOT NULL,
    risk_level TEXT NOT NULL,
    explanation TEXT,
    amount_zscore REAL,
    txn_time_deviation REAL,
    balance_drain_ratio REAL,
    is_new_device INTEGER,
    is_new_location INTEGER,
    velocity_1day INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);


-- ════════════════════════════════════════════
-- PHASE 6 — MTN Message Authenticity Detection
-- ════════════════════════════════════════════

-- ── A. message_checks ───────────────────────
-- Core table: every SMS or screenshot the user submits for verification.
-- Stores both the raw input and fields extracted by the parser.
--
-- Required fields: user_id, source_channel
-- All parsed/extracted fields are optional (filled after parsing).

CREATE TABLE IF NOT EXISTS message_checks (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Who submitted & from which wallet
    user_id               INTEGER NOT NULL,
    wallet_id             INTEGER,                              -- optional link to user's wallet

    -- Input data
    source_channel        TEXT    NOT NULL DEFAULT 'sms',       -- 'sms' | 'screenshot'
    raw_text              TEXT,                                 -- pasted SMS body (if sms)
    screenshot_path       TEXT,                                 -- file path on server (if screenshot)
    extracted_text        TEXT,                                 -- OCR output from screenshot

    -- Parsed transaction fields (filled by the SMS/OCR parser)
    mtn_transaction_id    TEXT,                                 -- MTN internal txn ID from message
    transaction_reference TEXT,                                 -- reference code from message
    transaction_datetime  TEXT,                                 -- datetime string from message
    transaction_type      TEXT,                                 -- 'deposit' | 'withdrawal' | 'transfer' | 'payment' | 'airtime'
    transaction_category  TEXT,                                 -- 'mobile_money' | 'bank' | 'merchant' | 'utility'
    direction             TEXT    DEFAULT 'incoming',           -- 'incoming' | 'outgoing'
    status                TEXT    DEFAULT 'pending',            -- 'pending' | 'parsed' | 'verified' | 'flagged'

    -- Counterparty info
    counterparty_name     TEXT,                                 -- sender/receiver name from message
    counterparty_number   TEXT,                                 -- sender/receiver phone from message

    -- Financial details
    amount                REAL,
    fee                   REAL,
    tax                   REAL,
    total_amount          REAL,
    currency              TEXT    DEFAULT 'GHS',                -- 'GHS' for Ghana cedis
    balance_before        REAL,
    balance_after         REAL,
    available_balance     REAL,

    -- Provider & confidence
    provider              TEXT    DEFAULT 'MTN',                -- always 'MTN' for v1
    parser_confidence     REAL,                                 -- 0.0–1.0: how confident the parser is

    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)   REFERENCES users(id),
    FOREIGN KEY (wallet_id) REFERENCES wallets(id)
);


-- ── B. predictions ──────────────────────────
-- ML/rule-based verdict for each message check.
-- One prediction per message_check (1:1 relationship).
--
-- predicted_label: 'genuine' | 'suspicious' | 'likely_fraudulent'

CREATE TABLE IF NOT EXISTS predictions (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,

    message_check_id          INTEGER NOT NULL UNIQUE,          -- 1:1 with message_checks

    -- Verdict
    predicted_label           TEXT    NOT NULL,                  -- 'genuine' | 'suspicious' | 'likely_fraudulent'
    confidence_score          REAL    NOT NULL,                  -- 0.0–1.0 overall confidence
    explanation               TEXT,                             -- human-readable reason for the verdict

    -- Component risk scores (each 0.0–1.0)
    format_risk_score         REAL    DEFAULT 0.0,              -- how well the message matches known MTN format
    behavior_risk_score       REAL    DEFAULT 0.0,              -- deviation from user's normal behavior
    balance_consistency_score REAL    DEFAULT 0.0,              -- do the numbers add up?
    sender_novelty_score      REAL    DEFAULT 0.0,              -- is this a new/unknown sender?

    -- Tracking
    model_version             TEXT    DEFAULT 'v1',             -- which engine version produced this verdict

    created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (message_check_id) REFERENCES message_checks(id)
);


-- ── C. user_behavior_profiles ───────────────
-- Aggregated profile of each user's normal transaction patterns.
-- Updated periodically as new message_checks come in.
-- One profile per user (1:1 with users).

CREATE TABLE IF NOT EXISTS user_behavior_profiles (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,

    user_id                     INTEGER NOT NULL UNIQUE,        -- 1:1 with users

    -- Transaction amount patterns
    avg_incoming_amount         REAL    DEFAULT 0.0,
    max_incoming_amount         REAL    DEFAULT 0.0,

    -- Behavioral patterns (stored as JSON strings for SQLite compatibility)
    usual_senders               TEXT    DEFAULT '[]',           -- JSON array of known sender numbers
    usual_transaction_types     TEXT    DEFAULT '[]',           -- JSON array like ["deposit","transfer"]
    common_message_patterns     TEXT    DEFAULT '[]',           -- JSON array of regex/hash patterns

    -- Frequency & counts
    total_checks_count          INTEGER DEFAULT 0,              -- lifetime message checks submitted
    avg_transaction_frequency   REAL    DEFAULT 0.0,            -- avg checks per day

    created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id)
);


-- ── D. fraud_reviews ────────────────────────
-- Admin/reviewer audit trail for flagged messages.
-- Allows human override of ML predictions.
--
-- review_status: 'pending' | 'confirmed_fraud' | 'confirmed_genuine' | 'escalated'

CREATE TABLE IF NOT EXISTS fraud_reviews (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,

    message_check_id  INTEGER NOT NULL,
    predicted_label   TEXT    NOT NULL,                          -- copy of ML prediction at review time
    reviewer_label    TEXT,                                      -- human override: 'genuine' | 'suspicious' | 'likely_fraudulent'
    review_status     TEXT    NOT NULL DEFAULT 'pending',        -- 'pending' | 'confirmed_fraud' | 'confirmed_genuine' | 'escalated'
    notes             TEXT,                                      -- reviewer comments
    reviewed_by       INTEGER,                                  -- user_id of the admin/reviewer
    reviewed_at       TIMESTAMP,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,      -- when the review was queued

    FOREIGN KEY (message_check_id) REFERENCES message_checks(id),
    FOREIGN KEY (reviewed_by)      REFERENCES users(id)
);

-- ============================================
-- MTN Mobile Money Fraud Detection
-- Database Schema (PostgreSQL)
-- ============================================
-- Phase 1: users, wallets
-- Phase 2: transactions, fraud_predictions (legacy)
-- Phase 6: message_checks, predictions, user_behavior_profiles, fraud_reviews
-- ============================================


-- ════════════════════════════════════════════
-- PHASE 1 — Auth & Wallets
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    username TEXT UNIQUE,
    email TEXT UNIQUE NOT NULL,
    phone_number TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMP,
    role TEXT NOT NULL DEFAULT 'customer',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS wallets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    wallet_number TEXT NOT NULL,
    provider TEXT NOT NULL,
    wallet_name TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);


-- ════════════════════════════════════════════
-- PHASE 2 — Legacy transaction tables
-- ════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS message_checks (
    id                    SERIAL PRIMARY KEY,

    user_id               INTEGER NOT NULL,
    wallet_id             INTEGER,

    source_channel        TEXT    NOT NULL DEFAULT 'sms',
    raw_text              TEXT,
    screenshot_path       TEXT,
    extracted_text        TEXT,

    mtn_transaction_id    TEXT,
    transaction_reference TEXT,
    transaction_datetime  TEXT,
    transaction_type      TEXT,
    transaction_category  TEXT,
    direction             TEXT    DEFAULT 'incoming',
    status                TEXT    DEFAULT 'pending',

    counterparty_name     TEXT,
    counterparty_number   TEXT,

    amount                REAL,
    fee                   REAL,
    tax                   REAL,
    total_amount          REAL,
    currency              TEXT    DEFAULT 'GHS',
    balance_before        REAL,
    balance_after         REAL,
    available_balance     REAL,

    provider              TEXT    DEFAULT 'MTN',
    parser_confidence     REAL,

    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)   REFERENCES users(id),
    FOREIGN KEY (wallet_id) REFERENCES wallets(id)
);

CREATE TABLE IF NOT EXISTS predictions (
    id                        SERIAL PRIMARY KEY,

    message_check_id          INTEGER NOT NULL UNIQUE,

    predicted_label           TEXT    NOT NULL,
    confidence_score          REAL    NOT NULL,
    explanation               TEXT,

    format_risk_score         REAL    DEFAULT 0.0,
    behavior_risk_score       REAL    DEFAULT 0.0,
    balance_consistency_score REAL    DEFAULT 0.0,
    sender_novelty_score      REAL    DEFAULT 0.0,

    model_version             TEXT    DEFAULT 'v1',

    created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (message_check_id) REFERENCES message_checks(id)
);

CREATE TABLE IF NOT EXISTS user_behavior_profiles (
    id                          SERIAL PRIMARY KEY,

    user_id                     INTEGER NOT NULL UNIQUE,

    avg_incoming_amount         REAL    DEFAULT 0.0,
    max_incoming_amount         REAL    DEFAULT 0.0,

    usual_senders               TEXT    DEFAULT '[]',
    usual_transaction_types     TEXT    DEFAULT '[]',
    common_message_patterns     TEXT    DEFAULT '[]',

    total_checks_count          INTEGER DEFAULT 0,
    avg_transaction_frequency   REAL    DEFAULT 0.0,

    created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS fraud_reviews (
    id                SERIAL PRIMARY KEY,

    message_check_id  INTEGER NOT NULL,
    predicted_label   TEXT    NOT NULL,
    reviewer_label    TEXT,
    review_status     TEXT    NOT NULL DEFAULT 'pending',
    notes             TEXT,
    reviewed_by       INTEGER,
    reviewed_at       TIMESTAMP,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (message_check_id) REFERENCES message_checks(id),
    FOREIGN KEY (reviewed_by)      REFERENCES users(id)
);

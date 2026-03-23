# Mobile Money Fraud Detection — Research Documentation

> **System title:** Behavioural Anomaly Detection for Unauthorised Withdrawals in Mobile Money  
> **Model:** Isolation Forest (Unsupervised Anomaly Detection)  
> **Target domain:** Mobile Money Services (e.g. MTN MoMo, Telecel Cash, AirtelTigo Money — Ghana)  
> **Level:** Undergraduate Final Year Project · suitable for MSc expansion

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DATA LAYER                                        │
│  momo_fraud.db (SQLite)                                              │
│    ├── users          (user_id, phone, region, device_id …)         │
│    └── transactions   (txn_id, user_id, amount, timestamp …)        │
└───────────────────────────┬────────────────────────────────────────┘
                            │  feature_engineering.py
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  FEATURE ENGINEERING LAYER                           │
│  11 Behavioural Features:                                            │
│  amount, balance_before, balance_after, sim_swap_flag,              │
│  txn_hour, amount_zscore, txn_time_deviation,                       │
│  balance_drain_ratio, is_new_device, is_new_location,               │
│  velocity_1day                                                       │
│  Output → data/engineered_features.csv                              │
└───────────────────────────┬────────────────────────────────────────┘
                            │  train_model.py / predict_api.py
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│               ML DETECTION LAYER (Isolation Forest)                  │
│  • Trained on engineered_features.csv (unsupervised)                │
│  • Saved to model/isolation_forest.pkl                               │
│  • decision_function() → anomaly_score                              │
│  • score < 0  → suspicious  (anomaly_label = 1)                     │
│  • score ≥ 0  → normal      (anomaly_label = 0)                     │
└───────────────────────────┬────────────────────────────────────────┘
                            │  predict_api.py (Flask, port 5001)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     API LAYER  (REST — Flask)                        │
│  GET  /health    — system status + feature list + total predictions  │
│  POST /predict   — score one transaction → prediction + explanation  │
│  GET  /history   — paginated prediction log from SQLite             │
│  GET  /stats     — aggregate KPIs + hourly breakdown                │
│  GET  /export    — full history as downloadable CSV                  │
│  Persistence: data/predictions.db (SQLite)                          │
└───────────────────────────┬────────────────────────────────────────┘
                            │  HTTP fetch (JS)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│               MONITORING & DASHBOARD LAYER                           │
│  ml/dashboard.html  (single-file, no build step)                    │
│  • Transaction form with 11 inputs                                  │
│  • Half-donut Risk Gauge (Chart.js)                                 │
│  • Feature Bar Chart (absolute feature values)                      │
│  • Risk Summary (4-box grid: prediction, level, score, reason)      │
│  • Suspicious Signals (parsed explanation tags)                     │
│  • Pattern Summary (rule-based fraud category banner)               │
│  • Model Metadata (model name, type, confidence level)              │
│  • 5-KPI Fraud Summary (total, suspicious, fraud-rate, avg-score,  │
│    24h suspicious count)                                             │
│  • Hourly Bar Chart (suspicious txns by hour of day)                │
│  • Recent Transactions table (newest first)                         │
│  • Export CSV button → GET /export                                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Methodology

### 2.1 Problem Statement

Unauthorised withdrawals — transactions executed without the account holder's knowledge or consent — represent the dominant fraud vector in Mobile Money systems across sub-Saharan Africa. Traditional rule-based systems (e.g., velocity limits, blacklists) fail to detect sophisticated attacks such as SIM-swap fraud, where an attacker takes over a victim's phone number and immediately drains the balance.

This system addresses the problem through **unsupervised behavioural anomaly detection**: instead of requiring labelled fraud examples (which are scarce, imbalanced, and perpetually outdated), the model learns what _normal_ user behaviour looks like and flags deviations from that baseline.

---

### 2.2 Feature Engineering

Each raw transaction is enriched with seven behavioural deviation features computed per-user:

| Feature               | Type             | Description                                               |
| --------------------- | ---------------- | --------------------------------------------------------- |
| `amount`              | Raw              | Transaction amount in GHS                                 |
| `balance_before`      | Raw              | Account balance before the transaction                    |
| `balance_after`       | Raw / Derived    | Balance after transaction (source or computed)            |
| `sim_swap_flag`       | Raw (binary)     | 1 if the SIM was recently swapped (network flag)          |
| `txn_hour`            | Derived          | Hour of day (0–23) the transaction occurred               |
| `amount_zscore`       | Derived          | Standardised deviation from user's typical amount         |
| `txn_time_deviation`  | Derived          | Absolute deviation from user's average transaction hour   |
| `balance_drain_ratio` | Derived          | Fraction of balance withdrawn (`amount / balance_before`) |
| `is_new_device`       | Derived (binary) | 1 if this is the first transaction from this device ID    |
| `is_new_location`     | Derived (binary) | 1 if this is the first transaction from this region       |
| `velocity_1day`       | Derived          | Count of transactions in the prior 24 hours               |

These features collectively capture the **five fraud signals** most commonly associated with unauthorised withdrawals:

1. **Unusual amount** — `amount_zscore` > 2σ
2. **After-hours activity** — `txn_time_deviation` > 6 hours
3. **Full-balance drain** — `balance_drain_ratio` > 0.9
4. **SIM swap** — `sim_swap_flag` = 1
5. **New device / location** — `is_new_device` or `is_new_location` = 1

---

### 2.3 Model Selection — Isolation Forest

**Why Isolation Forest?**

- **No labelled data required.** Fraud labels are expensive, slow to collect, and class-imbalanced. Isolation Forest operates entirely unsupervised.
- **Linear time complexity.** Scales to millions of records with negligible inference latency.
- **Interpretable anomaly score.** The `decision_function()` output is a continuous score on a calibrated scale (positive = normal, negative = anomalous), enabling risk-tier assignment.
- **Robustness.** Unlike k-means or DBSCAN, Isolation Forest is explicitly designed for anomaly detection rather than clustering.

**How it works:**

Isolation Forest builds an ensemble of random binary trees. For each data point, it measures how many splits are needed to isolate that point from the rest of the dataset. Points that are isolated quickly (shallow trees) are anomalous — they occupy sparse regions of the feature space. The average path length across all trees yields the anomaly score.

**Key hyperparameters used:**

| Parameter       | Value    | Rationale                                           |
| --------------- | -------- | --------------------------------------------------- |
| `n_estimators`  | 100      | Sufficient ensemble diversity with acceptable speed |
| `contamination` | `"auto"` | Let sklearn estimate the contamination fraction     |
| `random_state`  | 42       | Reproducibility                                     |

---

### 2.4 Explainability

After prediction, the system computes a z-score for each feature relative to training-set statistics (mean and standard deviation). Features that deviate by more than 1σ are ranked by deviation magnitude, and the top 4 are assembled into a plain-English explanation sentence:

> _"This transaction was flagged because sim_swap_flag was unusually high (1.00); balance_drain_ratio was unusually high (0.97); amount_zscore was unusually high (3.20)."_

This satisfies the "right to explanation" principle central to responsible AI deployment and makes the system suitable for academic and regulatory review.

---

### 2.5 Persistence — SQLite

Predictions are stored in `data/predictions.db` with full feature values, result, and timestamp. This provides:

- **Durable history** — survives API restarts (unlike in-memory logging)
- **Aggregate analytics** — fraud rate, hourly distribution, 24h counts via SQL aggregation
- **Export capability** — full history downloadable as CSV for offline analysis
- **Audit trail** — every flagged transaction is traceable with its explanation

---

## 3. System Limitations

| #   | Limitation                                                      | Impact                                                                          | Mitigation                                                                   |
| --- | --------------------------------------------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 1   | **Unsupervised only** — no ground-truth labels used in training | Cannot measure Precision/Recall/F1 objectively                                  | Collect analyst-verified labels; add a supervised layer for hybrid detection |
| 2   | **Static model** — model does not update after deployment       | Concept drift: fraud patterns evolve; the model may become stale                | Schedule periodic retraining on new data (`retrain.py` cron job)             |
| 3   | **Fixed contamination estimate**                                | If true fraud rate diverges from the estimated fraction, recall/precision shift | Use a validation set with labels to tune `contamination`                     |
| 4   | **11 features only** — no graph/network features                | Coordinated fraud rings invisible to single-account analysis                    | Add graph features: shared devices, shared regions, fast chain transactions  |
| 5   | **SQLite concurrency**                                          | High-throughput production deployments will hit write locks                     | Migrate to PostgreSQL for concurrent multi-worker deployments                |
| 6   | **No authentication on API**                                    | Any host can POST to `/predict` or GET `/export`                                | Add API key middleware or JWT authentication before production               |
| 7   | **Single-server deployment** — no load balancing                | API is a single point of failure                                                | Deploy with gunicorn + nginx + systemd; or containerise with Docker          |
| 8   | **Dashboard loads all history**                                 | With 10,000+ records the table becomes unwieldy                                 | Add server-side pagination and a search/filter interface                     |

---

## 4. Future Improvements

### 4.1 Short-term (MSc-level extensions)

- **Hybrid model:** combine Isolation Forest (unsupervised) with a gradient-boosted classifier (XGBoost / LightGBM) trained on verified fraud labels. The IF flags anomalies; the supervised model ranks them by known fraud signatures.
- **SHAP integration:** replace z-score explanations with SHAP (SHapley Additive exPlanations) values for globally consistent feature attribution.
- **Online learning:** replace batch Isolation Forest with an incremental variant (e.g., `river` library's `forest.HalfSpaceTrees`) that updates online as new transactions arrive.
- **Graph features:** build a bipartite transaction graph (users ↔ devices/regions) and extract graph-level features (PageRank, community membership) as additional inputs.
- **Alert routing:** integrate an SMS/email alerting module that notifies account holders in real-time when a transaction is flagged.

### 4.2 Long-term (production / research publication)

- **Federated learning:** train local models at individual MNO nodes without sharing raw transaction data — preserves customer privacy while enabling cross-network fraud pattern sharing.
- **Regulatory compliance module:** generate a structured fraud report (PDF) per flagged transaction for submission to the Bank of Ghana or NCA.
- **Multi-class detection:** extend from binary (suspicious / normal) to multi-class (SIM swap, account takeover, device cloning, social engineering) using a multi-label classifier on verified fraud records.
- **Benchmark dataset:** publish the engineered feature set (anonymised) as an open dataset for the African mobile money fraud research community.

---

## 5. Project Structure

```
mobile-money-fraud-detection/
│
├── ml/
│   ├── feature_engineering.py     # Step 1 — load DB, compute 11 features, save CSV
│   ├── train_model.py             # Step 2 — train Isolation Forest, save .pkl
│   ├── predict_api.py             # Step 3 — Flask API (port 5001) with SQLite persistence
│   ├── behavioral_features.py     # Feature constants / helpers shared across scripts
│   ├── explain_anomalies.py       # Standalone explanation utility
│   ├── dashboard.html             # Single-file monitoring dashboard
│   ├── requirements.txt           # Python dependencies
│   ├── data/
│   │   ├── momo_fraud.db          # Source transaction database (SQLite)
│   │   ├── engineered_features.csv # Output of feature_engineering.py
│   │   ├── fraud_training_data.csv # (optional) labelled training data
│   │   └── predictions.db         # Persistent prediction history (SQLite)
│   └── model/
│       └── isolation_forest.pkl   # Saved trained model
│
├── backend/                       # Node.js/Express backend (separate service)
├── frontend/                      # React frontend (separate service)
├── RESEARCH.md                    # ← This file
└── DEPLOYMENT.md                  # Deployment and hosting guide
```

---

## 6. Reproducing the Full Pipeline

```bash
# 1. Create and activate the virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r ml/requirements.txt

# 3. Run feature engineering (reads momo_fraud.db, writes engineered_features.csv)
cd ml
python feature_engineering.py

# 4. Train the Isolation Forest (reads CSV, saves model/isolation_forest.pkl)
python train_model.py

# 5. Start the prediction API (auto-trains if model is missing)
python predict_api.py
# API now available at http://localhost:5001

# 6. Open the dashboard
# Open ml/dashboard.html in any browser — no build step required.
```

---

## 7. API Reference

### `POST /predict`

**Request body** (JSON):

```json
{
  "amount": 8000,
  "balance_before": 8500,
  "balance_after": 500,
  "sim_swap_flag": 1,
  "txn_hour": 2,
  "amount_zscore": 3.2,
  "txn_time_deviation": 9.5,
  "balance_drain_ratio": 0.94,
  "is_new_device": 1,
  "is_new_location": 1,
  "velocity_1day": 7
}
```

**Response** (JSON):

```json
{
  "prediction": "suspicious",
  "anomaly_label": 1,
  "anomaly_score": -0.183421,
  "explanation": "This transaction was flagged because sim_swap_flag was unusually high (1.00); balance_drain_ratio was unusually high (0.94)."
}
```

### `GET /stats`

```json
{
  "total": 142,
  "suspicious": 38,
  "normal": 104,
  "fraud_rate_pct": 26.76,
  "avg_score": 0.042,
  "avg_score_sus": -0.181,
  "recent_24h": { "total": 12, "suspicious": 4 },
  "hourly_counts": [{"hour": 2, "count": 7}, ...]
}
```

### `GET /history?limit=200&offset=0`

Returns an array of prediction records (oldest first by default).

### `GET /export`

Returns the full predictions table as `fraud_predictions.csv`.

### `GET /health`

```json
{
  "status": "ok",
  "model": "Isolation Forest",
  "detection_type": "Unsupervised Anomaly Detection",
  "features": ["amount", "balance_before", ...],
  "total_predictions": 142
}
```

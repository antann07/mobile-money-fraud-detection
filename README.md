# AI-Driven Mobile Money Fraud Detection System for Unauthorized Withdrawals

A machine learning system that detects fraudulent mobile money withdrawals using **Isolation Forest** anomaly detection, **behavioral feature engineering**, and a **real-time prediction API** — built with Python, Flask, React, and Node.js.

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Project Overview](#project-overview)
- [Features](#features)
- [System Architecture](#system-architecture)
- [Technologies Used](#technologies-used)
- [Project Structure](#project-structure)
- [How to Run Locally](#how-to-run-locally)
- [API Usage](#api-usage)
- [Screenshots](#screenshots)
- [Future Improvements](#future-improvements)
- [Author](#author)

---

## Problem Statement

Mobile money services like **MTN MoMo**, **Vodafone Cash**, and **AirtelTigo Money** are widely used in Ghana for everyday financial transactions. However, the rapid growth of mobile money has attracted fraud — particularly **unauthorized withdrawals** where attackers exploit SIM swaps, stolen credentials, or compromised devices to drain victims' accounts.

Traditional rule-based systems struggle to keep up with evolving fraud techniques. This project applies **unsupervised machine learning** (Isolation Forest) combined with **behavioral feature engineering** to detect suspicious withdrawal patterns in real time, helping protect mobile money users in Ghana.

---

## Project Overview

This system provides an end-to-end fraud detection pipeline:

1. **Synthetic transaction data** is generated to simulate real-world mobile money usage in Ghana
2. **Behavioral features** are engineered from raw transaction data (e.g., spending velocity, SIM swap flags, device/location anomalies)
3. An **Isolation Forest model** is trained to detect anomalous withdrawal patterns
4. A **Flask API** exposes the model for real-time fraud prediction
5. A **React + Node.js web application** provides a dashboard for analysts to monitor transactions, review fraud alerts, and manage cases
6. An **HTML dashboard** provides a standalone interface for ML prediction and history

---

## Features

- **Real-Time Fraud Prediction** — Submit a transaction and get an instant suspicious/normal verdict with anomaly score
- **Behavioral Feature Engineering** — 11 engineered features capture spending patterns, device changes, SIM swaps, and timing anomalies
- **Explainable Results** — Each prediction includes a plain-English explanation of why it was flagged
- **Risk Level Classification** — Transactions are ranked as HIGH RISK or LOW RISK
- **Prediction History** — All predictions are stored in SQLite and displayed in a live-updating table
- **Fraud Analytics Dashboard** — KPI summary with total, suspicious, normal counts and fraud rate
- **Hourly Suspicious Activity Chart** — Visual breakdown of suspicious transactions by hour of day
- **CSV Export** — Download full prediction history as a CSV report
- **Fraud Alert Management** — Create, review, and resolve fraud alerts
- **Fraud Case Tracking** — Group related alerts into investigation cases
- **Auto-Refresh** — Dashboard updates every 5 seconds automatically

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend Layer                       │
│                                                         │
│   React Dashboard          ML Dashboard (HTML)          │
│   (Vite + React Router)    (Chart.js + Vanilla JS)      │
│   Port: 5173               File: ml/dashboard.html      │
└──────────┬─────────────────────────┬────────────────────┘
           │                         │
           ▼                         ▼
┌──────────────────┐     ┌─────────────────────┐
│  Node.js Backend │     │    Flask ML API      │
│  (Express)       │     │    (predict_api.py)  │
│  Port: 5000      │────▶│    Port: 5001        │
│                  │     │                      │
│  • Auth (JWT)    │     │  • /predict          │
│  • Transactions  │     │  • /history          │
│  • Fraud Alerts  │     │  • /stats            │
│  • Fraud Cases   │     │  • /export           │
│  • Dashboard API │     │  • /health           │
└──────┬───────────┘     └──────────┬───────────┘
       │                            │
       ▼                            ▼
┌──────────────────┐     ┌──────────────────────┐
│    MongoDB        │     │  Isolation Forest    │
│    (Atlas)        │     │  Model (.pkl)        │
│                   │     │        +             │
│  • Users          │     │  SQLite Database     │
│  • Transactions   │     │  (fraud_monitor.db)  │
│  • Fraud Alerts   │     │                      │
│  • Fraud Cases    │     │  • prediction_history│
└───────────────────┘     └──────────────────────┘
```

---

## Technologies Used

| Layer         | Technology                                                     |
| ------------- | -------------------------------------------------------------- |
| **ML Model**  | Python, scikit-learn (Isolation Forest), pandas, NumPy, joblib |
| **ML API**    | Flask, Flask-CORS, SQLite3                                     |
| **Backend**   | Node.js, Express, Mongoose, JWT, bcrypt, Axios                 |
| **Frontend**  | React, Vite, React Router DOM                                  |
| **Dashboard** | HTML, CSS, JavaScript, Chart.js                                |
| **Database**  | MongoDB Atlas (application data), SQLite (prediction history)  |
| **DevOps**    | Git, GitHub, nodemon, gunicorn                                 |

---

## Project Structure

```
mobile-money-fraud-detection/
│
├── ml/                              # Machine Learning module
│   ├── predict_api.py               # Flask API (port 5001) — main prediction server
│   ├── withdrawal_api.py            # Flask API (port 5002) — withdrawal detection
│   ├── train_model.py               # Random Forest model training
│   ├── isolation_forest.py          # Isolation Forest training
│   ├── feature_engineering.py       # Behavioral feature engineering
│   ├── behavioral_features.py       # MongoDB-based feature extraction
│   ├── explain_anomalies.py         # SHAP / anomaly explanation
│   ├── db_helper.py                 # SQLite helper (init, save, query)
│   ├── dashboard.html               # Standalone ML dashboard
│   ├── requirements.txt             # Python dependencies
│   ├── data/
│   │   ├── engineered_features.csv  # Processed training data
│   │   ├── fraud_training_data.csv  # Labeled training data
│   │   └── fraud_monitor.db         # SQLite prediction history
│   └── model/
│       └── isolation_forest.pkl     # Trained model
│
├── backend/                         # Node.js API server
│   ├── package.json
│   └── src/
│       ├── app.js                   # Express app setup
│       ├── server.js                # Server entry point
│       ├── config/db.js             # MongoDB connection
│       ├── controllers/             # Route handlers
│       ├── models/                  # Mongoose schemas
│       ├── routes/                  # API routes
│       ├── services/                # Fraud detection logic
│       ├── middleware/              # Auth middleware
│       └── utils/                   # JWT token generation
│
├── frontend/                        # React dashboard
│   ├── package.json
│   ├── index.html
│   └── src/
│       ├── App.jsx                  # Main app with routing
│       ├── pages/                   # Dashboard, Transactions, Alerts, Cases
│       ├── components/              # Navbar, Sidebar
│       └── services/api.js          # Axios API client
│
└── README.md
```

---

## How to Run Locally

### Prerequisites

- **Python 3.10+** with pip
- **Node.js 18+** with npm
- **MongoDB Atlas** account (or local MongoDB)
- **Git**

### 1. Clone the Repository

```bash
git clone https://github.com/antann07/mobile-money-fraud-detection.git
cd mobile-money-fraud-detection
```

### 2. Set Up the ML API

```bash
# Create a virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install Python dependencies
pip install -r ml/requirements.txt

# Start the ML prediction API (port 5001)
cd ml
python predict_api.py
```

The API will automatically train the Isolation Forest model on first run if no saved model is found.

### 3. Set Up the Backend

```bash
# Open a new terminal
cd backend
npm install

# Create a .env file
# Add:
#   PORT=5000
#   MONGO_URI=your_mongodb_connection_string
#   JWT_SECRET=your_secret_key
#   ML_API_URL=http://localhost:5001

npm run dev
```

### 4. Set Up the Frontend

```bash
# Open a new terminal
cd frontend
npm install
npm run dev
```

The React app will be available at **http://localhost:5173**.

### 5. Open the ML Dashboard

Open `ml/dashboard.html` directly in your browser for the standalone ML prediction interface.

---

## API Usage

### Health Check

```bash
GET http://localhost:5001/health
```

### Predict Fraud

```bash
POST http://localhost:5001/predict
Content-Type: application/json

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

**Response:**

```json
{
  "prediction": "suspicious",
  "anomaly_label": 1,
  "anomaly_score": -0.1832,
  "risk_level": "HIGH RISK",
  "explanation": "This transaction was flagged because txn_time_deviation was unusually high (9.50); amount_zscore was unusually high (3.20); balance_drain_ratio was unusually high (0.94)."
}
```

### Get Prediction History

```bash
GET http://localhost:5001/history
```

### Get Fraud Statistics

```bash
GET http://localhost:5001/stats
```

### Export CSV Report

```bash
GET http://localhost:5001/export
```

---

## Screenshots

> _Screenshots of the application will be added here._

| Screen                                        | Description                                    |
| --------------------------------------------- | ---------------------------------------------- |
| ![Dashboard](screenshots/dashboard.png)       | ML Prediction Dashboard with fraud analytics   |
| ![Prediction](screenshots/prediction.png)     | Real-time prediction result with risk gauge    |
| ![History](screenshots/history.png)           | Prediction history table with color-coded rows |
| ![React App](screenshots/react-dashboard.png) | React frontend dashboard                       |

---

## Future Improvements

- **Real mobile money dataset** — Replace synthetic data with anonymized real-world transaction data from Ghanaian providers
- **Deep learning models** — Experiment with autoencoders and LSTM networks for sequence-based anomaly detection
- **Real-time streaming** — Integrate Apache Kafka or RabbitMQ for live transaction processing
- **SMS/Email alerts** — Notify users immediately when suspicious activity is detected
- **Multi-factor authentication** — Add OTP verification for high-risk transactions
- **Model retraining pipeline** — Automated scheduled retraining as new data accumulates
- **Mobile app** — Build a React Native companion app for on-the-go monitoring
- **Role-based access control** — Granular permissions for analysts, investigators, and administrators

---

## Author

**Anthony**

- GitHub: [@antann07](https://github.com/antann07)

---

> Built as an academic project exploring AI-driven fraud detection in Ghana's mobile money ecosystem.

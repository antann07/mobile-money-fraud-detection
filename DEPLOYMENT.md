# Deployment Guide

**AI-Driven Mobile Money Fraud Detection System**

This guide walks you through deploying both the Flask backend API and the static dashboard frontend on [Render](https://render.com).

---

## Architecture Overview

| Component               | Type          | Technology     | Render Service Type |
| ----------------------- | ------------- | -------------- | ------------------- |
| **Fraud Detection API** | Backend       | Python · Flask | **Web Service**     |
| **Dashboard Frontend**  | Monitoring UI | Static HTML/JS | **Static Site**     |

The dashboard (a single HTML file) calls the Flask API for predictions, history, and stats.

---

## Part 1 — Deploy the Flask Backend (Render Web Service)

### 1.1 Prerequisites

Before deploying, make sure your repository includes:

| File                  | Purpose                                         |
| --------------------- | ----------------------------------------------- |
| `ml/requirements.txt` | Python dependencies (Flask, scikit-learn, etc.) |
| `ml/predict_api.py`   | Flask application entry point                   |
| `ml/db_helper.py`     | SQLite helper (creates `fraud_monitor.db`)      |
| `ml/model/`           | Trained Isolation Forest model files (`.pkl`)   |
| `ml/data/`            | Training data and engineered features           |

### 1.2 Create the Web Service on Render

1. Go to [dashboard.render.com](https://dashboard.render.com) → **New** → **Web Service**
2. Connect your GitHub repository
3. Configure the service:

| Setting            | Value                                             |
| ------------------ | ------------------------------------------------- |
| **Name**           | `mobile-money-fraud-api` (or your preferred name) |
| **Region**         | Choose the closest to your users                  |
| **Branch**         | `main`                                            |
| **Root Directory** | `ml`                                              |
| **Runtime**        | `Python 3`                                        |
| **Build Command**  | `pip install -r requirements.txt`                 |
| **Start Command**  | `gunicorn predict_api:app`                        |

### 1.3 Environment Variables

Add these in the Render dashboard under **Environment**:

| Variable      | Value   | Required | Description                    |
| ------------- | ------- | -------- | ------------------------------ |
| `PORT`        | `10000` | No       | Render sets this automatically |
| `FLASK_DEBUG` | `false` | No       | Keep `false` in production     |

> Render automatically assigns a `PORT` environment variable. The `predict_api.py` reads it with:
>
> ```python
> port = int(os.environ.get("PORT", 5001))
> ```

### 1.4 Health Check

| Setting               | Value     |
| --------------------- | --------- |
| **Health Check Path** | `/health` |

The `/health` endpoint returns:

```json
{
  "status": "ok",
  "model": "Isolation Forest",
  "detection_type": "Unsupervised Anomaly Detection",
  "features": ["amount", "balance_before", "..."],
  "total_predictions": 42
}
```

### 1.5 API Endpoints Available After Deployment

| Method | Endpoint   | Description                      |
| ------ | ---------- | -------------------------------- |
| GET    | `/health`  | API status and model info        |
| POST   | `/predict` | Submit a transaction for scoring |
| GET    | `/history` | Retrieve all prediction history  |
| GET    | `/stats`   | Aggregate fraud statistics       |
| GET    | `/export`  | Download predictions as CSV      |

Your backend URL will look like:

```
https://mobile-money-fraud-api.onrender.com
```

---

## Part 2 — Deploy the Dashboard (Render Static Site)

### 2.1 File Structure

The dashboard is a single self-contained HTML file located at:

```
ml/
├── index.html          ← deploy this (or dashboard.html)
```

Both `index.html` and `dashboard.html` are identical. Render Static Sites serve `index.html` by default.

### 2.2 Connect the Dashboard to Your Backend

Before deploying, open `ml/index.html` and set `API_BASE` to your deployed backend URL:

```js
const API_BASE = "https://mobile-money-fraud-api.onrender.com";
//               ↑ Replace with your actual Render Web Service URL
```

> This single constant controls all API calls (`/health`, `/predict`, `/history`, `/stats`, `/export`).

### 2.3 Create the Static Site on Render

1. Go to [dashboard.render.com](https://dashboard.render.com) → **New** → **Static Site**
2. Connect the same GitHub repository
3. Configure:

| Setting               | Value                                  |
| --------------------- | -------------------------------------- |
| **Name**              | `fraud-detection-dashboard`            |
| **Branch**            | `main`                                 |
| **Root Directory**    | `ml`                                   |
| **Build Command**     | _(leave blank — no build step needed)_ |
| **Publish Directory** | `.`                                    |

4. Click **Create Static Site**

Your dashboard will be live at:

```
https://fraud-detection-dashboard.onrender.com
```

---

## Part 3 — Verify the Deployment

### 3.1 Check the Backend

```bash
# Health check
curl https://mobile-money-fraud-api.onrender.com/health

# Test a prediction
curl -X POST https://mobile-money-fraud-api.onrender.com/predict \
  -H "Content-Type: application/json" \
  -d '{
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
  }'

# Fetch stats
curl https://mobile-money-fraud-api.onrender.com/stats
```

### 3.2 Check the Dashboard

Open your Static Site URL in a browser. You should see:

- **API Health** → green "API is running" status
- **Transaction Form** → submit a test and see the prediction result
- **Recent Transactions** → table populates from `/history`
- **Fraud Summary** → KPI boxes update from `/stats`

---

## Common Deployment Errors & Fixes

| Error                                          | Cause                                     | Fix                                                                                                                                    |
| ---------------------------------------------- | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `ModuleNotFoundError: No module named 'flask'` | Missing dependency                        | Ensure `requirements.txt` is in the **Root Directory** (`ml/`) and the Build Command is `pip install -r requirements.txt`              |
| `FileNotFoundError: model/*.pkl`               | Model files not committed                 | Run `git add ml/model/ -f` and push — `.gitignore` may be excluding `.pkl` files                                                       |
| `gunicorn: command not found`                  | gunicorn not in requirements              | Confirm `gunicorn==23.0.0` is listed in `ml/requirements.txt`                                                                          |
| `CORS error` in browser console                | Backend doesn't allow dashboard origin    | `predict_api.py` uses `CORS(app)` which allows all origins — this should work. If you restrict origins later, add your Static Site URL |
| Dashboard shows "API unreachable"              | Wrong `API_BASE` URL                      | Open `ml/index.html`, update `API_BASE` to your actual Render Web Service URL, commit and push                                         |
| `/health` returns 502 Bad Gateway              | App failed to start                       | Check Render **Logs** tab — usually a missing file or import error                                                                     |
| Predictions disappear after redeploy           | SQLite is ephemeral on Render (see below) | Expected on free tier — consider upgrading to a persistent disk or PostgreSQL                                                          |

---

## Important: SQLite Limitations on Render

Render Web Services use an **ephemeral filesystem**. This means:

- The SQLite database (`ml/data/fraud_monitor.db`) is **created fresh** on every deploy or restart
- All prediction history stored in SQLite **will be lost** when the service redeploys
- This is a known limitation of Render's free tier

### What this means for your project

For **academic demos and presentations**, this is perfectly fine — the database works during the session and predictions are stored while the service is running.

### If you need persistent data later

| Option                     | Effort | Description                                                                          |
| -------------------------- | ------ | ------------------------------------------------------------------------------------ |
| **Render Persistent Disk** | Low    | Attach a disk to the Web Service ($0.25/GB/mo) — SQLite file persists across deploys |
| **PostgreSQL on Render**   | Medium | Create a free Render PostgreSQL database and update `db_helper.py` to use it         |
| **External database**      | Medium | Use a cloud database like MongoDB Atlas or Supabase                                  |

---

## Local Development (Quick Reference)

```bash
# Clone the repo
git clone https://github.com/antann07/mobile-money-fraud-detection.git
cd mobile-money-fraud-detection

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -r ml/requirements.txt

# Start the API locally
cd ml
python predict_api.py
# → http://localhost:5001

# Open the dashboard
# Open ml/dashboard.html in your browser
```

For local development, change `API_BASE` back to:

```js
const API_BASE = "http://127.0.0.1:5001";
```

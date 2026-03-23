# Deployment Guide — Mobile Money Fraud Detection API

## Overview

The system has two independently deployable components:

| Component                | Technology     | Default Port          |
| ------------------------ | -------------- | --------------------- |
| **Fraud Detection API**  | Python · Flask | 5001                  |
| **Monitoring Dashboard** | Static HTML    | any (open in browser) |

Both can run on a single low-cost Linux server (e.g., a DigitalOcean Droplet, AWS EC2 t3.micro, or an on-campus Ubuntu VM).

---

## Prerequisites

| Requirement         | Version      |
| ------------------- | ------------ |
| Python              | 3.9 or later |
| pip                 | latest       |
| (Optional) gunicorn | latest       |
| (Optional) nginx    | latest       |

---

## Option A — Local / Development (Windows or Linux)

```bash
# 1. Clone or copy the project
cd mobile-money-fraud-detection

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate it
.venv\Scripts\activate          # Windows PowerShell
# source .venv/bin/activate     # macOS / Linux

# 4. Install Python dependencies
pip install -r ml/requirements.txt

# 5. Run Feature Engineering (only needed once, or when raw data changes)
cd ml
python feature_engineering.py

# 6. Start the API
python predict_api.py
# → http://localhost:5001

# 7. Open the dashboard
# Open ml/dashboard.html in Chrome/Firefox — no server needed.
```

---

## Option B — Production on Linux (Ubuntu 22.04)

### Step 1 — Server Setup

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv nginx -y
```

### Step 2 — Upload Project Files

```bash
# From your local machine (replace IP with your server's address)
scp -r mobile-money-fraud-detection/ ubuntu@YOUR_SERVER_IP:/opt/fraud-api/
```

### Step 3 — Python Environment

```bash
cd /opt/fraud-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r ml/requirements.txt
pip install gunicorn
```

### Step 4 — Run Feature Engineering & Train Model

```bash
cd /opt/fraud-api/ml
python feature_engineering.py
python train_model.py
```

### Step 5 — Start the API with gunicorn

```bash
cd /opt/fraud-api/ml
gunicorn --workers 2 --bind 0.0.0.0:5001 predict_api:app
```

For persistent background operation, create a **systemd service**:

```ini
# /etc/systemd/system/fraud-api.service

[Unit]
Description=Mobile Money Fraud Detection API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/fraud-api/ml
Environment="ML_PORT=5001"
ExecStart=/opt/fraud-api/.venv/bin/gunicorn --workers 2 --bind 0.0.0.0:5001 predict_api:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable fraud-api
sudo systemctl start fraud-api
sudo systemctl status fraud-api
```

### Step 6 — nginx Reverse Proxy (optional but recommended)

```nginx
# /etc/nginx/sites-available/fraud-api

server {
    listen 80;
    server_name your-domain.com;   # or your server's IP

    # API proxy
    location /api/ {
        proxy_pass         http://127.0.0.1:5001/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
    }

    # Static dashboard
    location / {
        root /opt/fraud-api/ml;
        try_files /dashboard.html =404;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/fraud-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

> **HTTPS:** Add a free TLS certificate with `sudo certbot --nginx -d your-domain.com`.

---

## Option C — Docker (cross-platform)

Create `ml/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r ml/requirements.txt gunicorn

WORKDIR /app/ml
RUN python feature_engineering.py

EXPOSE 5001
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:5001", "predict_api:app"]
```

```bash
# Build
docker build -t fraud-api .

# Run
docker run -d -p 5001:5001 --name fraud-api fraud-api

# Persist predictions.db across restarts
docker run -d -p 5001:5001 \
  -v $(pwd)/ml/data:/app/ml/data \
  --name fraud-api fraud-api
```

---

## Environment Variables

| Variable       | Default                   | Description                                  |
| -------------- | ------------------------- | -------------------------------------------- |
| `ML_PORT`      | `5001`                    | Port the Flask/gunicorn server listens on    |
| `DATABASE_URL` | `sqlite:///momo_fraud.db` | SQLAlchemy URL for the source transaction DB |

---

## Dashboard Configuration

The dashboard reads the API from a hardcoded `API_BASE` variable near the top of the `<script>` block in `ml/dashboard.html`:

```js
const API_BASE = "http://127.0.0.1:5001"; // ← change this for production
```

For production, change it to your server's address:

```js
const API_BASE = "https://your-domain.com/api";
```

---

## Verifying the Deployment

```bash
# Health check
curl http://localhost:5001/health

# Test prediction
curl -X POST http://localhost:5001/predict \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 8000, "balance_before": 8500, "balance_after": 500,
    "sim_swap_flag": 1, "txn_hour": 2, "amount_zscore": 3.2,
    "txn_time_deviation": 9.5, "balance_drain_ratio": 0.94,
    "is_new_device": 1, "is_new_location": 1, "velocity_1day": 7
  }'

# Check stats
curl http://localhost:5001/stats

# Download history CSV
curl http://localhost:5001/export -o predictions.csv
```

---

## Security Checklist (before going live)

- [ ] Add API key authentication to all routes (Flask-HTTPAuth or a simple `X-API-Key` header check)
- [ ] Restrict CORS in `predict_api.py` to allowed origins instead of `*`
- [ ] Enable HTTPS with a valid TLS certificate (Let's Encrypt / certbot)
- [ ] Set `debug=False` in production (gunicorn handles this automatically)
- [ ] Restrict `/export` to authenticated administrators only
- [ ] Back up `data/predictions.db` regularly (cron job → offsite storage)
- [ ] Set server firewall rules: allow only ports 80, 443, and 22

---

## Performance Notes

| Scenario          | Recommendation                                                                                           |
| ----------------- | -------------------------------------------------------------------------------------------------------- |
| < 100 req/min     | gunicorn with 2 workers is sufficient                                                                    |
| 100–1,000 req/min | Increase workers to `2 × CPU cores + 1`; add nginx caching                                               |
| > 1,000 req/min   | Migrate to PostgreSQL; add Redis queue; deploy multiple API replicas behind a load balancer              |
| Batch scoring     | Use `predict_api.py` as a library and call `predict()` directly from a Python script instead of via HTTP |

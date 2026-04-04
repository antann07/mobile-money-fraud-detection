# ============================================================

# Production Verification Checklist

# MTN Mobile Money Fraud Detection System

# ============================================================

# Run through each section after `docker compose up --build -d`

# Mark each check: [x] pass [ ] fail

# ============================================================

## Prerequisites

Before starting, confirm:

```bash
# All containers are running
docker compose ps

# Expected: 3 services — db (healthy), backend (healthy), frontend (running)
```

| Item                     | Command / Action              | Expected            |
| ------------------------ | ----------------------------- | ------------------- |
| `.env` file exists       | `ls .env`                     | File present        |
| POSTGRES_PASSWORD is set | `grep POSTGRES_PASSWORD .env` | Non-empty value     |
| SECRET_KEY is set        | `grep SECRET_KEY .env`        | Not the default     |
| All 3 containers up      | `docker compose ps`           | 3 services, no Exit |

---

## 1. Backend Health and Startup

### 1.1 — Health endpoint responds

```bash
curl http://localhost:3000/api/health
```

| Check         | Expected           | Failure means                 |
| ------------- | ------------------ | ----------------------------- |
| HTTP status   | `200`              | Backend didn't start          |
| Response body | `{"status": "ok"}` | App factory crashed           |
| Response time | < 1 second         | DB connection or import issue |

**Common fixes:**

- `docker compose logs backend` — look for Python tracebacks
- Missing `SECRET_KEY` → Compose refuses to start (`:?` variable)
- `ModuleNotFoundError` → requirements.txt out of date, rebuild: `docker compose build backend`

### 1.2 — Gunicorn workers running

```bash
docker compose exec backend ps aux | grep gunicorn
```

| Check         | Expected             | Failure means                     |
| ------------- | -------------------- | --------------------------------- |
| Process count | 1 master + 4 workers | Gunicorn config issue             |
| User          | `appuser` (not root) | Dockerfile USER directive missing |

### 1.3 — Production mode active

```bash
docker compose exec backend python -c "from config import get_config; c = get_config(); print(c.ENV, c.DEBUG)"
```

| Check  | Expected           | Failure means                |
| ------ | ------------------ | ---------------------------- |
| Output | `production False` | FLASK_ENV not set in compose |

---

## 2. PostgreSQL Connectivity and Persistence

### 2.1 — Backend can reach the database

```bash
curl http://localhost:3000/api/health
```

If health passes, the DB is reachable (init_db runs on startup). For direct verification:

```bash
docker compose exec db psql -U momo -d fraud_detection -c "\dt"
```

| Check         | Expected                                 | Failure means                      |
| ------------- | ---------------------------------------- | ---------------------------------- |
| Tables listed | 8 tables (users, wallets, transactions…) | schema_pg.sql not applied          |
| No errors     | Clean output                             | DATABASE_URL wrong or DB not ready |

**Common fixes:**

- `docker compose logs db` — check for password auth failures
- `POSTGRES_USER` in `.env` must match the user in `DATABASE_URL` (auto-assembled in compose)
- If tables missing: restart backend — `docker compose restart backend`

### 2.2 — Data persists across restarts

```bash
# 1. Register a test user
curl -X POST http://localhost:3000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Test User","email":"persist@test.com","phone_number":"0241234567","password":"Test1234!"}'

# 2. Restart everything
docker compose down
docker compose up -d

# 3. Log in with the same user
curl -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"persist@test.com","password":"Test1234!"}'
```

| Check          | Expected             | Failure means                 |
| -------------- | -------------------- | ----------------------------- |
| Login succeeds | `200` with JWT token | pg_data volume not mounted    |
| After restart  | Same user accessible | Used `docker compose down -v` |

**Common fixes:**

- Never use `docker compose down -v` unless you want to wipe data
- Check `docker volume ls` — `pg_data` should exist

---

## 3. Frontend Production Serving (Nginx)

### 3.1 — SPA loads

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/
```

| Check       | Expected                    | Failure means                     |
| ----------- | --------------------------- | --------------------------------- |
| HTTP status | `200`                       | Nginx not running or build failed |
| Content     | HTML with React mount point | Vite build failed in Dockerfile   |

**Common fixes:**

- `docker compose logs frontend` — look for Nginx startup errors
- `npm run build` failing → check `docker compose build frontend` output

### 3.2 — Security headers present

```bash
curl -sI http://localhost:3000/ | grep -iE "x-frame|x-content|referrer|server"
```

| Check                  | Expected                                    |
| ---------------------- | ------------------------------------------- |
| X-Frame-Options        | `SAMEORIGIN`                                |
| X-Content-Type-Options | `nosniff`                                   |
| Referrer-Policy        | `strict-origin-when-cross-origin`           |
| Server                 | Should NOT show `nginx/1.27.x` (tokens off) |

### 3.3 — Gzip compression active

```bash
curl -sI -H "Accept-Encoding: gzip" http://localhost:3000/assets/ | grep -i content-encoding
```

| Check            | Expected                 |
| ---------------- | ------------------------ |
| Content-Encoding | `gzip` for JS/CSS assets |

---

## 4. API Routing and Deep-Link Refresh

### 4.1 — API proxy works through Nginx

```bash
# Must reach Flask through Nginx, not directly
curl http://localhost:3000/api/health
```

| Check    | Expected           | Failure means                  |
| -------- | ------------------ | ------------------------------ |
| Response | `{"status": "ok"}` | Nginx proxy_pass misconfigured |

**Common fixes:**

- Nginx can't resolve `backend` → Compose networking issue, run `docker compose up -d`
- 502 Bad Gateway → backend container crashed, check its logs

### 4.2 — SPA deep-link refresh

Open these URLs directly (paste in browser address bar or curl):

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/dashboard
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/check-message
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/admin/reviews
```

| Check           | Expected                                | Failure means               |
| --------------- | --------------------------------------- | --------------------------- |
| All return 200  | Nginx serves `index.html` via try_files | SPA fallback broken         |
| Content is HTML | React app HTML, not 404 page            | try_files directive missing |

**Note:** React Router handles the actual page rendering client-side. Nginx just needs to serve `index.html` for any non-file path.

---

## 5. Screenshot Upload and OCR

### 5.1 — Upload route accepts files through Nginx

```bash
# Get a token first
TOKEN=$(curl -s -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"persist@test.com","password":"Test1234!"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Upload a test image (create a 1x1 PNG first)
python -c "
import base64, pathlib
# Minimal valid PNG (1x1 red pixel)
png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==')
pathlib.Path('test_upload.png').write_bytes(png)
"

curl -X POST http://localhost:3000/api/message-checks/upload-screenshot \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test_upload.png"
```

| Check         | Expected                                   | Failure means                    |
| ------------- | ------------------------------------------ | -------------------------------- |
| HTTP status   | `200` or `201`                             | Upload route broken              |
| File saved    | Response references the screenshot path    | UPLOAD_DIR not writable          |
| OCR attempted | `extracted_text` field present (may be "") | Tesseract not installed in image |

**Common fixes:**

- `413 Request Entity Too Large` → `client_max_body_size` in nginx.conf too low (should be 10m)
- Permission denied → UPLOAD_DIR not owned by appuser, check Dockerfile `chown`
- OCR returns empty → expected for a 1px test image; real MTN screenshots should yield text

### 5.2 — Large upload rejected

```bash
# Create a file > 10 MB
python -c "open('big.bin','wb').write(b'x'*11_000_000)"

curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:3000/api/message-checks/upload-screenshot \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@big.bin"
```

| Check       | Expected | Failure means           |
| ----------- | -------- | ----------------------- |
| HTTP status | `413`    | Size limit not enforced |

---

## 6. Hybrid Rule + ML Prediction Flow

### 6.1 — SMS check returns a prediction

```bash
curl -X POST http://localhost:3000/api/message-checks/sms-check \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_text": "You have received GHS 500.00 from 0241234567. Your new balance is GHS 1,200.00. Transaction ID: 12345678. MTN MoMo.",
    "source_channel": "sms"
  }'
```

| Check                 | Expected                                             |
| --------------------- | ---------------------------------------------------- |
| HTTP status           | `200` or `201`                                       |
| `predicted_label`     | One of: `genuine`, `suspicious`, `likely_fraudulent` |
| `confidence_score`    | Float between 0.0 and 1.0                            |
| `format_risk_score`   | Present (≥ 0.0)                                      |
| `behavior_risk_score` | Present (≥ 0.0)                                      |
| `explanation`         | Non-empty human-readable string                      |

**Common fixes:**

- 500 error → check `docker compose logs backend` for ML model load failure
- Model files missing → seed the volume: `docker compose cp ./ml/model/. backend:/app/ml_models/`
- If ML model not found, the rule engine should still return a prediction (graceful fallback)

### 6.2 — Suspicious message triggers review queue

```bash
curl -X POST http://localhost:3000/api/message-checks/sms-check \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_text": "URGENT: You won GHS 10000! Click http://bit.ly/xyz to claim. MTN.",
    "source_channel": "sms"
  }'
```

| Check               | Expected                                              |
| ------------------- | ----------------------------------------------------- |
| `predicted_label`   | `suspicious` or `likely_fraudulent`                   |
| Review auto-created | Entry appears in `/api/reviews/flagged` (admin route) |

---

## 7. Admin Review Workflow

### 7.1 — Admin can view flagged checks

To test this, you need an admin user. Either promote one via DB or register and update:

```bash
# Direct DB approach
docker compose exec db psql -U momo -d fraud_detection \
  -c "UPDATE users SET role='admin' WHERE email='persist@test.com';"

# Re-login for fresh token
ADMIN_TOKEN=$(curl -s -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"persist@test.com","password":"Test1234!"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Fetch flagged queue
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:3000/api/reviews/flagged
```

| Check        | Expected                               | Failure means               |
| ------------ | -------------------------------------- | --------------------------- |
| HTTP status  | `200`                                  | Token invalid or not admin  |
| `data` array | Contains the suspicious check from 6.2 | Review auto-creation broken |

### 7.2 — Admin can submit a review verdict

```bash
# Use the message_check_id from the flagged list
CHECK_ID=<id_from_above>

curl -X POST "http://localhost:3000/api/reviews/$CHECK_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer_label": "confirmed_fraud",
    "review_status": "confirmed_fraud",
    "notes": "Obviously fake — phishing link present"
  }'
```

| Check           | Expected          | Failure means                |
| --------------- | ----------------- | ---------------------------- |
| HTTP status     | `200` or `201`    | Review route or model broken |
| `review_status` | `confirmed_fraud` | Update query failed          |
| `reviewed_by`   | Admin user's ID   | Auth context not passed      |

### 7.3 — Non-admin is rejected

```bash
# Use the original non-admin token (before promotion) or register a new user
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:3000/api/reviews/flagged
```

| Check       | Expected | Failure means            |
| ----------- | -------- | ------------------------ |
| HTTP status | `403`    | Admin guard not enforced |

---

## 8. Security Basics

### 8.1 — No sensitive data in response headers

```bash
curl -sI http://localhost:3000/api/health
```

| Check                    | Expected                               |
| ------------------------ | -------------------------------------- |
| No `Server: gunicorn`    | Nginx overrides upstream server header |
| No Nginx version         | `server_tokens off` working            |
| `X-Content-Type-Options` | `nosniff`                              |
| `X-Frame-Options`        | Present (`DENY` or `SAMEORIGIN`)       |

### 8.2 — Backend not directly accessible from host

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/api/health
```

| Check      | Expected           | Failure means                   |
| ---------- | ------------------ | ------------------------------- |
| Connection | Refused or timeout | Backend port is exposed to host |

The backend uses `expose: ["5001"]` (internal only), not `ports:`. If this returns 200, change `expose` to not use `ports` in docker-compose.yml.

### 8.3 — Auth tokens are validated

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer fake.token.here" \
  http://localhost:3000/api/auth/me
```

| Check       | Expected | Failure means           |
| ----------- | -------- | ----------------------- |
| HTTP status | `401`    | Token validation broken |

### 8.4 — CORS restricted in production

```bash
curl -sI -H "Origin: https://evil.com" http://localhost:3000/api/health | grep -i access-control
```

| Check                               | Expected                               |
| ----------------------------------- | -------------------------------------- |
| No `Access-Control-Allow-Origin: *` | CORS_ORIGINS is set to specific origin |

### 8.5 — Container runs as non-root

```bash
docker compose exec backend whoami
```

| Check  | Expected  | Failure means                     |
| ------ | --------- | --------------------------------- |
| Output | `appuser` | Dockerfile USER directive missing |

---

## 9. Restart Persistence Test

### 9.1 — Full stack restart

```bash
# Record current state
curl -s http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"persist@test.com","password":"Test1234!"}' | python -c "import sys,json; print('Before:', json.load(sys.stdin).get('token','FAIL')[:20])"

# Restart
docker compose restart

# Wait for health
sleep 20

# Verify data survived
curl -s http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"persist@test.com","password":"Test1234!"}' | python -c "import sys,json; print('After:', json.load(sys.stdin).get('token','FAIL')[:20])"
```

| Check                            | Expected              | Failure means             |
| -------------------------------- | --------------------- | ------------------------- |
| Both print tokens                | Data survived restart | Volume not persistent     |
| Health returns 200 after restart | Containers recovered  | Health check config issue |

### 9.2 — Single service recovery

```bash
docker compose kill backend
sleep 5
docker compose up -d backend
sleep 20
curl http://localhost:3000/api/health
```

| Check                               | Expected                        | Failure means                     |
| ----------------------------------- | ------------------------------- | --------------------------------- |
| Health returns 200                  | Backend recovered automatically | `restart: unless-stopped` missing |
| Frontend showed 50x during downtime | Error page, not Nginx default   | 50x.html not in build             |

---

## 10. Final Release Readiness

### Checklist Summary

Run through and mark each:

```
[ ] 1.1  Health endpoint responds 200
[ ] 1.2  Gunicorn 4 workers as appuser
[ ] 1.3  Production mode (not debug)
[ ] 2.1  PostgreSQL tables created (8 tables)
[ ] 2.2  Data persists after docker compose down/up
[ ] 3.1  Frontend SPA loads at :3000
[ ] 3.2  Security headers present
[ ] 3.3  Gzip compression on assets
[ ] 4.1  /api proxied through Nginx
[ ] 4.2  Deep-link refresh works (SPA fallback)
[ ] 5.1  Screenshot upload + OCR works
[ ] 5.2  Oversized upload rejected (413)
[ ] 6.1  SMS check returns prediction with scores
[ ] 6.2  Suspicious message creates review entry
[ ] 7.1  Admin can view flagged queue
[ ] 7.2  Admin can submit review verdict
[ ] 7.3  Non-admin gets 403 on review routes
[ ] 8.1  No server version leaked in headers
[ ] 8.2  Backend port not exposed to host
[ ] 8.3  Invalid JWT returns 401
[ ] 8.4  CORS not wildcard in production
[ ] 8.5  Container runs as non-root
[ ] 9.1  Full restart preserves data
[ ] 9.2  Single service recovers after kill
```

### Release Criteria

The system is **ready for controlled deployment** when:

| Criterion               | Minimum                                       |
| ----------------------- | --------------------------------------------- |
| Checklist items passing | All 23 items green                            |
| SECRET_KEY              | Random 32+ byte hex, not the default          |
| POSTGRES_PASSWORD       | Not `changeme`, not a dictionary word         |
| CORS_ORIGINS            | Set to actual deployment URL, not `*`         |
| Debug mode              | `FLASK_DEBUG=0`, `FLASK_ENV=production`       |
| ML models seeded        | At least the TF-IDF + LogisticRegression .pkl |
| Volumes                 | `pg_data`, `uploads`, `ml_models` all mounted |
| Logs accessible         | `docker compose logs` shows clean startup     |

### Post-Release Monitoring

After deployment, periodically check:

```bash
# Are all services healthy?
docker compose ps

# Any crash loops?
docker compose logs --since 1h backend | grep -i "error\|traceback"

# Disk space (uploads and PG data)
docker system df
```

# Pilot Deployment Guide — Vercel + Render + Neon

> End-to-end instructions for deploying the MTN Mobile Money Fraud Detection
> System to hosted services.  
> **Frontend**: Vercel (React/Vite)  
> **Backend**: Render (Flask/Gunicorn)  
> **Database**: Neon (PostgreSQL)

---

## Architecture

```
Browser
  │
  ▼
Vercel (frontend)              Render (backend)                Neon
 React SPA ───── HTTPS ──────► Flask API ──── PostgreSQL ─────► DB
 dist/                          flask_backend/                  sslmode=require
 VITE_API_BASE ──────────────►  /api/*
```

**Cross-origin flow**: The frontend on `https://your-app.vercel.app` makes
`fetch()` calls to `https://momo-fraud-api.onrender.com/api/*`. CORS is
handled by `flask-cors` on the backend, restricted to `CORS_ORIGINS`.

---

## Step 0: Prerequisites

- GitHub account with the repo pushed (all code, including `ml/model/*.pkl`)
- Accounts on [Vercel](https://vercel.com), [Render](https://render.com), [Neon](https://neon.tech)
- No local changes needed beyond what is already committed

---

## Step 1: Neon — Create the PostgreSQL Database

1. Go to [console.neon.tech](https://console.neon.tech) → **New Project**
2. Settings:
   - **Name**: `momo-fraud-detection`
   - **Region**: `US East` (or closest to Render's region — Oregon)
   - **PostgreSQL version**: 16 (or latest)
3. After creation, go to **Dashboard → Connection Details**
4. Copy the **connection string** (pooled, with `?sslmode=require`):
   ```
   postgresql://neondb_owner:PASSWORD@ep-XXXXX.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
5. **No manual table creation needed** — the Flask backend runs
   `schema_pg.sql` automatically on first startup via `init_db()`.

---

## Step 2: Render — Deploy the Backend

### 2A. Create the Service

1. Go to [dashboard.render.com](https://dashboard.render.com) → **New → Web Service**
2. Connect your GitHub repo
3. Settings:

| Setting | Value |
|---|---|
| **Name** | `momo-fraud-api` |
| **Region** | Oregon (US West) |
| **Runtime** | Python |
| **Branch** | `main` (or your default branch) |
| **Root Directory** | _(leave blank — the build script handles paths)_ |
| **Build Command** | `chmod +x build.sh && ./build.sh` |
| **Start Command** | `cd flask_backend && gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 120 --graceful-timeout 30 --max-requests 1000 --max-requests-jitter 50 --access-logfile - --error-logfile -` |
| **Health Check Path** | `/api/health` |
| **Plan** | Free (or paid if you need persistent uploads) |

### 2B. Set Environment Variables

In the Render dashboard → your service → **Environment** tab, add:

| Key | Value | Notes |
|---|---|---|
| `FLASK_ENV` | `production` | |
| `FLASK_DEBUG` | `0` | |
| `PYTHON_VERSION` | `3.12.0` | |
| `SECRET_KEY` | _(generate: `python -c "import secrets; print(secrets.token_hex(32))"`)_ | **Required.** 64-char hex. |
| `JWT_SECRET` | _(generate separately)_ | **Required.** Different from SECRET_KEY. |
| `DATABASE_URL` | `postgresql://neondb_owner:...?sslmode=require` | Neon connection string from Step 1. |
| `CORS_ORIGINS` | `https://your-app.vercel.app` | Your Vercel URL (no trailing slash). |
| `FRONTEND_URL` | `https://your-app.vercel.app` | Same as CORS_ORIGINS. Used in email links. |
| `TOKEN_EXPIRY_HOURS` | `12` | |
| `LOG_LEVEL` | `INFO` | |
| `MODEL_DIR` | `/opt/render/project/src/flask_backend/ml_models` | Where `build.sh` copies ML models. |
| `UPLOAD_DIR` | `/opt/render/project/src/flask_backend/uploads/screenshots` | Explicit path for uploads. |

> **If using render.yaml**: You can skip manual creation. Go to **Blueprints** →
> connect the repo → Render reads `render.yaml` and sets everything except
> `DATABASE_URL`, `CORS_ORIGINS`, and `FRONTEND_URL` (set those manually as
> they have `sync: false`).

### 2C. Disk (Paid Plans Only)

If you want uploaded screenshots to persist across deploys:
- Add a **Disk**: Mount path `/opt/render/project/src/flask_backend/uploads`, 1 GB
- Free tier: uploads work at runtime but are lost when the service redeploys

### 2D. Deploy

Click **Deploy** or push to your branch. Watch the logs for:
```
=== Installing Python dependencies ===
=== Copying ML models ===
=== Build complete ===
```
Then the start command runs. Look for:
```
[STARTUP] Database: OK (PostgreSQL)
[STARTUP] Schema tables: OK (10 tables verified)
[STARTUP] ML model: OK (loaded, ...)
```

Your backend URL will be: `https://momo-fraud-api.onrender.com`

---

## Step 3: Vercel — Deploy the Frontend

### 3A. Create the Project

1. Go to [vercel.com](https://vercel.com) → **New Project**
2. Import your GitHub repo
3. Settings:

| Setting | Value |
|---|---|
| **Framework Preset** | Vite |
| **Root Directory** | `frontend` |
| **Build Command** | `npm run build` (auto-detected) |
| **Output Directory** | `dist` (auto-detected) |

### 3B. Set Environment Variables

In Vercel → your project → **Settings → Environment Variables**, add:

| Key | Value | Environment |
|---|---|---|
| `VITE_API_BASE` | `https://momo-fraud-api.onrender.com` | Production |

> This overrides `frontend/.env.production`. Use your actual Render backend URL.
> **No trailing slash.**

### 3C. Deploy

Click **Deploy**. Vercel runs `npm run build` → outputs to `dist/` → serves via
their CDN. The `vercel.json` in `frontend/` handles:
- SPA routing (all paths → `index.html`)
- Asset caching (`Cache-Control: immutable` for hashed assets)
- Security headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy)

Your frontend URL will be: `https://your-app.vercel.app`

### 3D. Update Backend CORS

After getting your Vercel URL, go back to Render → Environment → update:
- `CORS_ORIGINS` = `https://your-app.vercel.app`
- `FRONTEND_URL` = `https://your-app.vercel.app`

Trigger a manual deploy or wait for the next push.

---

## Step 4: Post-Deployment Validation

### 4A. Backend Health Checks

```bash
# Shallow health (should return immediately)
curl https://momo-fraud-api.onrender.com/api/health
# Expected: {"status":"ok","env":"production"}

# Deep readiness (checks DB, ML, uploads)
curl https://momo-fraud-api.onrender.com/api/health/ready
# Expected: {"status":"ready","checks":{"database":"ok","schema":"ok",...}}
```

**Expected `checks` values:**
| Check | Expected | Notes |
|---|---|---|
| `database` | `ok` | Neon connected |
| `schema` | `ok` | Tables created by init_db() |
| `ml_model` | `ok` | fraud_model.pkl + tfidf.pkl loaded |
| `ocr` | `unavailable` | **Expected** — Tesseract not installed on Render native runtime |
| `upload_dir` | `ok` | Directory exists and writable |

### 4B. Auth Flow

```bash
# Register
curl -X POST https://momo-fraud-api.onrender.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Test User","email":"test@example.com","phone_number":"0551234567","password":"TestPass123!"}'

# Login
curl -X POST https://momo-fraud-api.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"TestPass123!"}'
# Save the "token" from the response
```

### 4C. Frontend Smoke Test

1. Open `https://your-app.vercel.app` in browser
2. Register a new account → should succeed
3. Login → should redirect to dashboard
4. Navigate to **Check Message** → paste an SMS → should return a verdict
5. Navigate to **Message History** → should show the check you just did
6. Navigate to **Wallets** → add a wallet → should persist

### 4D. Cross-Origin Verification

Open browser DevTools → Network tab:
- All `/api/*` requests should succeed (no CORS errors)
- Response headers should include `Access-Control-Allow-Origin: https://your-app.vercel.app`

---

## Known Limitations for Pilot

| Limitation | Impact | Workaround |
|---|---|---|
| **No Tesseract OCR on Render** | Screenshot analysis disabled; SMS text checking works fully | Use Docker runtime on Render for OCR (requires Dockerfile) |
| **Render free-tier cold starts** | First request after 15 min idle takes ~30–60s | Upgrade to paid ($7/mo) or use an uptime monitor to ping `/api/health` |
| **Uploads not persistent (free tier)** | Screenshots lost on redeploy | Add a Render disk (paid) or use external storage |
| **Single Gunicorn worker** | Limited concurrency; handles ~50 req/s | Increase `--workers` to 2–4 on paid plans with more RAM |
| **Email not configured** | Password reset and verification emails log to console | Set `MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD` env vars on Render |
| **Rate limiting in-memory** | Resets on deploy/restart | Acceptable for pilot; use Redis for production |

---

## Email Configuration (Optional)

To enable real email delivery for password resets and verification:

Add these env vars in Render:

| Key | Value |
|---|---|
| `MAIL_SERVER` | `smtp.gmail.com` |
| `MAIL_PORT` | `587` |
| `MAIL_USE_TLS` | `1` |
| `MAIL_USERNAME` | `yourapp@gmail.com` |
| `MAIL_PASSWORD` | _(Gmail App Password — NOT your login password)_ |
| `MAIL_DEFAULT_FROM` | `yourapp@gmail.com` |
| `EMAIL_VERIFICATION_ENABLED` | `0` _(set to `1` to require email verification)_ |

Without these, the app still works — emails are logged to stdout and
registration proceeds without verification.

---

## Files Changed for Deployment

| File | Change | Purpose |
|---|---|---|
| `render.yaml` | Workers 2→1, added UPLOAD_DIR, added notes about free tier/OCR | Render blueprint |
| `build.sh` | _(no change — already correct)_ | Render build script |
| `frontend/vercel.json` | _(no change — already correct)_ | Vercel SPA config |
| `frontend/vite.config.js` | **Created** — loads `@vitejs/plugin-react` | Ensures React plugin is active for build |
| `frontend/.env.production` | _(no change — template with placeholder URL)_ | Overridden by Vercel dashboard env var |
| `flask_backend/.env.production` | _(no change — reference template only)_ | Not used at runtime on Render |

---

## Troubleshooting

### Backend won't start
- Check Render logs for `[CONFIG] Production configuration errors:`
- Most common: `SECRET_KEY` not set, or `CORS_ORIGINS` still `*`
- Fix: set the missing env vars in Render dashboard

### Database connection fails
- Verify `DATABASE_URL` starts with `postgresql://` and includes `?sslmode=require`
- Check Neon dashboard: is the project active? (Neon suspends after inactivity on free tier)
- Test from local: `psql "your-connection-string"` → `SELECT 1;`

### CORS errors in browser
- Check that `CORS_ORIGINS` exactly matches your Vercel URL (protocol + domain, no trailing slash)
- Example: `https://momo-fraud-123.vercel.app` (not `http://`, not with trailing `/`)

### Frontend shows "Network Error" or blank page
- Check `VITE_API_BASE` in Vercel → Settings → Environment Variables
- Must be the full Render URL: `https://momo-fraud-api.onrender.com`
- After changing, trigger a **Redeploy** in Vercel (env vars bake into the build)

### ML model not loading
- Check Render build logs: `=== Copying ML models ===` should succeed
- Verify the `ml/model/` directory is committed to git (not in `.gitignore`)
- Run `ls ml/model/` locally — should show `fraud_model.pkl`, `tfidf.pkl`, etc.

### OCR unavailable (expected)
- Render's native runtime doesn't include Tesseract
- SMS text checking works; screenshot upload returns a clear error
- To enable: switch to Docker runtime with the existing `flask_backend/Dockerfile`

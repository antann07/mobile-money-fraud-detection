# MTN MoMo Fraud Detection — Production Readiness Plan

> Prepared for: Productionization Phase (pre-deployment)
> Scope: Student project → controlled real-world deployment

---

## 1. Production-Readiness Assessment

### What You Have (Strengths)

| Component                              | Status        | Notes                                                           |
| -------------------------------------- | ------------- | --------------------------------------------------------------- |
| Flask backend with app factory         | ✅ Solid      | Clean `create_app()`, blueprints, config split                  |
| JWT authentication + admin roles       | ✅ Working    | `auth_middleware.py` with `@login_required` / `@admin_required` |
| Security headers                       | ✅ Present    | `X-Frame-Options`, `X-Content-Type-Options`, HSTS in prod mode  |
| CORS with configurable origins         | ✅ Present    | Parsed from env var, wildcard only in dev                       |
| Parameterized SQL queries              | ✅ Good       | No raw f-string SQL injection vectors                           |
| Rule-based fraud engine                | ✅ Functional | Explainable output with confidence + reasons                    |
| SMS authenticity engine                | ✅ Functional | MTN format verification, urgency detection, v6.1 calibration    |
| OCR with Tesseract                     | ✅ Working    | Graceful degradation when Tesseract unavailable                 |
| File upload with magic-byte validation | ✅ Good       | 5 MB limit, extension + content-type checks                     |
| React frontend with pages + routing    | ✅ Complete   | 14 page components, protected routes, sidebar nav               |
| Admin review queue                     | ✅ Working    | Whitelist validation on labels/statuses                         |
| Config split (dev/prod)                | ✅ Present    | ProductionConfig with secret key validation                     |
| Deployment documentation               | ✅ Written    | Render deployment guide exists                                  |

### What Is Still Demo-Level (Must Fix)

| Issue                                | Severity    | Current State                                 | Production Requirement                                       |
| ------------------------------------ | ----------- | --------------------------------------------- | ------------------------------------------------------------ |
| **SQLite database**                  | 🔴 Critical | `sqlite3` with `check_same_thread=False`      | PostgreSQL with connection pooling                           |
| **Hardcoded secret key fallback**    | 🔴 Critical | Falls through to `"dev-secret-key..."`        | Fail-fast if SECRET_KEY not set                              |
| **Debug mode defaults ON**           | 🔴 Critical | `FLASK_DEBUG=1` default                       | Must default to OFF; stack traces leak routes/code           |
| **No rate limiting**                 | 🟠 High     | Login/register open to brute force            | flask-limiter on auth + prediction endpoints                 |
| **ML model: 20 training samples**    | 🟠 High     | Overfitted, not generalizable                 | 200+ labeled samples minimum for baseline                    |
| **No request validation library**    | 🟠 High     | Manual checks, inconsistent                   | marshmallow or pydantic schemas on all inputs                |
| **PII in log output**                | 🟠 High     | Emails, phone numbers logged in plaintext     | Mask PII; log only anonymized identifiers                    |
| **No WSGI server**                   | 🟠 High     | `flask run` (Werkzeug dev server)             | Gunicorn with worker processes                               |
| **Frontend API base hardcoded**      | 🟡 Medium   | `VITE_API_BASE` with `localhost` fallback     | Build-time env injection                                     |
| **No reverse proxy**                 | 🟡 Medium   | Flask serves directly                         | Nginx for TLS, static files, buffering                       |
| **Uploaded files on local disk**     | 🟡 Medium   | `uploads/screenshots/` directory              | Persistent volume or object storage                          |
| **No model versioning**              | 🟡 Medium   | `fraud_model.pkl` with no metadata            | Track model version, training date, metrics                  |
| **No health check for dependencies** | 🟡 Medium   | `/api/health` only checks Flask               | Also verify DB connection, model loaded, Tesseract available |
| **Token refresh has no revocation**  | 🟡 Medium   | Old tokens remain valid forever               | Token blacklist or short-lived + refresh token rotation      |
| **No pagination**                    | 🟡 Medium   | All predictions/transactions returned at once | LIMIT/OFFSET with page params                                |

---

## 2. Recommended Production Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      DOCKER HOST                            │
│                                                             │
│  ┌──────────┐    ┌────────────────────┐    ┌────────────┐  │
│  │  Nginx   │───▶│   Gunicorn (4w)    │───▶│ PostgreSQL │  │
│  │  :80/443 │    │   Flask app :5001  │    │   :5432    │  │
│  │          │    │                    │    │            │  │
│  │  static  │    │  ┌──────────────┐  │    └────────────┘  │
│  │  files   │    │  │ ML Models    │  │                     │
│  │  (React  │    │  │ (pkl files)  │  │    ┌────────────┐  │
│  │   build) │    │  └──────────────┘  │    │  Uploads   │  │
│  └──────────┘    │  ┌──────────────┐  │    │  (volume)  │  │
│                  │  │ Tesseract    │  │    └────────────┘  │
│                  │  │ OCR engine   │  │                     │
│                  │  └──────────────┘  │                     │
│                  └────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

### Component Decisions

#### Database: **Move to PostgreSQL**

SQLite is the right call for prototyping, but you must move to PostgreSQL for deployment. Here's why:

| Factor                               | SQLite                                  | PostgreSQL                       |
| ------------------------------------ | --------------------------------------- | -------------------------------- |
| Concurrent writes                    | Single-writer lock                      | Full MVCC concurrency            |
| Thread safety                        | Requires `check_same_thread=False` hack | Native multi-connection          |
| Data durability on Render/Docker     | **Lost on redeploy**                    | Persistent across deploys        |
| Connection pooling                   | Not supported                           | Via pgBouncer or SQLAlchemy pool |
| Full-text search (future SMS search) | Limited                                 | Built-in `tsvector`              |

**Migration approach**: Your schema is clean SQL with no SQLite-isms. It ports directly to PostgreSQL. Use `psycopg2-binary` and swap `sqlite3.connect()` for a connection pool.

#### WSGI Server: **Gunicorn**

```
gunicorn --workers 4 --bind 0.0.0.0:5001 --timeout 120 "app:create_app()"
```

- 4 workers (2× CPU cores for a small VM)
- 120s timeout (OCR processing can be slow on large screenshots)
- Already in your `ml/requirements.txt` — just add to `flask_backend/requirements.txt`

#### Reverse Proxy: **Nginx**

- Terminates TLS (Let's Encrypt via certbot)
- Serves the React build (`dist/`) as static files
- Proxies `/api/*` to Gunicorn
- Buffers uploads (protects slow Gunicorn workers)
- Adds security headers at the edge

#### Containerization: **Docker Compose (3 services)**

```yaml
services:
  db: # PostgreSQL 16
  backend: # Python 3.11 + Gunicorn + Tesseract
  nginx: # Nginx + React static build
```

This is the right level of complexity for a student project. Kubernetes/ECS would be overkill.

#### Environment Variables

```env
# .env.production (NEVER committed to git)
SECRET_KEY=<64-char random hex>
DATABASE_URL=postgresql://user:password@db:5432/fraud_detection
FLASK_ENV=production
FLASK_DEBUG=0
ALLOWED_ORIGINS=https://yourdomain.com
TOKEN_EXPIRY_HOURS=8
LOG_LEVEL=WARNING
TESSERACT_CMD=/usr/bin/tesseract
```

#### File Upload Storage

For a student deployment, a Docker named volume is sufficient:

```yaml
volumes:
  upload_data:
    driver: local
```

Mount to `/app/uploads`. If you later need cloud deployment, swap to S3-compatible storage with `boto3`.

#### OCR Dependency Handling

Tesseract must be installed in the Docker image:

```dockerfile
RUN apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-eng
```

The app should verify Tesseract on startup and log a clear warning (not silently degrade).

#### Model Artifact Handling

- Ship `.pkl` files **inside** the Docker image (they're small, ~1 MB)
- Add a `model_metadata.json` with version, training date, sample count, accuracy
- Load models at app startup (not lazily on first request)
- Log model version on startup for traceability

---

## 3. Priority Hardening Checklist

### 🔴 Security Hardening (P0 — Must Do)

- [ ] **S1: Enforce SECRET_KEY at startup** — Remove the default fallback entirely. If `SECRET_KEY` env var is missing, crash immediately with a clear error.
- [ ] **S2: Default DEBUG to OFF** — Change `Config.DEBUG` default to `False`. Only enable via explicit `FLASK_DEBUG=1`.
- [ ] **S3: Add rate limiting** — `flask-limiter` on `/api/auth/login` (5/min), `/api/auth/register` (3/min), `/api/message-checks/*` (10/min).
- [ ] **S4: Mask PII in logs** — Never log raw emails, phone numbers, or wallet numbers. Log user IDs only.
- [ ] **S5: Lock CORS origins** — In production config, reject `"*"` — require explicit whitelisted origins.
- [ ] **S6: Add CSRF protection** — For cookie-based sessions; or ensure all state-changing requests use `Authorization: Bearer` header (which is CSRF-immune).
- [ ] **S7: Strip EXIF metadata from uploads** — Before storing screenshots, remove GPS/device metadata with Pillow's `Image.getexif()`.
- [ ] **S8: Sanitize filenames** — Use `werkzeug.utils.secure_filename()` on all uploads (verify this is already done).
- [ ] **S9: Add Content-Security-Policy header** — Restrict script sources to your own domain.
- [ ] **S10: Pin all dependency versions exactly** — `scikit-learn==1.5.2` not `>=1.4`. Lock with `pip freeze > requirements.lock`.

### 🟠 Backend Hardening (P1 — Should Do)

- [ ] **B1: Migrate to PostgreSQL** — Replace `db.py` with `psycopg2` + connection pooling (or SQLAlchemy).
- [ ] **B2: Add input validation schemas** — Use marshmallow or pydantic for all request payloads: register, login, add-wallet, add-transaction, sms-check, upload.
- [ ] **B3: Add pagination** — All list endpoints (`/predictions`, `/transactions`, `/message-checks/history`) must accept `page` + `per_page` params.
- [ ] **B4: Centralized error handling** — Return consistent JSON error format: `{"error": "...", "code": "VALIDATION_ERROR"}`.
- [ ] **B5: Add request ID tracing** — Generate a UUID per request, include in all log lines and error responses.
- [ ] **B6: Enrich health check** — `/api/health` should verify: DB connection, model loaded, Tesseract available.
- [ ] **B7: Add Gunicorn + production entrypoint** — Create `wsgi.py` and `gunicorn.conf.py`.
- [ ] **B8: Implement token revocation** — Either short-lived tokens (1h) + refresh rotation, or a token blacklist table.
- [ ] **B9: Add database migrations** — Use Alembic or Flask-Migrate instead of raw `schema.sql` on every startup.
- [ ] **B10: Structured JSON logging** — Switch from plain text logs to JSON for log aggregation tools.

### 🟡 Frontend Hardening (P2 — Should Do)

- [ ] **F1: Build-time API base URL** — Ensure `VITE_API_BASE` is set in CI/CD build step, not relying on localhost fallback.
- [ ] **F2: Add loading states and error boundaries** — Every API call should show loading spinner; uncaught errors should show fallback UI, not a blank screen.
- [ ] **F3: Add client-side input validation** — Validate forms before submission (email format, password strength, amount > 0).
- [ ] **F4: Implement token expiry handling** — Show "Session expired" toast and redirect to login (your `api.js` partially does this — verify it works).
- [ ] **F5: Add CSP meta tag** — If Nginx CSP header isn't possible, add via `<meta>` in `index.html`.
- [ ] **F6: Lazy-load heavy pages** — Use `React.lazy()` for Review Queue and OCR pages to reduce initial bundle.
- [ ] **F7: Lighthouse audit** — Run Lighthouse, fix accessibility and performance issues.

### 🟢 ML Hardening (P3 — Important for Credibility)

- [ ] **M1: Expand training dataset to 200+ samples** — Generate or collect more labeled MTN MoMo SMS messages (genuine + fraudulent). Use data augmentation (paraphrasing) if needed.
- [ ] **M2: Add cross-validation** — Replace single 80/20 split with StratifiedKFold (k=5). Your `sms_model_training.py` already has this — unify the training scripts.
- [ ] **M3: Add model metadata tracking** — Save `model_metadata.json` alongside `.pkl` files: version, date, sample count, accuracy, F1-score.
- [ ] **M4: Load models at startup, not lazily** — Fail fast if model files are missing or corrupt.
- [ ] **M5: Log prediction confidence distribution** — Track how confident the model is across requests (drift detection).
- [ ] **M6: Consolidate training scripts** — You have `train_model.py` and `sms_model_training.py` doing similar work. Pick one and delete the other.

---

## 4. Phased Productionization Roadmap

### Phase A: Security & Config Lockdown (1–2 days)

**Goal**: Eliminate all critical security gaps without changing architecture.

| Task                                            | File(s)                                                      | Effort |
| ----------------------------------------------- | ------------------------------------------------------------ | ------ |
| Remove SECRET_KEY default; crash if not set     | `config.py`                                                  | 15 min |
| Default DEBUG to False                          | `config.py`                                                  | 5 min  |
| Add `flask-limiter` to auth & prediction routes | `auth_routes.py`, `prediction_routes.py`, `requirements.txt` | 1 hour |
| Mask PII in all log statements                  | `auth_routes.py`, `auth_service.py`                          | 30 min |
| Pin all dependency versions exactly             | `requirements.txt`                                           | 15 min |
| Reject CORS wildcard in production mode         | `config.py`, `app.py`                                        | 15 min |
| Strip EXIF from uploaded screenshots            | `ocr_service.py` or `message_check_routes.py`                | 30 min |
| Add `Content-Security-Policy` header            | `app.py`                                                     | 15 min |

**Deliverable**: Same app, same SQLite, but secure enough for controlled testing.

---

### Phase B: PostgreSQL Migration + Input Validation (2–3 days)

**Goal**: Make the data layer production-grade and validate all inputs.

| Task                                               | File(s)                                                                    | Effort  |
| -------------------------------------------------- | -------------------------------------------------------------------------- | ------- |
| Create PostgreSQL schema (port from `schema.sql`)  | New `schema_pg.sql`                                                        | 1 hour  |
| Replace `db.py` with psycopg2 connection pool      | `db.py`                                                                    | 2 hours |
| Update all model files to use new connection API   | `models/*.py`                                                              | 2 hours |
| Add marshmallow/pydantic schemas for all endpoints | New `schemas/` directory                                                   | 3 hours |
| Add pagination to list endpoints                   | `prediction_routes.py`, `transaction_routes.py`, `message_check_routes.py` | 1 hour  |
| Test all routes against PostgreSQL                 | Manual + existing test files                                               | 1 hour  |

**Deliverable**: App runs on PostgreSQL with validated inputs. SQLite still works for local dev via `DATABASE_URL` switch.

---

### Phase C: Docker & Deployment Infrastructure (1–2 days)

**Goal**: One-command deployment with `docker compose up`.

| Task                                                  | File(s)                             | Effort |
| ----------------------------------------------------- | ----------------------------------- | ------ |
| Create backend `Dockerfile` (Python 3.11 + Tesseract) | `flask_backend/Dockerfile`          | 1 hour |
| Create `gunicorn.conf.py` + `wsgi.py`                 | `flask_backend/`                    | 30 min |
| Build React frontend for production                   | `frontend/Dockerfile` or build step | 30 min |
| Create Nginx config (proxy + static files)            | `nginx/nginx.conf`                  | 1 hour |
| Create `docker-compose.yml` (3 services)              | Root                                | 1 hour |
| Create `.env.production.example` template             | Root                                | 15 min |
| Test full stack with `docker compose up`              | —                                   | 1 hour |
| Enrich `/api/health` to check DB + model + Tesseract  | `app.py`                            | 30 min |

**Deliverable**: `docker compose up` starts the full stack. `.env.production.example` documents all required variables.

---

### Phase D: ML Improvements + Model Pipeline (2–3 days)

**Goal**: Make the ML component credible for a project demo.

| Task                                                          | File(s)                               | Effort    |
| ------------------------------------------------------------- | ------------------------------------- | --------- |
| Expand training data to 200+ samples                          | `ml/data/`                            | 3–4 hours |
| Consolidate into single training script with cross-validation | `ml/train_model.py`                   | 1 hour    |
| Add `model_metadata.json` output                              | `ml/train_model.py`                   | 30 min    |
| Load models at Flask startup, not lazily                      | `flask_backend/services/ml_scorer.py` | 30 min    |
| Add model version to prediction API responses                 | `prediction_routes.py`                | 15 min    |
| Document training/retraining process                          | `ml/README.md`                        | 30 min    |

**Deliverable**: Model trained on real-sized dataset, versioned, loaded eagerly, documented.

---

### Phase E: Frontend Polish + Final Testing (1–2 days)

**Goal**: Production UX and end-to-end verification.

| Task                                                                                         | File(s)                                       | Effort  |
| -------------------------------------------------------------------------------------------- | --------------------------------------------- | ------- |
| Add loading states to all API calls                                                          | `pages/*.jsx`                                 | 2 hours |
| Add error boundary component                                                                 | New `components/ErrorBoundary.jsx`            | 30 min  |
| Add client-side form validation                                                              | `pages/Register.jsx`, `pages/Login.jsx`, etc. | 1 hour  |
| Run Lighthouse, fix critical issues                                                          | —                                             | 1 hour  |
| End-to-end test: register → login → add wallet → submit SMS → view prediction → admin review | Manual                                        | 1 hour  |
| Update `README.md` with production deployment instructions                                   | `README.md`                                   | 30 min  |

**Deliverable**: Polished, tested app ready for demo or controlled deployment.

---

## 5. Summary: Recommended Priority Order

```
Phase A  ──▶  Phase B  ──▶  Phase C  ──▶  Phase D  ──▶  Phase E
Security     Database      Docker        ML Model      Frontend
(1-2 days)   (2-3 days)    (1-2 days)    (2-3 days)    (1-2 days)
```

**Total estimated scope**: 7–12 working days depending on experience.

**If you only have time for one phase**: Do **Phase A** (security lockdown). It's the highest-impact, lowest-effort work and is mandatory for any deployment.

**If you have time for two phases**: Do **Phase A + Phase C** (security + Docker). This gives you a deployable, secure artifact even with SQLite.

---

## 6. Files That Need Changes (Quick Reference)

| File                                           | Changes Needed                                                               |
| ---------------------------------------------- | ---------------------------------------------------------------------------- |
| `flask_backend/config.py`                      | Remove SECRET_KEY default, default DEBUG=False, reject CORS wildcard in prod |
| `flask_backend/db.py`                          | Add PostgreSQL support with connection pooling                               |
| `flask_backend/app.py`                         | Add CSP header, enrich health check, rate limiter init                       |
| `flask_backend/requirements.txt`               | Add `flask-limiter`, `psycopg2-binary`, `marshmallow`, pin versions          |
| `flask_backend/routes/auth_routes.py`          | Mask PII in logs, add rate limiting decorators                               |
| `flask_backend/routes/message_check_routes.py` | EXIF stripping, rate limiting                                                |
| `flask_backend/services/ml_scorer.py`          | Eager model loading, version tracking                                        |
| `flask_backend/services/ocr_service.py`        | EXIF stripping, explicit Tesseract check                                     |
| `ml/train_model.py`                            | Cross-validation, metadata output, larger dataset                            |
| `frontend/src/services/api.js`                 | Verify VITE_API_BASE injection                                               |
| New: `flask_backend/Dockerfile`                | Python 3.11 image + Tesseract                                                |
| New: `flask_backend/wsgi.py`                   | Gunicorn entrypoint                                                          |
| New: `docker-compose.yml`                      | 3-service stack                                                              |
| New: `nginx/nginx.conf`                        | Reverse proxy + static files                                                 |
| New: `.env.production.example`                 | Document all required env vars                                               |

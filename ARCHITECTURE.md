# MTN MoMo Fraud Detection — Final Production Architecture

> Decision-final architecture for controlled real deployment.
> Complements: `PRODUCTION_PLAN.md` (security hardening checklist)

---

## 1. Chosen Deployment Pattern

**Pattern: Single-server Docker Compose with Nginx reverse proxy**

Three containers on one Linux host, orchestrated by Docker Compose:

```
┌──────────────────────────────────────────────────────────────────┐
│                     SINGLE VPS / DROPLET                         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                   Nginx  (port 80 / 443)                   │  │
│  │                                                            │  │
│  │   /              →  React dist/ (static files)             │  │
│  │   /api/*         →  proxy_pass → backend:5001              │  │
│  │   /uploads/*     →  alias → upload volume (direct serve)   │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                             │                                     │
│                             ▼                                     │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │            Gunicorn + Flask  (internal :5001)              │  │
│  │            4 sync workers · 120s timeout                   │  │
│  │                                                            │  │
│  │   ┌──────────────┐  ┌─────────────┐  ┌────────────────┐  │  │
│  │   │  Flask App   │  │  Tesseract  │  │  ML Models     │  │  │
│  │   │  6 blueprints│  │  OCR engine │  │  (.pkl baked   │  │  │
│  │   │  JWT auth    │  │  (apt pkg)  │  │   into image)  │  │  │
│  │   └──────────────┘  └─────────────┘  └────────────────┘  │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                             │                                     │
│                             ▼                                     │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              PostgreSQL 16  (internal :5432)               │  │
│  │              fraud_detection database                      │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Persistent volumes:                                             │
│    pg_data      — database files (survives rebuilds)             │
│    upload_data  — screenshot uploads (shared: backend writes,    │
│                   nginx reads)                                   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Why This Is the Best Tradeoff

This pattern was chosen over four alternatives. Here's the reasoning:

| Alternative                             | Why it loses                                                                                                                                                                                                      |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Bare Flask dev server**               | What you have now. Single-threaded, no TLS, no process recovery, no static file serving. Not deployable.                                                                                                          |
| **Gunicorn only (no Nginx, no Docker)** | Works, but you serve static files through Python (slow), manage TLS yourself, have no upload buffering, and "it works on my machine" problems when deploying. Misses half the production benefit.                 |
| **Managed platform (Render / Railway)** | Simpler to deploy, but you lose control over Tesseract installation, can't share volumes between services, free tiers have cold starts, and PostgreSQL add-ons cost extra. Less learning value for the portfolio. |
| **Kubernetes / cloud-native**           | Massively over-engineered for 3 containers serving <100 users. Adds weeks of YAML complexity with zero benefit at this scale.                                                                                     |

**Docker Compose with Nginx hits the sweet spot** because:

1. **One command deploys everything**: `docker compose up -d` starts all 3 services with correct networking, volumes, and restart policies.
2. **Same setup everywhere**: Your laptop, your partner's laptop, and the production server all run identical containers. No environment drift.
3. **Each component does one job**: Nginx handles the internet. Gunicorn handles Python. PostgreSQL handles data. No component is overloaded.
4. **Industry-standard pattern**: This is genuinely how small-to-medium Flask apps run in production. It's not a student workaround — it's the real thing.
5. **Clear upgrade path**: If you outgrow this, you push the same Docker images to Render, Railway, or Fly.io. No rewrite needed.

---

## 2. Component Responsibilities

Every component has **exactly one primary job** and a strict boundary. Here's what each does, what it explicitly does NOT do, and what files it maps to in your codebase.

### 2A. Nginx — Internet-Facing Gateway

**Primary job**: Accept all incoming HTTP/HTTPS traffic and route it to the right place.

```
Internet ──► Nginx ──► static files  (React app)
                  ──► Gunicorn      (API requests)
                  ──► upload volume  (screenshot images)
```

| Does                                         | Does NOT                            |
| -------------------------------------------- | ----------------------------------- |
| Terminates TLS (HTTPS via Let's Encrypt)     | Run any application logic           |
| Serves React `dist/` as static files         | Authenticate users or check JWTs    |
| Reverse-proxies `/api/*` to Gunicorn         | Touch the database                  |
| Serves uploaded screenshots from volume      | Process images or run OCR           |
| Buffers large uploads before forwarding      | Make decisions about fraud verdicts |
| Sets security headers (CSP, HSTS, X-Frame)   | Log application-level events        |
| Enforces per-IP rate limits (optional layer) | Store any state                     |

**Why Nginx specifically**: It's the most common reverse proxy for Python apps. Apache works too, but Nginx has better static file performance and simpler config syntax. Caddy is a newer alternative with automatic TLS, but Nginx has more documentation and community support.

**Key configuration decisions**:

- `client_max_body_size 5m` — matches your Flask 5MB upload limit
- `proxy_read_timeout 120s` — matches Gunicorn's 120s worker timeout for OCR
- `try_files $uri $uri/ /index.html` — SPA fallback so React Router works on refresh

**Codebase mapping**: No existing files. New file: `nginx/nginx.conf`

**CORS elimination**: Today your browser makes cross-origin requests (`localhost:5173` → `localhost:5001`), requiring CORS headers. With Nginx, the browser sees a single origin — Nginx serves both the frontend (`/`) and API (`/api/*`) from the same domain. CORS headers become unnecessary. Your existing `flask-cors` setup remains as a safety net but stops being the primary mechanism.

### 2B. Gunicorn — Application Process Manager

**Primary job**: Run multiple copies of your Flask app and manage their lifecycle.

| Does                                          | Does NOT                                      |
| --------------------------------------------- | --------------------------------------------- |
| Spawns 4 Flask worker processes               | Serve static files (Nginx does that)          |
| Kills and restarts workers that hang or crash | Handle TLS (Nginx does that)                  |
| Enforces 120s request timeout                 | Manage the database (PostgreSQL does that)    |
| Logs access and errors to stdout/stderr       | Run as a separate Docker container from Flask |
| Binds to port 5001 (internal only)            | Expose any port to the internet               |

**Why 4 sync workers**: The formula is `2 × CPU_cores + 1`. On a 2-vCPU droplet, that's 5 workers. We use 4 to leave headroom for PostgreSQL and Nginx. Sync workers (not async/gevent) are correct because your workload is CPU-bound (Tesseract OCR, scikit-learn scoring), not I/O-bound.

**Why 120s timeout**: Your OCR pipeline (image preprocessing → Tesseract → text parsing) can take 10-30s on a large screenshot. The default 30s Gunicorn timeout would kill OCR workers mid-processing. 120s gives generous headroom.

**Codebase mapping**:

- New: `flask_backend/wsgi.py` — one-line entry point: `from app import create_app; application = create_app()`
- New: `flask_backend/gunicorn.conf.py` — worker count, bind address, timeout
- Existing: `flask_backend/app.py` — your `create_app()` factory is already Gunicorn-compatible, no changes needed

**Relationship to Flask**: Gunicorn and Flask are NOT separate services. Gunicorn lives in the same Docker container as Flask and imports your `create_app()`. Think of Gunicorn as "the thing that runs Flask properly" — like how a car engine (Flask) needs a transmission (Gunicorn) to actually move.

### 2C. Flask Application — Business Logic

**Primary job**: Handle every API request end-to-end (auth, fraud analysis, OCR, review).

| Does                                           | Does NOT                                         |
| ---------------------------------------------- | ------------------------------------------------ |
| JWT authentication (issue, validate, expire)   | Serve the React frontend                         |
| SMS authenticity analysis (rule engine + ML)   | Terminate TLS                                    |
| Screenshot OCR orchestration (calls Tesseract) | Manage its own process lifecycle (Gunicorn does) |
| Admin review queue workflow                    | Serve uploaded files to browsers (Nginx does)    |
| Database reads/writes via `db.py`              | Run database migrations automatically            |
| Input validation on all endpoints              | Store ML model training state                    |
| JSON error responses with consistent format    | Monitor its own health (Docker healthcheck does) |

**What changes for production**: Almost nothing in `app.py` itself. Your app factory, blueprints, middleware, and route structure are already production-shaped. The changes are:

1. `config.py` — remove default secret key, fail-fast validation
2. `db.py` — add PostgreSQL support alongside existing SQLite
3. `requirements.txt` — add `gunicorn`, `psycopg2-binary`, `flask-limiter`

**Codebase mapping** (existing, no structural changes):

```
flask_backend/
├── app.py                    # App factory — unchanged
├── config.py                 # Tighten defaults — minor edits
├── db.py                     # Add PostgreSQL path — rewrite
├── middleware/auth_middleware.py  # unchanged
├── routes/                   # 6 blueprints — unchanged
├── services/                 # Fraud engine, OCR, ML — unchanged
├── models/                   # DB queries — update ? → %s for PG
└── utils/validators.py       # unchanged
```

### 2D. PostgreSQL — Persistent Data Layer

**Primary job**: Store all application data with concurrency support and persistence across deploys.

| Does                                            | Does NOT                                        |
| ----------------------------------------------- | ----------------------------------------------- |
| Store users, wallets, transactions, predictions | Cache frequent queries (not needed at scale)    |
| Handle concurrent reads/writes (MVCC)           | Run application logic or stored procedures      |
| Persist data in a Docker volume across rebuilds | Manage backups automatically (you must script)  |
| Enforce foreign key constraints natively        | Connect to the internet (internal network only) |
| Initialize schema on first run via init script  | Run migrations (manual for now, Alembic later)  |

**Why PostgreSQL over SQLite** (the specific reasons for your app):

1. **Your OCR upload flow is the bottleneck**: User A uploads a screenshot (OCR takes 15 seconds). During that time, User B submits an SMS check. With SQLite, User B's write blocks until User A's transaction commits. With PostgreSQL, both complete independently.

2. **Container lifecycle**: When you run `docker compose down && docker compose up` to deploy a new version, a SQLite file inside the container is destroyed. PostgreSQL data lives in a named volume that survives container rebuilds.

3. **Your schema is already relational**: 11 tables with foreign keys, JOIN-heavy queries in the review and history endpoints. This is exactly what PostgreSQL is built for.

4. **Migration is low-effort**: Your SQL has no SQLite-isms. The changes are mechanical:

   | SQLite                              | PostgreSQL           |
   | ----------------------------------- | -------------------- |
   | `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` |
   | `?` placeholder                     | `%s` placeholder     |
   | `datetime('now')`                   | `NOW()`              |
   | `PRAGMA foreign_keys`               | Enabled by default   |

**Codebase mapping**:

- Rewrite: `flask_backend/db.py` — dual-mode (SQLite for dev, psycopg2 pool for prod, selected by `DATABASE_URL`)
- New: `flask_backend/schema_pg.sql` — PostgreSQL version of existing `schema.sql`
- Edit: `flask_backend/models/*.py` — change `?` to `%s` in SQL queries

**Keep SQLite for local development**: Your `db.py` will detect `DATABASE_URL`. If it starts with `postgresql://`, use psycopg2. Otherwise, use sqlite3. This means `flask run` still works locally without Docker.

### 2E. Tesseract OCR — Image Text Extraction

**Primary job**: Convert MoMo screenshot images into text that the fraud engine can analyze.

| Does                                                            | Does NOT                                     |
| --------------------------------------------------------------- | -------------------------------------------- |
| Extract text from PNG/JPG/WEBP screenshots                      | Run as a separate service or container       |
| Apply your preprocessing pipeline (threshold, denoise, upscale) | Make fraud decisions (Flask services do)     |
| Return extracted text + confidence score                        | Store images (Flask writes to upload volume) |
| Degrade gracefully if unavailable                               | Require a GPU                                |

**Deployment**: Tesseract is a system package (`apt-get install tesseract-ocr`) installed in the backend Dockerfile. It is NOT a separate Docker service. `pytesseract` calls the binary directly.

**Why not a separate OCR service**: Your OCR is called once per screenshot upload, synchronously, in the same request that runs fraud analysis. Splitting it into a separate service would add network latency, a message queue, and async handling — complexity that buys nothing at your scale.

**Resource impact**: OCR is the most CPU-intensive operation in the app. On a single-core VPS, a large screenshot can take 10-30 seconds. This is why:

- Gunicorn timeout is 120s (not the default 30s)
- You use sync workers (OCR blocks the CPU; async workers can't help)
- 4 workers = max 4 concurrent OCR jobs

**Codebase mapping** (existing, no changes):

- `flask_backend/services/ocr_service.py` — preprocessing + pytesseract call
- New: Dockerfile `RUN apt-get install -y tesseract-ocr tesseract-ocr-eng`

### 2F. ML Model Artifacts — Fraud Scoring

**Primary job**: Provide trained model files that the Flask app loads to score SMS messages.

| Does                                                    | Does NOT                             |
| ------------------------------------------------------- | ------------------------------------ |
| Ship inside the Docker image (immutable per release)    | Retrain automatically                |
| Load at app startup (not lazily on first request)       | Update without a full redeploy       |
| Include version metadata (date, accuracy, sample count) | Run as a separate prediction service |
| Fall back to rule-engine-only if models are missing     | Require more than ~5 MB of storage   |

**Why bake into the image, not a volume**:

- Models change only when you retrain (rarely). Code changes more often than models, but they deploy together.
- Baking into the image means every Docker image is a complete, reproducible snapshot: code + models + dependencies.
- Rollback = `docker compose up` with a previous image tag. No "which model version was on the server?" confusion.

**Codebase mapping**:

- New directory: `flask_backend/model_artifacts/` — copy from `ml/model/`
- New file: `flask_backend/model_artifacts/model_metadata.json`
- Edit: `flask_backend/services/ml_scorer.py` — change model path, load at startup

**Training workflow** (stays separate from deployment):

```
ml/data/ → ml/train_model.py → ml/model/*.pkl → copy to flask_backend/model_artifacts/ → rebuild Docker image
```

### 2G. React/Vite Frontend — User Interface

**Primary job**: Provide the browser-based UI as a pre-built static bundle.

| Does                                        | Does NOT                                        |
| ------------------------------------------- | ----------------------------------------------- |
| Built once at deploy time (`npm run build`) | Run as a process in production (no Vite server) |
| Produce static HTML/JS/CSS in `dist/`       | Make direct database queries                    |
| Call API via relative URLs (`/api/*`)       | Handle authentication logic (backend JWTs do)   |
| Handle client-side routing (React Router)   | Process images or run OCR                       |

**The critical production change**: In development, React runs on `:5173` and calls Flask on `:5001` (cross-origin). In production, Nginx serves both from the same origin:

```
Development:
  Browser → localhost:5173 (Vite) → API calls to localhost:5001 (Flask) [CORS required]

Production:
  Browser → yourdomain.com (Nginx) → / serves dist/ files
                                   → /api/* proxied to Gunicorn [same origin, no CORS]
```

**Build-time configuration**: Set `VITE_API_BASE=/api` in `frontend/.env.production` so the build output uses relative API paths. Your existing `api.js` already reads `import.meta.env.VITE_API_BASE`.

**Codebase mapping** (existing, one config change):

- Existing: `frontend/src/` — no code changes needed
- Edit: `frontend/.env.production` — set `VITE_API_BASE=/api`
- Output: `frontend/dist/` — generated by `npm run build`, mounted into Nginx

---

## 3. How Requests Flow Through the Stack

Understanding request flow makes the architecture concrete. Here are the three request types your app handles:

### 3A. Page Load (Static)

```
Browser requests https://yourdomain.com/history
  → Nginx receives on :443
  → Matches location / (static files)
  → Serves frontend/dist/index.html (React SPA)
  → Browser loads JS bundle, React Router renders /history page
  → React calls GET /api/message-checks/history
  → (continues as API request below)
```

**Who does what**: Nginx serves the file. Flask is not involved. Fast.

### 3B. API Request (SMS Check)

```
Browser POSTs to /api/message-checks/sms-check with JWT + SMS text
  → Nginx receives on :443, strips TLS
  → Matches location /api/, proxies to backend:5001
  → Gunicorn assigns request to an available worker
  → Flask middleware validates JWT → extracts user_id
  → Route handler calls:
      1. sms_parser.py     → extracts structured fields from SMS text
      2. authenticity_engine.py → rule-based scoring (format, urgency, sender)
      3. ml_scorer.py       → ML model prediction (if model loaded)
      4. fraud_engine.py    → combines scores into final verdict
  → Model layer writes result to PostgreSQL
  → Flask returns JSON response
  → Gunicorn sends response back through Nginx
  → Browser renders verdict card
```

**Who does what**: Nginx proxies. Gunicorn manages the worker. Flask runs the logic. PostgreSQL stores the result.

### 3C. Screenshot Upload + OCR

```
Browser POSTs to /api/message-checks/upload-screenshot with JWT + image file
  → Nginx receives, buffers the entire upload (up to 5MB)
  → Proxies buffered request to backend:5001
  → Gunicorn assigns to a worker (this worker is now busy for 10-30s)
  → Flask middleware validates JWT
  → Route handler:
      1. Validates file (magic bytes, extension, size)
      2. Saves to upload volume (/app/uploads/screenshots/)
      3. Calls ocr_service.py → preprocesses image → calls Tesseract binary
      4. Tesseract extracts text (CPU-intensive, 5-25 seconds)
      5. Extracted text → same analysis pipeline as SMS check
      6. Result written to PostgreSQL
  → Flask returns JSON response
  → Worker is freed for the next request
```

**Who does what**: Nginx buffers the upload (protects Gunicorn from slow network). Gunicorn worker is dedicated for the full OCR duration. Tesseract does the heavy CPU work. Flask orchestrates.

**Why upload buffering matters**: Without Nginx, a user on a slow 3G connection uploading a 4MB screenshot would tie up a Gunicorn worker for 30+ seconds just receiving bytes. With Nginx buffering, the worker only starts when the complete file is ready — processing takes 10-25s instead of 40-55s.

---

## 4. Next Implementation Steps

Architecture planning is done. Here is the exact sequence of work to build this, in dependency order.

### Step 1: Production Entrypoint (Gunicorn + Config)

**What you're building**: The ability to run Flask under Gunicorn with production-safe defaults. No Docker yet — just make the app production-ready on your local machine.

**Files to create / edit**:

| File                             | Action | Content                                                                       |
| -------------------------------- | ------ | ----------------------------------------------------------------------------- |
| `flask_backend/wsgi.py`          | Create | `from app import create_app` + `application = create_app()`                   |
| `flask_backend/gunicorn.conf.py` | Create | `workers=4`, `bind="0.0.0.0:5001"`, `timeout=120`                             |
| `flask_backend/requirements.txt` | Edit   | Add `gunicorn==23.0.*`, `flask-limiter==3.8.*`, `psycopg2-binary==2.9.*`      |
| `flask_backend/config.py`        | Edit   | Remove default secret key, default DEBUG to `False`, add fail-fast validation |

**How to verify it works**:

```bash
cd flask_backend
pip install -r requirements.txt
gunicorn --config gunicorn.conf.py "wsgi:application"
# Visit http://127.0.0.1:5001/api/health → should return {"status": "ok"}
```

### Step 2: PostgreSQL Migration

**What you're building**: A `db.py` that auto-detects SQLite vs PostgreSQL from `DATABASE_URL`, so the same codebase runs both.

**Files to create / edit**:

| File                          | Action  | Content                                                                                  |
| ----------------------------- | ------- | ---------------------------------------------------------------------------------------- |
| `flask_backend/schema_pg.sql` | Create  | Port `schema.sql` — replace `AUTOINCREMENT` → `SERIAL`, `datetime('now')` → `NOW()`      |
| `flask_backend/db.py`         | Rewrite | Detect URL scheme, use `psycopg2.pool.SimpleConnectionPool` for PG, keep sqlite3 for dev |
| `flask_backend/models/*.py`   | Edit    | Replace `?` with `%s` in SQL queries (or use a helper that adapts)                       |

**How to verify it works**:

```bash
# Start a test PostgreSQL instance:
docker run -d --name pg-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=fraud_detection -p 5432:5432 postgres:16-alpine

# Point your app at it:
DATABASE_URL=postgresql://postgres:test@localhost:5432/fraud_detection flask run

# Run your existing smoke tests
python test_smoke.py
```

### Step 3: Dockerize the Backend

**What you're building**: A Dockerfile that produces a self-contained image with Python, Tesseract, your code, and model files.

**Files to create**:

| File                             | Action | Content                                                                              |
| -------------------------------- | ------ | ------------------------------------------------------------------------------------ |
| `flask_backend/Dockerfile`       | Create | `FROM python:3.11-slim` + `apt-get install tesseract-ocr` + copy code + install deps |
| `flask_backend/.dockerignore`    | Create | Exclude `.env`, `__pycache__`, `*.db`, `uploads/`                                    |
| `flask_backend/model_artifacts/` | Create | Copy `.pkl` files from `ml/model/` + create `model_metadata.json`                    |

**How to verify it works**:

```bash
cd flask_backend
docker build -t fraud-backend .
docker run --rm -p 5001:5001 -e SECRET_KEY=test-key-ok -e DATABASE_URL=sqlite:///tmp/test.db fraud-backend
# Visit http://127.0.0.1:5001/api/health
```

### Step 4: Nginx + Frontend Build

**What you're building**: Nginx config that serves the React build and proxies API requests.

**Files to create / edit**:

| File                       | Action | Content                                                                              |
| -------------------------- | ------ | ------------------------------------------------------------------------------------ |
| `nginx/nginx.conf`         | Create | `location /` → static files, `location /api/` → proxy, `location /uploads/` → volume |
| `frontend/.env.production` | Edit   | `VITE_API_BASE=/api`                                                                 |

**How to verify it works**:

```bash
cd frontend && npm run build    # produces dist/
# Then test nginx config with docker compose (Step 5)
```

### Step 5: Docker Compose — Full Stack

**What you're building**: One file that starts all three services together.

**Files to create**:

| File                      | Action | Content                                                            |
| ------------------------- | ------ | ------------------------------------------------------------------ |
| `docker-compose.prod.yml` | Create | 3 services (db, backend, nginx) + 2 volumes (pg_data, upload_data) |
| `.env.production.example` | Create | Template with all variables documented                             |
| `.env.production`         | Create | Actual secrets (add to `.gitignore` first)                         |

**How to verify it works**:

```bash
docker compose -f docker-compose.prod.yml up --build
# Open http://localhost → React app loads
# Register → Login → Submit SMS → See verdict
# docker compose down && docker compose up → data still there
```

### Step 6: Health Checks + Observability

**What you're building**: A `/api/health` endpoint that verifies all dependencies, plus Docker-level healthchecks.

**Files to edit**:

| File                                                | Action | Content                                                  |
| --------------------------------------------------- | ------ | -------------------------------------------------------- |
| `flask_backend/app.py`                              | Edit   | Enhance `/api/health` to check DB + ML model + Tesseract |
| `docker-compose.prod.yml`                           | Edit   | Add `healthcheck` blocks to all 3 services               |
| `flask_backend/model_artifacts/model_metadata.json` | Create | `{version, date, accuracy, samples}`                     |

### The Dependency Chain

Steps must be done in this order because each depends on the previous:

```
Step 1 (Gunicorn + config)
  └─► Step 2 (PostgreSQL)        — needs production config patterns from Step 1
       └─► Step 3 (Dockerfile)   — needs PG support and gunicorn from Steps 1-2
            └─► Step 4 (Nginx)   — needs frontend build config
                 └─► Step 5 (Compose) — assembles Steps 3 + 4
                      └─► Step 6 (Health) — adds observability to running stack
```

After Step 5, you have a fully deployable system. Step 6 makes it production-observable. Actual server deployment (VPS provisioning, DNS, TLS) is a separate future phase that uses the Docker Compose stack you've built.

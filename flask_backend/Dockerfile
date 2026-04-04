# ============================================================
# Flask Backend — Production Dockerfile
# ============================================================
# Multi-stage build:
#   Stage 1 (builder): installs Python deps into a virtualenv
#   Stage 2 (runtime): copies the venv + app code into a slim image
#
# Usage:
#   docker build -t momo-backend ./flask_backend
#   docker run -p 5001:5001 --env-file .env momo-backend
# ============================================================

# ── Stage 1: Build dependencies ─────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build-time system deps (needed to compile bcrypt, numpy, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
  gcc \
  g++ \
  && rm -rf /var/lib/apt/lists/*

# Create a virtualenv so we can cleanly copy it to the runtime stage
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime image ───────────────────────────────────
FROM python:3.12-slim

# Install runtime system deps:
#   - tesseract-ocr: OCR engine for screenshot analysis
#   - libglib2.0-0: image processing libs needed by Pillow
#   - curl: for healthcheck (more reliable than Python urllib)
RUN apt-get update && apt-get install -y --no-install-recommends \
  tesseract-ocr \
  libglib2.0-0 \
  curl \
  && rm -rf /var/lib/apt/lists/*

# Copy the pre-built virtualenv from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Don't buffer Python output — logs appear immediately in `docker logs`
ENV PYTHONUNBUFFERED=1
# Don't write .pyc files inside the container
ENV PYTHONDONTWRITEBYTECODE=1

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy application code
COPY . .

# Create directories the app expects (uploads, logs)
# These can be overridden with Docker volumes at runtime
RUN mkdir -p /app/uploads/screenshots /app/logs \
  && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Gunicorn listens on this port
EXPOSE 5001

# Health check — Docker/Compose can monitor this
# Uses the shallow /api/health (fast, no DB round-trip)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -sf http://localhost:5001/api/health || exit 1

# Start Gunicorn with production-safe defaults
#   -w 4            : 4 worker processes
#   -b 0.0.0.0:5001 : bind to all interfaces
#   --timeout 120   : allow slow OCR uploads
#   --graceful-timeout 30 : give workers 30s to finish on SIGTERM
#   --max-requests 1000   : recycle workers to prevent memory leaks
#   --max-requests-jitter 50 : stagger recycling to avoid all-at-once restarts
#   --access-logfile -  : access logs to stdout (Docker captures them)
CMD ["gunicorn", "wsgi:application", \
  "--bind", "0.0.0.0:5001", \
  "--workers", "4", \
  "--timeout", "120", \
  "--graceful-timeout", "30", \
  "--max-requests", "1000", \
  "--max-requests-jitter", "50", \
  "--access-logfile", "-", \
  "--error-logfile", "-"]

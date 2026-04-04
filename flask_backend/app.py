"""
Mobile Money Fraud Detection API — Production-Ready
Entry point: creates the Flask app, registers blueprints, initializes DB.

Routes:
  PUBLIC
    GET  /               — API info
    GET  /api/health     — shallow health (for load balancers)
    GET  /api/health/ready — deep readiness (DB + OCR + model checks)
    POST /api/auth/register
    POST /api/auth/login

  PROTECTED (JWT required)
    POST /api/wallet/add
    GET  /api/wallet
    POST /api/transactions/add
    GET  /api/transactions
    GET  /api/predictions
    POST /api/message-checks/sms-check
    POST /api/message-checks/upload-screenshot
    GET  /api/message-checks/history
    GET  /api/message-checks/<id>

Configuration:
  Reads FLASK_ENV to pick DevelopmentConfig or ProductionConfig.
  See config.py for all environment variables.
"""

import os
import time
import logging
from flask import Flask, jsonify, request, g
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import get_config
from db import init_db
from middleware.request_context import RequestIDFilter, init_request_context
from utils.startup import run_startup_checks
from routes.auth_routes import auth_bp
from routes.wallet_routes import wallet_bp
from routes.transaction_routes import transaction_bp
from routes.prediction_routes import prediction_bp
from routes.message_check_routes import message_check_bp
from routes.review_routes import review_bp


def _configure_logging(cfg) -> None:
    """Set up structured logging with request-ID tracing."""
    # Include request_id in every log line for traceability
    log_format = (
        "%(asctime)s [%(levelname)s] %(name)s "
        "[rid=%(request_id)s]: %(message)s"
    )
    level = getattr(logging, cfg.LOG_LEVEL, logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(log_format))
    handler.addFilter(RequestIDFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(handler)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def _parse_origins(cfg) -> list | str:
    """Parse ALLOWED_ORIGINS from config into a list or wildcard."""
    raw = cfg.ALLOWED_ORIGINS
    if raw == "*":
        return "*"
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app() -> Flask:
    """Application factory."""
    cfg = get_config()

    app = Flask(__name__)
    app.config.from_object(cfg)

    # Flask enforces this — rejects uploads larger than this size
    app.config["MAX_CONTENT_LENGTH"] = cfg.MAX_CONTENT_LENGTH

    # Store config reference for easy access
    app.app_config = cfg

    # Ensure the upload directory exists
    os.makedirs(cfg.UPLOAD_DIR, exist_ok=True)

    # ---------- logging -----------------------
    _configure_logging(cfg)
    logger = logging.getLogger(__name__)
    logger.info("Starting app in %s mode (debug=%s)", cfg.ENV, cfg.DEBUG)

    # ---------- request-ID tracing ------------
    init_request_context(app)

    # ---------- enable CORS -------------------
    origins = _parse_origins(cfg)
    CORS(app, resources={r"/api/*": {"origins": origins}}, supports_credentials=True)

    # ---------- rate limiting -----------------
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per minute"],
        storage_uri="memory://",
    )
    # Stricter limits on auth endpoints
    limiter.limit("10 per minute")(auth_bp)
    # Screenshot uploads and SMS checks are expensive — limit the blueprint.
    # 60/min is generous for GET reads (history, detail) while still providing
    # protection against abusive bulk-submission of checks.
    limiter.limit("60 per minute")(message_check_bp)

    # ---------- register blueprints ----------
    app.register_blueprint(auth_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(transaction_bp)
    app.register_blueprint(prediction_bp)
    app.register_blueprint(message_check_bp)
    app.register_blueprint(review_bp)

    # ---------- initialize database ----------
    with app.app_context():
        init_db()

    # ---------- startup dependency checks -----
    with app.app_context():
        startup_status = run_startup_checks(cfg)
    # Store for the readiness endpoint
    app._startup_status = startup_status

    # ---------- request timing ----------------
    @app.before_request
    def _start_timer():
        g.start_time = time.monotonic()

    # ---------- request/response logging ------
    @app.after_request
    def _log_request(response):
        # Calculate response time
        elapsed_ms = 0.0
        if hasattr(g, "start_time"):
            elapsed_ms = (time.monotonic() - g.start_time) * 1000
        # Log all requests in production (INFO), verbose in dev (DEBUG)
        log_level = logging.DEBUG if cfg.DEBUG else logging.INFO
        # Skip noisy health-check logs
        if request.path in ("/api/health", "/api/health/ready"):
            log_level = logging.DEBUG
        logger.log(
            log_level,
            "%s %s %s %.0fms %s",
            request.method, request.path, response.status_code,
            elapsed_ms, request.remote_addr,
        )
        # Warn on slow requests (> 5 seconds)
        if elapsed_ms > 5000:
            logger.warning(
                "SLOW REQUEST: %s %s took %.0fms user_agent=%s",
                request.method, request.path, elapsed_ms,
                request.user_agent.string[:100],
            )
        return response

    # ---------- security headers --------------
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not cfg.DEBUG:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # ---------- root route --------------------
    @app.route("/", methods=["GET"])
    def index():
        return jsonify({"message": "Fintech Fraud Detection API Running"}), 200

    # ---------- shallow health check ----------
    # Fast — for load balancers / Docker HEALTHCHECK / uptime monitors.
    # Only confirms the process is alive and can respond.
    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "env": cfg.ENV}), 200

    # ---------- deep readiness check ----------
    # Verifies actual dependencies. Use for deployment gates and monitoring.
    @app.route("/api/health/ready", methods=["GET"])
    def readiness():
        checks = {}
        overall = True

        # Database connectivity
        try:
            from db import check_db_health
            if check_db_health():
                checks["database"] = "ok"
            else:
                checks["database"] = "unavailable"
                overall = False
        except Exception as e:
            checks["database"] = "unavailable"
            overall = False
            logger.error("Readiness: database check failed: %s", e)

        # Schema tables (from startup status)
        ss = getattr(app, "_startup_status", {})
        checks["schema"] = "ok" if ss.get("schema") else "unavailable"

        # OCR engine
        try:
            from services.ocr_service import is_available as ocr_is_available
            checks["ocr"] = "ok" if ocr_is_available() else "unavailable"
        except Exception:
            checks["ocr"] = "unavailable"

        # ML model
        checks["ml_model"] = "ok" if ss.get("ml_model") else "unavailable"

        # Upload directory writable
        checks["upload_dir"] = "ok" if os.access(cfg.UPLOAD_DIR, os.W_OK) else "unavailable"

        # Surface any critical issues from startup
        critical = ss.get("critical", [])

        status_code = 200 if overall else 503
        result = {
            "status": "ready" if overall else "degraded",
            "checks": checks,
            "env": cfg.ENV,
        }
        if critical:
            result["critical_issues"] = critical
        return jsonify(result), status_code

    # ---------- global error handlers ---------
    @app.errorhandler(404)
    def not_found(_e):
        logger.warning("404 Not Found: %s %s", request.method, request.path)
        return jsonify({"success": False, "errors": ["Resource not found."]}), 404

    @app.errorhandler(405)
    def method_not_allowed(_e):
        logger.warning("405 Method Not Allowed: %s %s", request.method, request.path)
        return jsonify({"success": False, "errors": ["Method not allowed."]}), 405

    @app.errorhandler(413)
    def payload_too_large(_e):
        logger.warning("413 Payload Too Large: %s %s from %s",
                        request.method, request.path, request.remote_addr)
        return jsonify({"success": False, "errors": ["File too large. Maximum upload size is 5 MB."]}), 413

    @app.errorhandler(429)
    def rate_limit_exceeded(_e):
        logger.warning("429 Rate Limited: %s %s from %s",
                        request.method, request.path, request.remote_addr)
        return jsonify({
            "success": False,
            "errors": ["Too many requests. Please wait a moment and try again."],
        }), 429

    @app.errorhandler(500)
    def server_error(_e):
        logger.error("500 Internal Server Error: %s %s", request.method, request.path, exc_info=True)
        # Never leak stack traces in production
        if cfg.DEBUG:
            return jsonify({"success": False, "errors": ["Internal server error.", str(_e)]}), 500
        return jsonify({"success": False, "errors": ["Something went wrong. Please try again later."]}), 500

    return app


# ---------- run directly with: python app.py ----------
if __name__ == "__main__":
    application = create_app()
    cfg = get_config()
    print(f"\n>>> Starting server at http://127.0.0.1:5001 ({cfg.ENV} mode)\n")
    application.run(host="127.0.0.1", port=5001, debug=cfg.DEBUG)

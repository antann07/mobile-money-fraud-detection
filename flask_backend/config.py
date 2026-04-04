"""
Application configuration — dev / production split.

How it works:
  1. python-dotenv loads flask_backend/.env automatically.
  2. The Config base class reads environment variables with safe defaults.
  3. DevelopmentConfig and ProductionConfig override where needed.
  4. app.py picks the right class based on FLASK_ENV (default: development).

Environment variables used:
  SECRET_KEY          – JWT / session signing key (MUST be set in production)
  JWT_SECRET          – Separate JWT signing key (falls back to SECRET_KEY)
  FLASK_ENV           – "development" or "production"
  FLASK_DEBUG         – "1" or "0"
  DATABASE_URL        – SQLite path or PostgreSQL connection string
  UPLOAD_DIR          – Directory for screenshot uploads
  MODEL_DIR           – Directory containing trained .pkl model files
  TESSERACT_CMD       – Full path to the Tesseract binary
  MAX_CONTENT_LENGTH  – Maximum upload size in bytes (default: 5 MB)
  CORS_ORIGINS        – Comma-separated allowed origins (also reads ALLOWED_ORIGINS)
  TOKEN_EXPIRY_HOURS  – JWT lifetime in hours (default: 24)
  LOG_LEVEL           – Python log level name (default: INFO)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env from the flask_backend directory ───────────────────────
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

# ── Convenience: project paths ───────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _BACKEND_DIR.parent


class Config:
    """Base configuration — safe defaults for all environments."""

    # ── Security ─────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    JWT_SECRET = os.environ.get("JWT_SECRET") or SECRET_KEY
    TOKEN_EXPIRY_HOURS = int(os.environ.get("TOKEN_EXPIRY_HOURS", "24"))

    # ── Account lockout ──────────────────────────────────────────
    MAX_FAILED_LOGINS = int(os.environ.get("MAX_FAILED_LOGINS", "5"))
    LOCKOUT_MINUTES = int(os.environ.get("LOCKOUT_MINUTES", "15"))

    # ── Password reset ───────────────────────────────────────────
    RESET_TOKEN_EXPIRY_MINUTES = int(os.environ.get("RESET_TOKEN_EXPIRY_MINUTES", "30"))

    # ── Flask ────────────────────────────────────────────────────
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
    ENV = os.environ.get("FLASK_ENV", "development")

    # ── Database ─────────────────────────────────────────────────
    # SQLite: a file path.  PostgreSQL: postgresql://user:pass@host:5432/db
    _default_db = str(_BACKEND_DIR / "fraud_detection.db")
    DATABASE_URL = os.environ.get("DATABASE_URL", _default_db)

    # ── File Uploads ─────────────────────────────────────────────
    _default_upload_dir = str(_BACKEND_DIR / "uploads" / "screenshots")
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", _default_upload_dir)

    # ── Max upload size (bytes) — Flask enforces this automatically ──
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", str(5 * 1024 * 1024)))

    # ── ML Model Directory ───────────────────────────────────────
    _default_model_dir = str(_PROJECT_DIR / "ml" / "model")
    MODEL_DIR = os.environ.get("MODEL_DIR", _default_model_dir)

    # ── Tesseract OCR ────────────────────────────────────────────
    # Set this if Tesseract is not on PATH (e.g. Windows custom install)
    TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "")

    # ── CORS ─────────────────────────────────────────────────────
    # Reads CORS_ORIGINS first, then ALLOWED_ORIGINS for backward compat.
    CORS_ORIGINS = os.environ.get(
        "CORS_ORIGINS",
        os.environ.get("ALLOWED_ORIGINS", "*"),
    )
    # Keep ALLOWED_ORIGINS as an alias so existing code doesn't break
    ALLOWED_ORIGINS = CORS_ORIGINS

    # ── Logs Directory ─────────────────────────────────────────────
    # Where structured log files are written (rotated by the OS / Docker).
    # Leave blank to log to stdout only (stdout is always active).
    _default_log_dir = str(_BACKEND_DIR / "logs")
    LOG_DIR = os.environ.get("LOG_DIR", _default_log_dir)

    # ── Logging ──────────────────────────────────────────────────
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


class DevelopmentConfig(Config):
    """Local development — verbose logging, debug mode on."""

    DEBUG = True
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG").upper()


class StagingConfig(Config):
    """
    Pilot / staging — debug off, INFO-level logs.
    Enforces the same security checks as production so pilot runs
    with real secrets and real CORS restrictions.
    """

    DEBUG = False
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

    @staticmethod
    def validate():
        """Re-use production validation so staging catches the same misconfigs."""
        ProductionConfig.validate()


class ProductionConfig(Config):
    """Production — debug off, strict CORS, require real secret key."""

    DEBUG = False
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "WARNING").upper()

    @staticmethod
    def validate():
        """Fail fast if critical env vars are missing in production."""
        errors = []
        warnings = []

        if Config.SECRET_KEY == "dev-secret-key-change-in-production":
            errors.append(
                "SECRET_KEY is still the default. "
                "Set a strong SECRET_KEY env variable before deploying."
            )
        if len(Config.SECRET_KEY) < 32:
            warnings.append(
                "SECRET_KEY is shorter than 32 characters. "
                "Use a longer key for stronger security."
            )
        if Config.CORS_ORIGINS == "*":
            errors.append(
                "CORS_ORIGINS is '*' (allow-all). "
                "Set explicit origins for production."
            )
        if Config.TOKEN_EXPIRY_HOURS > 72:
            warnings.append(
                f"TOKEN_EXPIRY_HOURS is {Config.TOKEN_EXPIRY_HOURS}. "
                "Consider a shorter token lifetime for production."
            )
        # Warn if SQLite is used in production — not suitable for concurrent writes
        if not Config.DATABASE_URL.startswith(("postgresql://", "postgres://")):
            warnings.append(
                "DATABASE_URL is not PostgreSQL. "
                "SQLite is not recommended for production (no concurrent writes)."
            )

        import logging
        logger = logging.getLogger(__name__)
        for w in warnings:
            logger.warning("[CONFIG] %s", w)

        if errors:
            raise RuntimeError(
                "Production configuration errors:\n  - " + "\n  - ".join(errors)
            )


# ── Map FLASK_ENV → config class ─────────────────────────────────────
_config_map = {
    "development": DevelopmentConfig,
    "staging":     StagingConfig,
    "production":  ProductionConfig,
}


def get_config():
    """Return the config class matching FLASK_ENV."""
    env = os.environ.get("FLASK_ENV", "development").lower()
    cfg = _config_map.get(env, DevelopmentConfig)
    # Both staging and production enforce the strict validation checks
    if env in ("staging", "production") and hasattr(cfg, "validate"):
        cfg.validate()
    return cfg

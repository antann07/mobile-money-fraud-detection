"""
Startup dependency checks — run once when the app boots.

Validates that critical dependencies are reachable BEFORE the app starts
accepting traffic.  Problems are logged clearly so operators know exactly
what to fix.

Called from create_app() after init_db().
"""

import os
import logging

logger = logging.getLogger(__name__)


def run_startup_checks(cfg) -> dict:
    """
    Validate all external dependencies and return a status dict.

    Returns:
        {
            "database": True/False,
            "schema": True/False,
            "ocr": True/False,
            "ml_model": True/False,
            "upload_dir": True/False,
            "warnings": ["..."],
            "critical": ["..."],
        }
    """
    results = {
        "database": False,
        "schema": False,
        "ocr": False,
        "ml_model": False,
        "upload_dir": False,
        "logs_dir": False,
        "warnings": [],
        "critical": [],
    }

    # ── 1. Database connectivity ─────────────────────────────────
    try:
        from db import get_db, close_db, is_pg
        conn = get_db()
        if is_pg():
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
        else:
            conn.execute("SELECT 1")
        close_db(conn)
        results["database"] = True
        logger.info("[STARTUP] Database: OK (%s)",
                    "PostgreSQL" if is_pg() else "SQLite")
    except Exception as e:
        msg = f"Database connection failed: {e}"
        results["critical"].append(msg)
        logger.error("[STARTUP] %s", msg)

    # ── 1b. Schema table verification ────────────────────────────
    # Verify that essential tables exist (catches stale DB / missing migrations)
    if results["database"]:
        _REQUIRED_TABLES = [
            "users", "wallets", "transactions", "message_checks",
            "predictions", "fraud_reviews", "user_behavior_profiles",
        ]
        try:
            from db import get_db, close_db, is_pg
            conn = get_db()
            missing_tables = []
            for table in _REQUIRED_TABLES:
                try:
                    if is_pg():
                        cur = conn.cursor()
                        cur.execute(
                            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                            "WHERE table_name = %s)", (table,)
                        )
                        exists = cur.fetchone()[0]
                        cur.close()
                    else:
                        row = conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                            (table,)
                        ).fetchone()
                        exists = row is not None
                    if not exists:
                        missing_tables.append(table)
                except Exception:
                    missing_tables.append(f"{table} (query failed)")
            close_db(conn)

            if missing_tables:
                msg = f"Missing database tables: {', '.join(missing_tables)}"
                results["critical"].append(msg)
                logger.error("[STARTUP] %s", msg)
            else:
                results["schema"] = True
                logger.info("[STARTUP] Schema tables: OK (%d tables verified)",
                            len(_REQUIRED_TABLES))
        except Exception as e:
            msg = f"Schema table check failed: {e}"
            results["warnings"].append(msg)
            logger.warning("[STARTUP] %s", msg)

    # ── 2. OCR (Tesseract) availability ──────────────────────────
    try:
        from services.ocr_service import is_available as ocr_is_available
        if ocr_is_available():
            results["ocr"] = True
            logger.info("[STARTUP] OCR (Tesseract): OK")
        else:
            msg = "Tesseract OCR not found — screenshot analysis will be disabled"
            results["warnings"].append(msg)
            logger.warning("[STARTUP] %s", msg)
    except ImportError as e:
        msg = f"OCR module import failed ({e}) — pytesseract or Pillow not installed"
        results["warnings"].append(msg)
        logger.warning("[STARTUP] %s", msg)
    except Exception as e:
        msg = f"OCR check failed: {e}"
        results["warnings"].append(msg)
        logger.warning("[STARTUP] %s", msg)

    # ── 3. ML model files + load validation ──────────────────────
    model_path = os.path.join(cfg.MODEL_DIR, "fraud_model.pkl")
    tfidf_path = os.path.join(cfg.MODEL_DIR, "tfidf.pkl")
    if os.path.isfile(model_path) and os.path.isfile(tfidf_path):
        # Try to actually import joblib and load the model to catch
        # corrupt files / version mismatches at startup, not first request
        try:
            import joblib
            model = joblib.load(model_path)
            tfidf = joblib.load(tfidf_path)
            # Basic sanity: model should have predict method, tfidf should have transform
            if not hasattr(model, "predict"):
                raise ValueError("Model missing predict() method")
            if not hasattr(tfidf, "transform"):
                raise ValueError("TF-IDF vectorizer missing transform() method")
            results["ml_model"] = True
            model_size_kb = os.path.getsize(model_path) // 1024
            logger.info("[STARTUP] ML model: OK (loaded, %dKB, dir=%s)",
                        model_size_kb, cfg.MODEL_DIR)
        except Exception as e:
            msg = f"ML model files exist but failed to load: {e}"
            results["warnings"].append(msg)
            logger.warning("[STARTUP] %s", msg)
    else:
        missing = []
        if not os.path.isfile(model_path):
            missing.append("fraud_model.pkl")
        if not os.path.isfile(tfidf_path):
            missing.append("tfidf.pkl")
        msg = (f"ML model files missing ({', '.join(missing)}) in {cfg.MODEL_DIR} "
               f"— ML scoring disabled, rule engine will handle all requests")
        results["warnings"].append(msg)
        logger.warning("[STARTUP] %s", msg)

    # ── 4. Upload directory ──────────────────────────────────────
    try:
        os.makedirs(cfg.UPLOAD_DIR, exist_ok=True)
        # Verify we can actually write to it
        test_file = os.path.join(cfg.UPLOAD_DIR, ".write_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        results["upload_dir"] = True
        logger.info("[STARTUP] Upload directory: OK (%s)", cfg.UPLOAD_DIR)
    except Exception as e:
        msg = f"Upload directory not writable ({cfg.UPLOAD_DIR}): {e}"
        results["critical"].append(msg)
        logger.error("[STARTUP] %s", msg)

    # ── 5. Logs directory ───────────────────────────────────────
    log_dir = getattr(cfg, "LOG_DIR", None)
    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
            test_file = os.path.join(log_dir, ".write_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            results["logs_dir"] = True
            logger.info("[STARTUP] Logs directory: OK (%s)", log_dir)
        except Exception as e:
            msg = f"Logs directory not writable ({log_dir}): {e}"
            results["warnings"].append(msg)
            logger.warning("[STARTUP] %s", msg)
    else:
        # No file-based log dir configured — stdout logging only, perfectly fine
        results["logs_dir"] = True
        logger.info("[STARTUP] Logs directory: not configured (stdout only)")

    # ── 6. JWT secret sanity ───────────────────────────────────────
    if cfg.SECRET_KEY == cfg.JWT_SECRET:
        logger.info("[STARTUP] JWT secret: using SECRET_KEY (shared)")
    else:
        logger.info("[STARTUP] JWT secret: using separate JWT_SECRET")

    # ── Summary ──────────────────────────────────────────────────
    total_warnings = len(results["warnings"]) + len(results["critical"])
    if results["critical"]:
        logger.error("[STARTUP] *** %d CRITICAL issue(s) ***:", len(results["critical"]))
        for c in results["critical"]:
            logger.error("[STARTUP]   CRITICAL: %s", c)
    if results["warnings"]:
        logger.warning("[STARTUP] %d warning(s):", len(results["warnings"]))
        for w in results["warnings"]:
            logger.warning("[STARTUP]   - %s", w)
    if total_warnings == 0:
        logger.info("[STARTUP] All dependency checks passed")

    return results

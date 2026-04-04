"""
Mobile Money Fraud Detection API – Phase 1
Entry point: creates the Flask app, registers blueprints, initializes DB.
"""

import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
from config import Config
from db import init_db
from routes.auth_routes import auth_bp
from routes.wallet_routes import wallet_bp


def _configure_logging(app: Flask) -> None:
    """Set up structured logging with timestamp, level, and module."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_format)
    # Keep werkzeug at INFO so the "Running on http://..." line is visible
    logging.getLogger("werkzeug").setLevel(logging.INFO)
    app.logger.setLevel(logging.INFO)


def create_app() -> Flask:
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(Config)

    # ---------- logging -----------------------
    _configure_logging(app)

    # ---------- enable CORS -------------------
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # ---------- register blueprints ----------
    app.register_blueprint(auth_bp)
    app.register_blueprint(wallet_bp)

    # ---------- initialize database ----------
    with app.app_context():
        init_db()

    # ---------- request logging ---------------
    @app.before_request
    def log_request():
        app.logger.info("%s %s from %s", request.method, request.path, request.remote_addr)

    @app.after_request
    def log_response(response):
        app.logger.info("%s %s -> %s", request.method, request.path, response.status_code)
        return response

    # ---------- root route --------------------
    @app.route("/", methods=["GET"])
    def index():
        return jsonify({"message": "Fintech Fraud Detection API Running"}), 200

    # ---------- health check ------------------
    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "message": "API is running."}), 200

    # ---------- global error handlers ---------
    @app.errorhandler(404)
    def not_found(_e):
        app.logger.warning("404 Not Found: %s %s", request.method, request.path)
        return jsonify({"success": False, "errors": ["Resource not found."]}), 404

    @app.errorhandler(500)
    def server_error(_e):
        app.logger.error("500 Internal Server Error: %s %s", request.method, request.path, exc_info=True)
        return jsonify({"success": False, "errors": ["Internal server error."]}), 500

    return app


# ---------- run directly with: python app.py ----------
if __name__ == "__main__":
    application = create_app()
    print("\n>>> Starting server at http://127.0.0.1:5001\n")
    application.run(host="127.0.0.1", port=5001, debug=Config.DEBUG)

"""Application configuration."""

import logging
import os
import secrets
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """Base configuration -- override via environment variables or .env file."""

    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"


if not os.environ.get("SECRET_KEY"):
    logger.warning(
        "SECRET_KEY not set in environment. Using a random key -- "
        "all tokens will be invalidated when the server restarts. "
        "Set SECRET_KEY in your .env file for persistence."
    )

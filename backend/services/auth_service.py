"""Authentication service -- registration, login, and JWT helpers."""

import bcrypt
import jwt
from datetime import datetime, timedelta, timezone

from config import Config
from models.user_model import create_user, get_user_by_email
from utils.validators import (
    validate_registration,
    validate_email,
    normalize_phone,
    MAX_PWD_LEN,
)


# --------------- helpers ---------------

def _hash_password(plain: str) -> str:
    """Return a bcrypt hash of the plaintext password."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Corrupt or malformed hash in the database
        return False


# ── JWT helpers ───────────────────────────────────────────

_TOKEN_EXPIRY_HOURS = 24


def generate_token(user_id: int, role: str) -> str:
    """Create a JWT containing the user id and role."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": now + timedelta(hours=_TOKEN_EXPIRY_HOURS),
        "iat": now,
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Decode and return the JWT payload. Raises on invalid / expired."""
    payload = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
    # Ensure required claims are present (defence in depth)
    if "user_id" not in payload or "role" not in payload:
        raise jwt.InvalidTokenError("Token is missing required claims.")
    return payload


# ── Response helper ───────────────────────────────────────

def _sanitize_user(user: dict) -> dict:
    """Return a copy of the user dict without sensitive fields."""
    safe = dict(user)
    safe.pop("password_hash", None)
    return safe


# ── Public API ────────────────────────────────────────────

def register_user(data: dict) -> tuple[dict, int]:
    """Validate input, create user, return (response_body, status_code)."""
    errors = validate_registration(data)
    if errors:
        return {"success": False, "errors": errors}, 400

    email = data["email"].strip().lower()
    if get_user_by_email(email):
        return {"success": False, "errors": ["Email already registered."]}, 409

    user = create_user(
        full_name=data["full_name"].strip(),
        email=email,
        phone_number=normalize_phone(data["phone_number"]),
        password_hash=_hash_password(data["password"]),
        role=data.get("role", "customer"),
    )

    # create_user returns None on UNIQUE constraint violation (race condition)
    if user is None:
        return {"success": False, "errors": ["Email already registered."]}, 409

    return {
        "success": True,
        "message": "User registered successfully.",
        "token": generate_token(user["id"], user["role"]),
        "user": _sanitize_user(user),
    }, 201


def login_user(data: dict) -> tuple[dict, int]:
    """Authenticate with email + password, return token on success."""
    email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
    password = data.get("password") if isinstance(data.get("password"), str) else ""

    # Required field checks
    if not email and not password:
        return {"success": False, "errors": ["Email and password are required."]}, 400
    if not email:
        return {"success": False, "errors": ["email is required."]}, 400
    if not password:
        return {"success": False, "errors": ["password is required."]}, 400

    # Password length cap (match registration rule, avoid bcrypt CPU abuse)
    if len(password) > MAX_PWD_LEN:
        return {"success": False, "errors": [f"password must not exceed {MAX_PWD_LEN} characters."]}, 400

    # Email format check (reject obviously invalid before DB lookup)
    email_err = validate_email(email)
    if email_err:
        return {"success": False, "errors": [email_err]}, 400

    # Authenticate
    user = get_user_by_email(email)
    if not user or not _check_password(password, user["password_hash"]):
        return {"success": False, "errors": ["Invalid email or password."]}, 401

    return {
        "success": True,
        "message": "Login successful.",
        "token": generate_token(user["id"], user["role"]),
        "user": _sanitize_user(user),
    }, 200

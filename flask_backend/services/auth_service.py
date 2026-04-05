"""Authentication service – registration, login, token helpers, and password reset."""

import re
import logging
import secrets
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from config import get_config

logger = logging.getLogger(__name__)

from models.reset_token import (
    create_reset_token, get_valid_tokens_for_user,
    mark_token_used, invalidate_all_tokens,
)
from services.email_service import send_welcome_email, send_password_reset_email, send_verification_email
from models.email_verification import (
    create_verification_token, get_valid_verification_tokens,
    invalidate_all_verification_tokens,
)
from models.user import (
    create_user, get_user_by_email, get_user_by_email_or_username,
    get_user_by_username, increment_failed_logins, lock_account,
    reset_failed_logins, update_password, set_email_verified,
)

_cfg = get_config()


# --------------- helpers ---------------

def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def generate_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": now + timedelta(hours=_cfg.TOKEN_EXPIRY_HOURS),
        "iat": now,
    }
    return jwt.encode(payload, _cfg.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, _cfg.SECRET_KEY, algorithms=["HS256"])


# ------------- validation --------------

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
_USERNAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9._-]{2,29}$")

GHANA_PHONE_PREFIXES = {
    "024", "025", "053", "054", "055", "059",   # MTN
    "020", "050",                                  # Telecel
    "026", "027", "056", "057",                    # AirtelTigo
}

_GHANA_PHONE_RE = re.compile(r"^0[2-5]\d{8}$")

VALID_ROLES = ("customer", "admin")


def validate_ghana_phone(phone: str) -> str | None:
    if not phone:
        return "phone_number is required."
    phone = phone.strip()
    if not _GHANA_PHONE_RE.match(phone):
        return "phone_number must be a 10-digit Ghana number starting with 0 (e.g. 0241234567)."
    prefix = phone[:3]
    if prefix not in GHANA_PHONE_PREFIXES:
        return (
            f"phone_number prefix '{prefix}' is not a valid Ghana network prefix. "
            f"Valid prefixes: {', '.join(sorted(GHANA_PHONE_PREFIXES))}."
        )
    return None


def _validate_password(pwd: str) -> list[str]:
    """Validate password strength. Returns list of error strings."""
    errors = []
    if len(pwd) < 8:
        errors.append("Password must be at least 8 characters.")
    elif len(pwd) > 128:
        errors.append("Password must not exceed 128 characters.")
    else:
        if not re.search(r"[A-Z]", pwd):
            errors.append("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", pwd):
            errors.append("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", pwd):
            errors.append("Password must contain at least one digit.")
        if not re.search(r"[^a-zA-Z0-9]", pwd):
            errors.append("Password must contain at least one special character.")
    return errors


def _validate_register(data: dict) -> list[str]:
    errors = []

    required = ["full_name", "email", "phone_number", "password"]
    missing = [f for f in required if f not in data or data[f] is None]
    if missing:
        errors.append(f"Missing required fields: {', '.join(missing)}.")
        return errors

    # full_name
    name = data["full_name"].strip() if isinstance(data["full_name"], str) else ""
    if not name:
        errors.append("full_name is required.")
    elif len(name) < 2:
        errors.append("full_name must be at least 2 characters.")
    elif len(name) > 100:
        errors.append("full_name must not exceed 100 characters.")
    elif not re.match(r"^[a-zA-Z\s.'-]+$", name):
        errors.append("full_name may only contain letters, spaces, hyphens, apostrophes, and dots.")

    # username (optional)
    username = data.get("username")
    if username is not None:
        username = username.strip() if isinstance(username, str) else ""
        if username and not _USERNAME_RE.match(username):
            errors.append(
                "Username must be 3-30 characters, start with a letter, "
                "and contain only letters, digits, dots, hyphens, or underscores."
            )
        elif username and get_user_by_username(username.lower()):
            errors.append("Username is already taken.")

    # email
    email = data["email"].strip() if isinstance(data["email"], str) else ""
    if not email:
        errors.append("email is required.")
    elif not _EMAIL_RE.match(email):
        errors.append("A valid email address is required (e.g. user@example.com).")

    # phone_number (Ghana-specific)
    phone_err = validate_ghana_phone(
        data["phone_number"] if isinstance(data["phone_number"], str) else ""
    )
    if phone_err:
        errors.append(phone_err)

    # password strength
    pwd = data["password"] if isinstance(data["password"], str) else ""
    errors.extend(_validate_password(pwd))

    return errors


# ----------- public API ----------------

def register_user(data: dict) -> tuple[dict, int]:
    errors = _validate_register(data)
    if errors:
        return {"success": False, "errors": errors}, 400

    email = data["email"].strip().lower()
    if get_user_by_email(email):
        return {"success": False, "errors": ["Email already registered."]}, 409

    # Extract optional username
    raw_username = data.get("username")
    username = raw_username.strip().lower() if isinstance(raw_username, str) and raw_username.strip() else None

    # Force role to customer — prevent privilege escalation
    user = create_user(
        full_name=data["full_name"].strip(),
        email=email,
        phone_number=data["phone_number"].strip(),
        password_hash=_hash_password(data["password"]),
        role="customer",
        username=username,
    )

    if user is None:
        return {"success": False, "errors": ["Email or username already registered."]}, 409

    user.pop("password_hash", None)
    token = generate_token(user["id"], user["role"])

    # Email verification or welcome email (non-blocking — failure does not block registration)
    if _cfg.EMAIL_VERIFICATION_ENABLED:
        try:
            raw_vtoken = secrets.token_urlsafe(32)
            vtoken_hash = _hash_password(raw_vtoken)
            expires_at = (
                datetime.now(timezone.utc)
                + timedelta(hours=_cfg.EMAIL_VERIFICATION_EXPIRY_HOURS)
            ).isoformat()
            create_verification_token(user["id"], vtoken_hash, expires_at)
            send_verification_email(email, data["full_name"].strip(), raw_vtoken)
            logger.info("Verification email queued for user_id=%s", user["id"])
        except Exception:
            logger.exception("Failed to send verification email to %s", email)

        return {
            "success": True,
            "message": "Registration successful! Please check your email to verify your account.",
            "token": token,
            "user": user,
            "email_verification_required": True,
        }, 201
    else:
        try:
            send_welcome_email(email, data["full_name"].strip())
        except Exception:
            logger.exception("Failed to send welcome email to %s", email)

        return {
            "success": True,
            "message": "Registration successful! A welcome email has been sent.",
            "token": token,
            "user": user,
            "email_verification_required": False,
        }, 201


def login_user(data: dict) -> tuple[dict, int]:
    """Authenticate with email/username + password. Includes lockout logic."""
    identifier = (data.get("email") or data.get("username") or "").strip().lower()
    password = data.get("password", "")

    if not identifier or not password:
        return {"success": False, "errors": ["Email/username and password are required."]}, 400

    user = get_user_by_email_or_username(identifier)
    if not user:
        # Don't reveal whether the account exists
        logger.warning("Login failed: no account for identifier=%s", identifier)
        return {"success": False, "errors": ["Invalid credentials."]}, 401

    # Check account lockout
    locked_until = user.get("locked_until")
    if locked_until:
        if isinstance(locked_until, str):
            lock_time = datetime.fromisoformat(locked_until)
        else:
            lock_time = locked_until
        if lock_time.tzinfo is None:
            lock_time = lock_time.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < lock_time:
            remaining = int((lock_time - datetime.now(timezone.utc)).total_seconds() / 60) + 1
            logger.info(
                "Login blocked: account locked user_id=%s until=%s",
                user["id"], lock_time.isoformat(),
            )
            return {
                "success": False,
                "errors": [f"Account temporarily locked. Try again in {remaining} minute(s)."],
            }, 429

    # Guard against corrupt stored hashes (raises ValueError in bcrypt).
    try:
        password_matches = _check_password(password, user["password_hash"])
    except Exception:
        logger.exception(
            "bcrypt error for user_id=%s — stored hash may be corrupt", user["id"]
        )
        return {"success": False, "errors": ["Invalid credentials."]}, 401

    if not password_matches:
        failed = user.get("failed_login_attempts", 0) + 1
        increment_failed_logins(user["id"])
        logger.info(
            "Login failed: wrong password user_id=%s attempt=%d/%d",
            user["id"], failed, _cfg.MAX_FAILED_LOGINS,
        )

        if failed >= _cfg.MAX_FAILED_LOGINS:
            until = (datetime.now(timezone.utc) + timedelta(minutes=_cfg.LOCKOUT_MINUTES)).isoformat()
            lock_account(user["id"], until)
            logger.warning(
                "Account locked user_id=%s after %d failed attempts", user["id"], failed
            )
            return {
                "success": False,
                "errors": [f"Too many failed attempts. Account locked for {_cfg.LOCKOUT_MINUTES} minutes."],
            }, 429

        return {"success": False, "errors": ["Invalid credentials."]}, 401

    # Successful login — reset lockout counters
    reset_failed_logins(user["id"])
    logger.info("Login successful for user_id=%s", user["id"])

    token = generate_token(user["id"], user["role"])
    user_copy = dict(user)
    user_copy.pop("password_hash", None)
    user_copy.pop("failed_login_attempts", None)
    user_copy.pop("locked_until", None)

    return {
        "success": True,
        "message": "Login successful.",
        "token": token,
        "user": user_copy,
    }, 200


# ----------- password reset ------------

def request_password_reset(email: str) -> tuple[dict, int]:
    """Generate a reset token for the given email.

    Security contract:
      - The raw token is NEVER included in the API response body.
      - A password reset email is sent via SMTP when configured.
      - In development mode, the token is also logged to the server
        console so developers can test the flow without SMTP.
      - When SMTP is not configured, the email service logs the token
        to the console as a dev fallback.
    """
    email = email.strip().lower()
    user = get_user_by_email(email)

    # Always return the same response to avoid email enumeration.
    success_msg = {
        "success": True,
        "message": "If that email is registered, a reset link has been sent.",
    }

    if not user:
        # No user — return the generic message, log nothing (avoids timing oracle).
        return success_msg, 200

    # Generate a secure random token
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_password(raw_token)
    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=_cfg.RESET_TOKEN_EXPIRY_MINUTES)
    ).isoformat()

    create_reset_token(user["id"], token_hash, expires_at)

    # Send reset email (best-effort — failure is logged, not exposed to user)
    try:
        sent = send_password_reset_email(email, raw_token)
        if sent:
            logger.info("Password reset email sent to %s", email)
    except Exception:
        logger.exception("Failed to send password reset email to %s", email)

    if _cfg.DEBUG:
        # Development only: also log the token to the server console.
        logger.info(
            "[DEV] Password reset token for user_id=%s email=%s: %s",
            user["id"], email, raw_token,
        )
        logger.info(
            "[DEV] Reset link: /reset-password?email=%s&token=%s",
            email, raw_token,
        )

    return success_msg, 200


_RESET_INVALID_MSG = "This reset link is invalid or has expired. Please request a new one."


def reset_password(email: str, token: str, new_password: str) -> tuple[dict, int]:
    """Verify the reset token and update the password."""
    email = email.strip().lower()
    user = get_user_by_email(email)

    if not user:
        # Don't reveal whether the account exists
        logger.warning("Password reset attempted for unregistered email=%s", email)
        return {"success": False, "errors": [_RESET_INVALID_MSG]}, 400

    # Validate new password strength first so the user gets inline feedback
    pwd_errors = _validate_password(new_password)
    if pwd_errors:
        return {"success": False, "errors": pwd_errors}, 400

    # Fetch all unused tokens for this user
    tokens = get_valid_tokens_for_user(user["id"])
    now = datetime.now(timezone.utc)

    if not tokens:
        logger.info(
            "Password reset failed user_id=%s: no unused tokens in DB",
            user["id"],
        )
        return {"success": False, "errors": [_RESET_INVALID_MSG]}, 400

    for stored in tokens:
        # --- expiry check ---
        expires = stored["expires_at"]
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)

        if now > expires:
            logger.debug(
                "Skipping expired token id=%s user_id=%s (expired=%s)",
                stored.get("id"), user["id"], expires.isoformat(),
            )
            continue

        # --- bcrypt comparison (guard against corrupt stored hashes) ---
        try:
            matched = _check_password(token, stored["token_hash"])
        except Exception:
            logger.exception(
                "bcrypt error for token id=%s user_id=%s — hash may be corrupt",
                stored.get("id"), user["id"],
            )
            continue

        if matched:
            # Valid token found — rotate password and clear all reset tokens
            update_password(user["id"], _hash_password(new_password))
            invalidate_all_tokens(user["id"])
            reset_failed_logins(user["id"])
            logger.info("Password reset successful for user_id=%s", user["id"])
            return {"success": True, "message": "Password reset successfully. You can now log in."}, 200

    logger.info(
        "Password reset failed user_id=%s: %d token(s) checked, none matched",
        user["id"], len(tokens),
    )
    return {"success": False, "errors": [_RESET_INVALID_MSG]}, 400


# ----------- email verification -----------

_VERIFY_INVALID_MSG = "This verification link is invalid or has expired. Please request a new one."


def verify_email(email: str, token: str) -> tuple[dict, int]:
    """Verify a user's email using the verification token."""
    email = email.strip().lower()
    user = get_user_by_email(email)

    if not user:
        return {"success": False, "errors": [_VERIFY_INVALID_MSG]}, 400

    if user.get("email_verified"):
        return {"success": True, "message": "Email already verified. You can sign in."}, 200

    tokens = get_valid_verification_tokens(user["id"])
    now = datetime.now(timezone.utc)

    if not tokens:
        return {"success": False, "errors": [_VERIFY_INVALID_MSG]}, 400

    for stored in tokens:
        expires = stored["expires_at"]
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)

        if now > expires:
            continue

        try:
            matched = _check_password(token, stored["token_hash"])
        except Exception:
            logger.exception("bcrypt error for verification token id=%s", stored.get("id"))
            continue

        if matched:
            set_email_verified(user["id"])
            invalidate_all_verification_tokens(user["id"])
            logger.info("Email verified for user_id=%s", user["id"])
            return {"success": True, "message": "Email verified successfully! You can now sign in."}, 200

    return {"success": False, "errors": [_VERIFY_INVALID_MSG]}, 400


def resend_verification_email(email: str) -> tuple[dict, int]:
    """Resend a verification email for the given address."""
    email = email.strip().lower()
    user = get_user_by_email(email)

    # Generic response to avoid email enumeration
    success_msg = {
        "success": True,
        "message": "If that email is registered and unverified, a verification link has been sent.",
    }

    if not user:
        return success_msg, 200

    if user.get("email_verified"):
        return {"success": True, "message": "Email already verified. You can sign in."}, 200

    # Invalidate old tokens and create a new one
    invalidate_all_verification_tokens(user["id"])
    raw_vtoken = secrets.token_urlsafe(32)
    vtoken_hash = _hash_password(raw_vtoken)
    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(hours=_cfg.EMAIL_VERIFICATION_EXPIRY_HOURS)
    ).isoformat()
    create_verification_token(user["id"], vtoken_hash, expires_at)

    try:
        send_verification_email(email, user["full_name"], raw_vtoken)
    except Exception:
        logger.exception("Failed to resend verification email to %s", email)

    return success_msg, 200

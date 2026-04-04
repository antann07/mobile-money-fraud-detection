"""
Shared validation helpers for the Phase 1 API.

All input-validation logic lives here so that services stay focused
on business logic and models stay focused on persistence.
"""

import re


# ── Email ─────────────────────────────────────────────────

_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$"
)
MAX_EMAIL_LEN = 254  # RFC 5321


def validate_email(email: str) -> str | None:
    """Return an error message if *email* is invalid, else ``None``."""
    if not email:
        return "email is required."
    if len(email) > MAX_EMAIL_LEN:
        return f"email must not exceed {MAX_EMAIL_LEN} characters."
    if not _EMAIL_RE.match(email):
        return "A valid email address is required (e.g. user@example.com)."
    return None


# ── Ghana phone numbers ──────────────────────────────────

GHANA_PHONE_PREFIXES = {
    "024", "025", "053", "054", "055", "059",  # MTN
    "020", "050",                                # Telecel
    "026", "027", "056", "057",                  # AirtelTigo
}

_GHANA_PHONE_RE = re.compile(r"^0[2-5]\d{8}$")


def normalize_phone(phone: str) -> str:
    """Strip spaces, dashes, and dots from a phone / wallet number."""
    return phone.strip().replace(" ", "").replace("-", "").replace(".", "")


def validate_ghana_phone(phone: str) -> str | None:
    """Return an error message if *phone* is not a valid Ghana number, else ``None``."""
    if not phone:
        return "phone_number is required."
    phone = normalize_phone(phone)
    if not _GHANA_PHONE_RE.match(phone):
        return "phone_number must be a 10-digit Ghana number starting with 0 (e.g. 0241234567)."
    prefix = phone[:3]
    if prefix not in GHANA_PHONE_PREFIXES:
        return (
            f"phone_number prefix '{prefix}' is not a valid Ghana network prefix. "
            f"Valid prefixes: {', '.join(sorted(GHANA_PHONE_PREFIXES))}."
        )
    return None


# ── Full name ─────────────────────────────────────────────

_NAME_RE = re.compile(r"^[a-zA-Z\s.'-]+$")


def validate_full_name(name: str) -> str | None:
    """Return an error message if *name* is invalid, else ``None``."""
    if not name:
        return "full_name is required."
    if len(name) < 2:
        return "full_name must be at least 2 characters."
    if len(name) > 100:
        return "full_name must not exceed 100 characters."
    if not _NAME_RE.match(name):
        return "full_name may only contain letters, spaces, hyphens, apostrophes, and dots."
    return None


# ── Password ──────────────────────────────────────────────

MAX_PWD_LEN = 128
_MIN_PWD_LEN = 8


def validate_password(pwd: str) -> list[str]:
    """Return a list of password-strength errors (empty list = OK)."""
    if len(pwd) < _MIN_PWD_LEN:
        return ["password must be at least 8 characters."]
    if len(pwd) > MAX_PWD_LEN:
        return ["password must not exceed 128 characters."]
    errors = []
    if not re.search(r"[A-Z]", pwd):
        errors.append("password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", pwd):
        errors.append("password must contain at least one lowercase letter.")
    if not re.search(r"\d", pwd):
        errors.append("password must contain at least one digit.")
    return errors


# ── Role ──────────────────────────────────────────────────

VALID_ROLES = ("customer", "admin")


def validate_role(role: str) -> str | None:
    """Return an error message if *role* is invalid, else ``None``."""
    if role not in VALID_ROLES:
        return f"role must be one of {VALID_ROLES}."
    return None


# ── Wallet number & provider ─────────────────────────────

VALID_PROVIDERS = ("MTN", "Telecel", "AirtelTigo")

PREFIX_TO_PROVIDER = {
    "024": "MTN", "025": "MTN", "053": "MTN",
    "054": "MTN", "055": "MTN", "059": "MTN",
    "020": "Telecel", "050": "Telecel",
    "026": "AirtelTigo", "027": "AirtelTigo",
    "056": "AirtelTigo", "057": "AirtelTigo",
}

_GHANA_WALLET_RE = re.compile(r"^0[2-5]\d{8}$")


def validate_wallet_number(wallet_number: str) -> str | None:
    """Return an error message if *wallet_number* is invalid, else ``None``."""
    if not wallet_number:
        return "wallet_number is required."
    if not _GHANA_WALLET_RE.match(wallet_number):
        return "wallet_number must be a 10-digit Ghana number starting with 0 (e.g. 0241234567)."
    prefix = wallet_number[:3]
    if prefix not in PREFIX_TO_PROVIDER:
        return (
            f"wallet_number prefix '{prefix}' is not a recognized Ghana mobile money prefix. "
            f"Valid prefixes: {', '.join(sorted(PREFIX_TO_PROVIDER.keys()))}."
        )
    return None


def validate_provider(provider: str) -> str | None:
    """Return an error message if *provider* is invalid, else ``None``."""
    if not provider:
        return "provider is required."
    if provider not in VALID_PROVIDERS:
        return f"provider must be one of {list(VALID_PROVIDERS)}."
    return None


def validate_wallet_name(name: str) -> str | None:
    """Return an error message if *wallet_name* is invalid, else ``None``."""
    if not name:
        return "wallet_name is required (e.g. 'My MTN MoMo')."
    if len(name) < 2:
        return "wallet_name must be at least 2 characters."
    if len(name) > 50:
        return "wallet_name must not exceed 50 characters."
    return None


def cross_validate_prefix_provider(wallet_number: str, provider: str) -> str | None:
    """Return an error if the wallet prefix doesn't match the declared provider."""
    prefix = wallet_number[:3]
    expected = PREFIX_TO_PROVIDER.get(prefix)
    if expected and expected != provider:
        return (
            f"wallet_number prefix '{prefix}' belongs to {expected}, "
            f"but provider was set to '{provider}'. They must match."
        )
    return None


# ── Composite validators (called by services) ────────────

def validate_registration(data: dict) -> list[str]:
    """Validate all registration fields. Returns list of errors (empty = OK)."""
    errors = []

    # Required fields must exist
    required = ["full_name", "email", "phone_number", "password"]
    missing = [f for f in required if f not in data or data[f] is None]
    if missing:
        errors.append(f"Missing required fields: {', '.join(missing)}.")
        return errors

    # Individual field validations
    name = data["full_name"].strip() if isinstance(data["full_name"], str) else ""
    err = validate_full_name(name)
    if err:
        errors.append(err)

    email = data["email"].strip() if isinstance(data["email"], str) else ""
    err = validate_email(email)
    if err:
        errors.append(err)

    phone = data["phone_number"] if isinstance(data["phone_number"], str) else ""
    err = validate_ghana_phone(phone)
    if err:
        errors.append(err)

    pwd = data["password"] if isinstance(data["password"], str) else ""
    errors.extend(validate_password(pwd))

    role = data.get("role", "customer")
    err = validate_role(role)
    if err:
        errors.append(err)

    return errors


def validate_wallet(data: dict) -> list[str]:
    """Validate all wallet-linking fields. Returns list of errors (empty = OK)."""
    errors = []

    # Required fields must exist
    required = ["wallet_number", "provider", "wallet_name"]
    missing = [f for f in required if f not in data or data[f] is None]
    if missing:
        errors.append(f"Missing required fields: {', '.join(missing)}.")
        return errors

    # Normalize then validate wallet number
    wn = normalize_phone(
        data["wallet_number"] if isinstance(data["wallet_number"], str) else ""
    )
    err = validate_wallet_number(wn)
    if err:
        errors.append(err)

    # Validate provider
    provider = data["provider"].strip() if isinstance(data["provider"], str) else ""
    err = validate_provider(provider)
    if err:
        errors.append(err)

    # Cross-validate prefix vs. provider (only when both are individually valid)
    if not errors and wn and provider:
        err = cross_validate_prefix_provider(wn, provider)
        if err:
            errors.append(err)

    # Validate wallet name
    wname = data["wallet_name"].strip() if isinstance(data["wallet_name"], str) else ""
    err = validate_wallet_name(wname)
    if err:
        errors.append(err)

    return errors

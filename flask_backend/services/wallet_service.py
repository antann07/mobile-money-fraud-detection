"""Wallet service – business logic for wallet linking."""

import re
from models.wallet import create_wallet, get_wallets_by_user, wallet_exists, delete_wallet, set_wallet_primary

VALID_PROVIDERS = ("MTN", "Telecel", "AirtelTigo")

# Ghana network prefixes mapped to their provider
_PREFIX_TO_PROVIDER = {
    "024": "MTN", "025": "MTN", "053": "MTN", "054": "MTN", "055": "MTN", "059": "MTN",
    "020": "Telecel", "050": "Telecel",
    "026": "AirtelTigo", "027": "AirtelTigo", "056": "AirtelTigo", "057": "AirtelTigo",
}

_GHANA_WALLET_RE = re.compile(r"^0[2-5]\d{8}$")


def _validate_wallet(data: dict) -> list[str]:
    """Return validation errors (empty list = OK)."""
    errors = []

    # --- required fields existence check ---
    required = ["wallet_number", "provider", "wallet_name"]
    missing = [f for f in required if f not in data or data[f] is None]
    if missing:
        errors.append(f"Missing required fields: {', '.join(missing)}.")
        return errors

    # --- wallet_number ---
    wn = data["wallet_number"].strip() if isinstance(data["wallet_number"], str) else ""
    if not wn:
        errors.append("wallet_number is required.")
    elif not _GHANA_WALLET_RE.match(wn):
        errors.append("wallet_number must be a 10-digit Ghana number starting with 0 (e.g. 0241234567).")
    else:
        prefix = wn[:3]
        if prefix not in _PREFIX_TO_PROVIDER:
            errors.append(
                f"wallet_number prefix '{prefix}' is not a recognized Ghana mobile money prefix. "
                f"Valid prefixes: {', '.join(sorted(_PREFIX_TO_PROVIDER.keys()))}."
            )

    # --- provider ---
    provider = data["provider"].strip() if isinstance(data["provider"], str) else ""
    if not provider:
        errors.append("provider is required.")
    elif provider not in VALID_PROVIDERS:
        errors.append(f"provider must be one of {list(VALID_PROVIDERS)}.")

    # --- cross-validate: wallet prefix must match the declared provider ---
    if not errors and wn and provider:
        prefix = wn[:3]
        expected_provider = _PREFIX_TO_PROVIDER.get(prefix)
        if expected_provider and expected_provider != provider:
            errors.append(
                f"wallet_number prefix '{prefix}' belongs to {expected_provider}, "
                f"but provider was set to '{provider}'. They must match."
            )

    # --- wallet_name ---
    wname = data["wallet_name"].strip() if isinstance(data["wallet_name"], str) else ""
    if not wname:
        errors.append("wallet_name is required (e.g. 'My MTN MoMo').")
    elif len(wname) > 50:
        errors.append("wallet_name must not exceed 50 characters.")

    return errors


def add_wallet(user_id: int, data: dict) -> tuple[dict, int]:
    """Validate, check duplicates, then create a wallet."""
    errors = _validate_wallet(data)
    if errors:
        return {"success": False, "errors": errors}, 400

    wallet_number = data["wallet_number"].strip()
    provider = data["provider"].strip()

    if wallet_exists(wallet_number, provider):
        return {
            "success": False,
            "errors": [f"Wallet {wallet_number} is already registered with {provider}."],
        }, 409

    wallet = create_wallet(
        user_id=user_id,
        wallet_number=wallet_number,
        provider=provider,
        wallet_name=data["wallet_name"].strip(),
        is_primary=bool(data.get("is_primary", False)),
    )

    # create_wallet returns None on UNIQUE constraint violation (race condition)
    if wallet is None:
        return {
            "success": False,
            "errors": [f"Wallet {wallet_number} is already registered with {provider}."],
        }, 409

    return {
        "success": True,
        "message": "Wallet linked successfully.",
        "wallet": wallet,
    }, 201


def list_wallets(user_id: int) -> tuple[dict, int]:
    """Return all wallets for the authenticated user."""
    wallets = get_wallets_by_user(user_id)
    return {
        "success": True,
        "count": len(wallets),
        "wallets": wallets,
    }, 200


def remove_wallet(user_id: int, wallet_id: int) -> tuple[dict, int]:
    """Remove a wallet belonging to user_id."""
    deleted = delete_wallet(wallet_id, user_id)
    if not deleted:
        return {"success": False, "errors": ["Wallet not found or access denied."]}, 404
    return {"success": True, "message": "Wallet removed."}, 200


def set_primary_wallet(user_id: int, wallet_id: int) -> tuple[dict, int]:
    """Set a wallet as primary and return the updated wallet list."""
    updated = set_wallet_primary(wallet_id, user_id)
    if not updated:
        return {"success": False, "errors": ["Wallet not found or access denied."]}, 404
    wallets = get_wallets_by_user(user_id)
    return {"success": True, "message": "Primary wallet updated.", "wallets": wallets}, 200

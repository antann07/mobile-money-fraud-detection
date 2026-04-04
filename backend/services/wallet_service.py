"""Wallet service -- business logic for wallet linking."""

from models.wallet_model import create_wallet, get_wallets_by_user, wallet_exists
from utils.validators import validate_wallet, normalize_phone


# ── Public API ────────────────────────────────────────────

def add_wallet(user_id: int, data: dict) -> tuple[dict, int]:
    """Validate, check duplicates, then create a wallet."""
    errors = validate_wallet(data)
    if errors:
        return {"success": False, "errors": errors}, 400

    wallet_number = normalize_phone(data["wallet_number"])
    provider = data["provider"].strip()

    if wallet_exists(user_id, wallet_number):
        return {
            "success": False,
            "errors": [f"You have already linked wallet {wallet_number}."],
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
            "errors": [f"You have already linked wallet {wallet_number}."],
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

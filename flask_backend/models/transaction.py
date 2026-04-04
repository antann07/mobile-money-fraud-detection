"""
Transaction model – CRUD helpers for the transactions table.

Provides:
  create_transaction()           — insert a new row
  get_transaction_by_id()        — fetch one by primary key
  get_transactions_by_wallet_ids() — fetch all for a list of wallets
"""

from db import get_db, PH, IntegrityError, insert_returning_id, query


def create_transaction(
    wallet_id: int,
    transaction_type: str,
    direction: str,
    amount: float,
    transaction_time: str,
    transaction_reference: str = None,
    balance_before: float = None,
    balance_after: float = None,
    location_info: str = None,
    device_info: str = None,
    source_channel: str = "manual",
    raw_message: str = None,
) -> dict | None:
    """
    Insert a new transaction row and return it as a dict.
    Returns None if an integrity constraint is violated.
    """
    conn = get_db()
    try:
        new_id = insert_returning_id(
            conn,
            f"""
            INSERT INTO transactions
                (wallet_id, transaction_reference, transaction_type, direction,
                 amount, balance_before, balance_after, transaction_time,
                 location_info, device_info, source_channel, raw_message)
            VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH})
            """,
            (
                wallet_id,
                transaction_reference,
                transaction_type,
                direction,
                amount,
                balance_before,
                balance_after,
                transaction_time,
                location_info,
                device_info,
                source_channel,
                raw_message,
            ),
        )
        conn.commit()
        return get_transaction_by_id(new_id)
    except IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_transaction_by_id(txn_id: int) -> dict | None:
    """Fetch a single transaction by its primary key."""
    conn = get_db()
    try:
        row = query(
            conn,
            f"SELECT * FROM transactions WHERE id = {PH}",
            (txn_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_transactions_by_wallet_ids(wallet_ids: list[int]) -> list[dict]:
    """Return all transactions for a list of wallet IDs, newest first."""
    if not wallet_ids:
        return []
    conn = get_db()
    try:
        placeholders = ",".join(PH for _ in wallet_ids)
        rows = query(
            conn,
            f"""
            SELECT * FROM transactions
            WHERE wallet_id IN ({placeholders})
            ORDER BY transaction_time DESC
            """,
            wallet_ids,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

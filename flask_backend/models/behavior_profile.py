"""
UserBehaviorProfile model — CRUD helpers for the user_behavior_profiles table.

Stores aggregated patterns of each user's normal transaction behavior.
Used by the fraud detection engine to calculate behavior_risk_score.

Relationship: one profile per user (1:1 with users).

JSON fields (stored as TEXT in SQLite):
  usual_senders          — ["0771234567", "0781234567"]
  usual_transaction_types — ["deposit", "transfer"]
  common_message_patterns — hashes or regex snippets of previously seen messages

Provides:
  get_or_create_profile()    — fetch existing profile or create a blank one
  get_profile_by_user()      — fetch profile for a user
  update_profile()           — update profile fields after recalculation
"""

import json
from db import get_db, PH, IntegrityError, query, execute


def get_profile_by_user(user_id: int) -> dict | None:
    """Fetch the behavior profile for a user."""
    conn = get_db()
    try:
        row = query(
            conn,
            f"SELECT * FROM user_behavior_profiles WHERE user_id = {PH}",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        profile = dict(row)
        # Parse JSON text fields into Python lists for convenience
        profile["usual_senders"] = json.loads(profile.get("usual_senders") or "[]")
        profile["usual_transaction_types"] = json.loads(profile.get("usual_transaction_types") or "[]")
        profile["common_message_patterns"] = json.loads(profile.get("common_message_patterns") or "[]")
        return profile
    finally:
        conn.close()


def get_or_create_profile(user_id: int) -> dict:
    """
    Return the user's behavior profile, creating a blank one if none exists.
    Always returns a dict (never None).
    """
    profile = get_profile_by_user(user_id)
    if profile is not None:
        return profile

    conn = get_db()
    try:
        execute(
            conn,
            f"INSERT INTO user_behavior_profiles (user_id) VALUES ({PH})",
            (user_id,),
        )
        conn.commit()
    except IntegrityError:
        # Race condition: another request created it first — that's fine
        conn.rollback()
    finally:
        conn.close()

    return get_profile_by_user(user_id)


def update_profile(user_id: int, **fields) -> dict | None:
    """
    Update one or more fields on a user's behavior profile.

    Usage:
        update_profile(user_id,
            avg_incoming_amount=45000.0,
            max_incoming_amount=500000.0,
            usual_senders=["0771234567", "0781234567"],
            avg_transaction_frequency=2.5,
        )

    List/dict values for JSON fields are auto-serialized to JSON strings.
    Returns the updated profile, or None if no profile exists.
    """
    ALLOWED_FIELDS = {
        "avg_incoming_amount", "max_incoming_amount",
        "usual_senders", "usual_transaction_types", "common_message_patterns",
        "total_checks_count", "avg_transaction_frequency",
    }
    JSON_FIELDS = {"usual_senders", "usual_transaction_types", "common_message_patterns"}

    updates = {k: v for k, v in fields.items() if k in ALLOWED_FIELDS}
    if not updates:
        return get_profile_by_user(user_id)

    # Serialize list/dict values to JSON for storage
    for key in JSON_FIELDS:
        if key in updates and isinstance(updates[key], (list, dict)):
            updates[key] = json.dumps(updates[key])

    # Always bump last_updated
    set_clause = ", ".join(f"{col} = {PH}" for col in updates)
    set_clause += ", last_updated = CURRENT_TIMESTAMP"
    values = list(updates.values()) + [user_id]

    conn = get_db()
    try:
        execute(
            conn,
            f"UPDATE user_behavior_profiles SET {set_clause} WHERE user_id = {PH}",
            values,
        )
        conn.commit()
        return get_profile_by_user(user_id)
    finally:
        conn.close()

"""
Local review-flow test helper.

Safe, reversible operations for testing the admin Review Queue
against the local SQLite database.

Usage:
  python test_review_setup.py inspect                  # show all predictions + linked message_checks
  python test_review_setup.py flag [PRED_ID]           # flag a prediction as suspicious (default: id 1)
  python test_review_setup.py flag [PRED_ID] fraud     # flag a prediction as likely_fraudulent
  python test_review_setup.py restore [PRED_ID]        # restore original label (saved before flagging)
  python test_review_setup.py verify                   # confirm the review queue query returns rows
  python test_review_setup.py reviews                  # show all fraud_review rows
  python test_review_setup.py cleanup [PRED_ID]        # restore prediction + delete test review row

Run from the flask_backend/ directory.
"""

import sys
import json
import sqlite3
from pathlib import Path

DB_PATH = "fraud_detection.db"
# Stores original values so restore is always safe
BACKUP_FILE = Path(__file__).parent / ".test_review_backup.json"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── inspect ──────────────────────────────────────────────────
def inspect():
    """Show every prediction joined with its message_check summary."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT
            p.id              AS pred_id,
            p.message_check_id,
            p.predicted_label,
            p.confidence_score,
            mc.source_channel,
            mc.amount,
            mc.counterparty_name,
            mc.counterparty_number,
            mc.created_at
        FROM predictions p
        JOIN message_checks mc ON mc.id = p.message_check_id
        ORDER BY p.id
        """
    ).fetchall()

    print("=== Predictions + linked message_checks ===")
    print(f"{'pred_id':<8} {'mc_id':<6} {'label':<20} {'conf':<6} {'channel':<10} {'amount':<8} {'counterparty':<20} {'created_at'}")
    print("-" * 110)
    for r in rows:
        d = dict(r)
        cp = d["counterparty_name"] or d["counterparty_number"] or "—"
        print(
            f"{d['pred_id']:<8} {d['message_check_id']:<6} {d['predicted_label']:<20} "
            f"{d['confidence_score']:<6.2f} {d['source_channel']:<10} "
            f"{d['amount'] or 0:<8.2f} {cp:<20} {d['created_at']}"
        )
    print(f"\nTotal: {len(rows)}")
    conn.close()


# ── flag ─────────────────────────────────────────────────────
def flag(pred_id: int, label: str = "suspicious"):
    """Change one prediction's label. Saves original values to a backup file."""
    if label not in ("suspicious", "likely_fraudulent"):
        print(f"ERROR: label must be 'suspicious' or 'likely_fraudulent', got '{label}'")
        return

    conn = get_conn()

    # Read current row first (so we can restore later)
    row = conn.execute(
        "SELECT id, message_check_id, predicted_label, confidence_score FROM predictions WHERE id = ?",
        (pred_id,),
    ).fetchone()

    if not row:
        print(f"ERROR: No prediction with id={pred_id}. Run 'inspect' to see available IDs.")
        conn.close()
        return

    original = dict(row)

    # Don't overwrite backup if already flagged (re-running flag is idempotent)
    backup = _load_backup()
    if str(pred_id) not in backup:
        backup[str(pred_id)] = {
            "predicted_label": original["predicted_label"],
            "confidence_score": original["confidence_score"],
        }
        _save_backup(backup)
        print(f"Backed up original: label={original['predicted_label']}, conf={original['confidence_score']}")

    # Apply the flag
    new_conf = 0.72 if label == "suspicious" else 0.88
    conn.execute(
        "UPDATE predictions SET predicted_label = ?, confidence_score = ? WHERE id = ?",
        (label, new_conf, pred_id),
    )
    conn.commit()

    # Verify
    updated = conn.execute(
        """
        SELECT p.id, p.message_check_id, p.predicted_label, p.confidence_score, mc.amount
        FROM predictions p JOIN message_checks mc ON mc.id = p.message_check_id
        WHERE p.id = ?
        """,
        (pred_id,),
    ).fetchone()
    conn.close()

    d = dict(updated)
    print(f"FLAGGED: pred_id={d['id']}, message_check_id={d['message_check_id']}, "
          f"label={d['predicted_label']}, confidence={d['confidence_score']}, amount={d['amount']}")
    print(f"\nThis row should now appear in the Review Queue at /review-queue")
    print(f"Review Detail page: /review-queue/{d['message_check_id']}")


# ── restore ──────────────────────────────────────────────────
def restore(pred_id: int):
    """Restore the original label from the backup file."""
    backup = _load_backup()
    key = str(pred_id)

    if key not in backup:
        print(f"No backup found for pred_id={pred_id}. Nothing to restore.")
        print("(Was it already restored, or was 'flag' never run for this ID?)")
        return

    orig = backup[key]
    conn = get_conn()
    conn.execute(
        "UPDATE predictions SET predicted_label = ?, confidence_score = ? WHERE id = ?",
        (orig["predicted_label"], orig["confidence_score"], pred_id),
    )
    conn.commit()

    row = conn.execute(
        "SELECT id, predicted_label, confidence_score FROM predictions WHERE id = ?",
        (pred_id,),
    ).fetchone()
    conn.close()

    # Remove from backup
    del backup[key]
    _save_backup(backup)

    d = dict(row)
    print(f"RESTORED: pred_id={d['id']}, label={d['predicted_label']}, confidence={d['confidence_score']}")


# ── verify ───────────────────────────────────────────────────
def verify():
    """Run the same query the Review Queue uses and show what it returns."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT
            mc.id               AS message_check_id,
            mc.created_at,
            mc.source_channel,
            mc.counterparty_name,
            mc.counterparty_number,
            mc.amount,
            mc.currency,
            p.predicted_label,
            p.confidence_score,
            fr.review_status,
            fr.reviewer_label
        FROM message_checks mc
        JOIN predictions p ON p.message_check_id = mc.id
        LEFT JOIN fraud_reviews fr ON fr.message_check_id = mc.id
        WHERE p.predicted_label IN ('suspicious', 'likely_fraudulent')
        ORDER BY mc.created_at DESC
        """
    ).fetchall()
    conn.close()

    if not rows:
        print("Review Queue would show: EMPTY (no flagged predictions)")
        print("Run 'flag' first to create test data.")
        return

    print(f"=== Review Queue would show {len(rows)} row(s) ===")
    for r in rows:
        d = dict(r)
        cp = d["counterparty_name"] or d["counterparty_number"] or "—"
        status = d["review_status"] or "pending"
        print(f"  mc_id={d['message_check_id']}  label={d['predicted_label']}  "
              f"conf={d['confidence_score']}  amount={d['amount']}  "
              f"review_status={status}  counterparty={cp}")


# ── reviews ──────────────────────────────────────────────────
def reviews():
    """Show all fraud_review rows."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM fraud_reviews ORDER BY id").fetchall()
    conn.close()

    if not rows:
        print("No fraud_review rows yet. Submit a review from /review-queue/<id> to create one.")
        return

    print(f"=== fraud_reviews ({len(rows)} row(s)) ===")
    for r in rows:
        print(dict(r))


# ── cleanup ──────────────────────────────────────────────────
def cleanup(pred_id: int):
    """Restore prediction + delete any test review row for that message_check."""
    # Restore prediction first
    restore(pred_id)

    # Find and delete the review
    conn = get_conn()
    row = conn.execute(
        "SELECT message_check_id FROM predictions WHERE id = ?", (pred_id,)
    ).fetchone()

    if row:
        mc_id = row["message_check_id"]
        deleted = conn.execute(
            "DELETE FROM fraud_reviews WHERE message_check_id = ?", (mc_id,)
        ).rowcount
        conn.commit()
        if deleted:
            print(f"Deleted {deleted} review(s) for message_check_id={mc_id}")
        else:
            print(f"No reviews to delete for message_check_id={mc_id}")
    conn.close()


# ── backup helpers ───────────────────────────────────────────
def _load_backup() -> dict:
    if BACKUP_FILE.exists():
        return json.loads(BACKUP_FILE.read_text())
    return {}


def _save_backup(data: dict):
    if data:
        BACKUP_FILE.write_text(json.dumps(data, indent=2))
    elif BACKUP_FILE.exists():
        BACKUP_FILE.unlink()


# ── CLI ──────────────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else "inspect"

    if cmd == "inspect":
        inspect()
    elif cmd == "flag":
        pid = int(args[1]) if len(args) > 1 else 1
        lbl = args[2] if len(args) > 2 else "suspicious"
        flag(pid, lbl)
    elif cmd == "restore":
        pid = int(args[1]) if len(args) > 1 else 1
        restore(pid)
    elif cmd == "verify":
        verify()
    elif cmd == "reviews":
        reviews()
    elif cmd == "cleanup":
        pid = int(args[1]) if len(args) > 1 else 1
        cleanup(pid)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)

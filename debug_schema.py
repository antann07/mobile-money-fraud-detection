"""Inspect actual DB table columns vs expected schema."""
import sqlite3

conn = sqlite3.connect("flask_backend/fraud_detection.db")

tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("=== TABLES ===")
for t in tables:
    print(f"  {t[0]}")

for table_name in ["message_checks", "predictions", "user_behavior_profiles", "fraud_reviews"]:
    print(f"\n=== {table_name} columns ===")
    cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if not cols:
        print("  TABLE DOES NOT EXIST!")
    else:
        for c in cols:
            print(f"  {c[1]:30s}  {c[2]:15s}  notnull={c[3]}  default={c[4]}")

conn.close()

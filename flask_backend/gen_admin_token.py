"""Verify admin users and generate a working admin token for testing."""
import json, base64
from db import get_db
from services.auth_service import generate_token

# 1. Show all users and their roles
conn = get_db()
rows = conn.execute("SELECT id, email, role FROM users ORDER BY id").fetchall()
print("=== ALL USERS ===")
for r in rows:
    d = dict(r)
    marker = " <-- ADMIN" if d["role"] == "admin" else ""
    print(f"  id={d['id']}  email={d['email']}  role={d['role']}{marker}")

# 2. Find admin users
admins = conn.execute("SELECT id, email, role FROM users WHERE role = 'admin'").fetchall()
conn.close()

if not admins:
    print("\n*** NO ADMIN USERS FOUND! ***")
    print("Run:  UPDATE users SET role = 'admin' WHERE id = <your_id>;")
    raise SystemExit(1)

admin = dict(admins[0])
print(f"\n=== GENERATING TOKEN FOR admin id={admin['id']} ({admin['email']}) ===")

# 3. Generate token
token = generate_token(admin["id"], admin["role"])

# 4. Decode and show JWT payload
parts = token.split(".")
padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
payload = json.loads(base64.urlsafe_b64decode(padded))
print(f"  JWT payload: {json.dumps(payload)}")

# 5. Print the token for manual injection
print(f"\n=== PASTE THIS INTO BROWSER CONSOLE TO FIX NOW ===")
print(f'localStorage.setItem("token", "{token}"); window.location.reload();')

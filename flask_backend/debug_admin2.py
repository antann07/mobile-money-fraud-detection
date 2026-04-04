"""Debug: generate an admin token directly and test the review endpoint."""
import json, base64, urllib.request, urllib.error, sys
sys.path.insert(0, ".")

from db import get_db
from services.auth_service import generate_token

# 1. Verify DB role
conn = get_db()
row = conn.execute("SELECT id, full_name, email, role FROM users WHERE id = 2").fetchone()
user = dict(row)
conn.close()
print("=== DB USER ===")
print(f"  id={user['id']}  name={user['full_name']}  email={user['email']}  role={user['role']}")

# 2. Generate a fresh admin token (same function login uses)
token = generate_token(user["id"], user["role"])
print(f"\n=== GENERATED TOKEN ===")
print(f"  token={token[:50]}...")

# 3. Decode JWT to verify contents
parts = token.split(".")
padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
jwt_payload = json.loads(base64.urlsafe_b64decode(padded))
print(f"\n=== JWT PAYLOAD ===")
print(f"  user_id={jwt_payload.get('user_id')}")
print(f"  role={jwt_payload.get('role')}")

# 4. Call the review endpoint with this token
print(f"\n=== GET /api/reviews/flagged ===")
req = urllib.request.Request(
    "http://127.0.0.1:5001/api/reviews/flagged",
    headers={"Authorization": f"Bearer {token}"},
)
try:
    resp = urllib.request.urlopen(req)
    body = json.loads(resp.read())
    print(f"  Status: {resp.status}")
    print(f"  success: {body.get('success')}")
    print(f"  count: {body.get('count')}")
except urllib.error.HTTPError as e:
    body = json.loads(e.read())
    print(f"  Status: {e.code}")
    print(f"  errors: {body.get('errors')}")

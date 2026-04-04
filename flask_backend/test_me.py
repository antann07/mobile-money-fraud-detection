"""Test the /api/auth/me endpoint with a fresh admin token."""
import json, urllib.request, urllib.error
from db import get_db
from services.auth_service import generate_token

# Generate fresh admin token
conn = get_db()
row = conn.execute("SELECT id, role FROM users WHERE id = 2").fetchone()
conn.close()
user = dict(row)
token = generate_token(user["id"], user["role"])

# Call /api/auth/me
req = urllib.request.Request(
    "http://127.0.0.1:5001/api/auth/me",
    headers={"Authorization": f"Bearer {token}"},
)
try:
    resp = urllib.request.urlopen(req)
    body = json.loads(resp.read())
    print(f"Status: {resp.status}")
    print(f"token_role: {body.get('token_role')}")
    print(f"db_role: {body.get('db_role')}")
    print(f"Match: {body.get('token_role') == body.get('db_role')}")
except urllib.error.HTTPError as e:
    print(f"Status: {e.code}")
    print(json.loads(e.read()))

# Also call /api/reviews/flagged
print()
req2 = urllib.request.Request(
    "http://127.0.0.1:5001/api/reviews/flagged",
    headers={"Authorization": f"Bearer {token}"},
)
try:
    resp2 = urllib.request.urlopen(req2)
    body2 = json.loads(resp2.read())
    print(f"/api/reviews/flagged -> {resp2.status} (count={body2.get('count')})")
except urllib.error.HTTPError as e:
    print(f"/api/reviews/flagged -> {e.code}")
    print(json.loads(e.read()))

"""Debug: login as admin user and inspect the JWT payload."""
import json, base64, urllib.request

# 1. Login
payload = json.dumps({"email": "antann07@gmail.com", "password": "Test1234"}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:5001/api/auth/login",
    data=payload,
    headers={"Content-Type": "application/json"},
)
try:
    resp = urllib.request.urlopen(req)
    body = json.loads(resp.read())
except urllib.error.HTTPError as e:
    body = json.loads(e.read())
    print(f"LOGIN FAILED ({e.code}):", json.dumps(body, indent=2))
    raise SystemExit(1)

print("=== LOGIN RESPONSE ===")
print("success:", body.get("success"))
print("user object:", json.dumps(body.get("user"), indent=2))
print("user.role:", body.get("user", {}).get("role"))

# 2. Decode the JWT payload (base64 only, no verification)
token = body.get("token", "")
if token:
    parts = token.split(".")
    # Add padding
    padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
    jwt_payload = json.loads(base64.urlsafe_b64decode(padded))
    print("\n=== JWT PAYLOAD ===")
    print(json.dumps(jwt_payload, indent=2))
    print("jwt.role:", jwt_payload.get("role"))
else:
    print("\nNo token in response!")

# 3. Test the review endpoint with this token
print("\n=== REVIEW ENDPOINT TEST ===")
req2 = urllib.request.Request(
    "http://127.0.0.1:5001/api/reviews/flagged",
    headers={"Authorization": f"Bearer {token}"},
)
try:
    resp2 = urllib.request.urlopen(req2)
    print(f"Status: {resp2.status}")
    review_body = json.loads(resp2.read())
    print("success:", review_body.get("success"))
    print("count:", review_body.get("count"))
except urllib.error.HTTPError as e:
    print(f"Status: {e.code}")
    err_body = json.loads(e.read())
    print("errors:", err_body.get("errors"))

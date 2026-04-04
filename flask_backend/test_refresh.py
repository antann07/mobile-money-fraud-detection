"""Test the /api/auth/refresh endpoint."""
import requests, jwt, json, sys
sys.path.insert(0, ".")
from config import get_config
from services.auth_service import generate_token

cfg = get_config()

# Generate a token with role=customer for the admin user (simulating stale token)
stale_token = generate_token(user_id=2, role="customer")
payload = jwt.decode(stale_token, cfg.SECRET_KEY, algorithms=["HS256"])
print(f"Stale token role: {payload['role']}")

# Call refresh endpoint with the stale token
r = requests.post("http://127.0.0.1:5001/api/auth/refresh",
                   headers={"Authorization": f"Bearer {stale_token}"})
print(f"Refresh status: {r.status_code}")
data = r.json()
print(f"Refresh response: {json.dumps(data, indent=2)}")

if data.get("token"):
    new_payload = jwt.decode(data["token"], cfg.SECRET_KEY, algorithms=["HS256"])
    print(f"\nNew token role: {new_payload['role']}")
    if new_payload["role"] == "admin":
        print("SUCCESS: Refresh endpoint correctly updated role from customer -> admin")
    else:
        print("FAIL: Role was not updated")

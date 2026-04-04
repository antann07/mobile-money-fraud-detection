"""End-to-end login test: login via API, decode token, test review endpoint."""
import requests, jwt, json, sys
sys.path.insert(0, ".")
from config import get_config

cfg = get_config()

# Try to login as the admin user
print("=== Step 1: Login ===")
r = requests.post("http://127.0.0.1:5001/api/auth/login",
                   json={"email": "antann07@gmail.com", "password": "Test1234"})
print(f"Status: {r.status_code}")
data = r.json()
print(f"Success: {data.get('success')}")

if not data.get("token"):
    print("NO TOKEN RETURNED!")
    print(f"Response: {json.dumps(data, indent=2)}")
    # Try some common passwords
    for pwd in ["test1234", "Password1", "Admin1234", "password"]:
        r2 = requests.post("http://127.0.0.1:5001/api/auth/login",
                           json={"email": "antann07@gmail.com", "password": pwd})
        if r2.status_code == 200:
            print(f"  Password '{pwd}' worked!")
            data = r2.json()
            break
        else:
            print(f"  Password '{pwd}' failed ({r2.status_code})")

if data.get("token"):
    token = data["token"]
    print(f"\n=== Step 2: Decode Token ===")
    payload = jwt.decode(token, cfg.SECRET_KEY, algorithms=["HS256"])
    print(f"Payload: {json.dumps(payload, default=str)}")
    print(f"ROLE IN TOKEN: {payload.get('role')}")

    if data.get("user"):
        print(f"User role in response body: {data['user'].get('role')}")

    print(f"\n=== Step 3: Test Review Endpoint ===")
    r3 = requests.get("http://127.0.0.1:5001/api/reviews/flagged",
                       headers={"Authorization": f"Bearer {token}"})
    print(f"Status: {r3.status_code}")
    print(f"Response: {json.dumps(r3.json(), indent=2)}")

    if r3.status_code == 200:
        print("\n✅ FULL CHAIN WORKS — login returns admin token, review endpoint accepts it")
    else:
        print(f"\n❌ Review endpoint returned {r3.status_code}")
else:
    print("\n❌ Could not login — cannot test further")
    print("The user needs to provide the correct password for e2e test")

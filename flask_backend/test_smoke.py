"""Quick smoke test for all Phase 1 endpoints."""
import json, os, sys

# Ensure imports resolve when run from flask_backend/
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app

app = create_app()
client = app.test_client()

passed = 0
failed = 0

def check(label, resp, expected_status):
    global passed, failed
    ok = resp.status_code == expected_status
    mark = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    print(f"\n{'='*55}")
    print(f"[{mark}] {label}  ->  HTTP {resp.status_code} (expected {expected_status})")
    print(json.dumps(resp.get_json(), indent=2))
    if not ok:
        print(f"  *** EXPECTED {expected_status}, GOT {resp.status_code} ***")

# ==================== HEALTH ====================
check("Health check", client.get("/api/health"), 200)

# ==================== REGISTRATION VALIDATION ====================

# Missing all required fields
check("Register: empty body",
    client.post("/api/auth/register", json={}), 400)

# Missing some fields
check("Register: missing password",
    client.post("/api/auth/register", json={
        "full_name": "Kofi", "email": "k@x.com", "phone_number": "0241234567"
    }), 400)

# Bad email
check("Register: invalid email",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "not-an-email",
        "phone_number": "0241234567", "password": "Secure123"
    }), 400)

# Non-Ghana phone (generic international)
check("Register: non-Ghana phone",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "a@b.com",
        "phone_number": "+14155551234", "password": "Secure123"
    }), 400)

# Invalid Ghana prefix (031 doesn't exist)
check("Register: invalid Ghana prefix",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "a@b.com",
        "phone_number": "0311234567", "password": "Secure123"
    }), 400)

# Weak password (no uppercase)
check("Register: weak password (no uppercase)",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "a@b.com",
        "phone_number": "0241234567", "password": "weakpass1"
    }), 400)

# Weak password (no digit)
check("Register: weak password (no digit)",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "a@b.com",
        "phone_number": "0241234567", "password": "WeakPasss"
    }), 400)

# Invalid role
check("Register: bad role",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "a@b.com",
        "phone_number": "0241234567", "password": "Secure123", "role": "hacker"
    }), 400)

# Short name
check("Register: name too short",
    client.post("/api/auth/register", json={
        "full_name": "K", "email": "a@b.com",
        "phone_number": "0241234567", "password": "Secure123"
    }), 400)

# Name with numbers
check("Register: name with numbers",
    client.post("/api/auth/register", json={
        "full_name": "Kofi123", "email": "a@b.com",
        "phone_number": "0241234567", "password": "Secure123"
    }), 400)

# ==================== VALID REGISTRATION ====================

# Valid MTN user
check("Register: valid MTN user",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah",
        "email": "kofi@example.com",
        "phone_number": "0241234567",
        "password": "SecurePass1",
        "role": "customer"
    }), 201)

# Valid Telecel user
check("Register: valid Telecel user",
    client.post("/api/auth/register", json={
        "full_name": "Ama Darko",
        "email": "ama@example.com",
        "phone_number": "0201234567",
        "password": "StrongPwd9",
    }), 201)

# Valid AirtelTigo user
check("Register: valid AirtelTigo user",
    client.post("/api/auth/register", json={
        "full_name": "Kwame Asante",
        "email": "kwame@example.com",
        "phone_number": "0261234567",
        "password": "GoodPass3",
    }), 201)

# Duplicate email
check("Register: duplicate email", 
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah",
        "email": "kofi@example.com",
        "phone_number": "0241234567",
        "password": "SecurePass1",
    }), 409)

# ==================== LOGIN VALIDATION ====================

check("Login: empty body",
    client.post("/api/auth/login", json={}), 400)

check("Login: wrong password",
    client.post("/api/auth/login", json={
        "email": "kofi@example.com", "password": "WrongPass1"
    }), 401)

check("Login: nonexistent email",
    client.post("/api/auth/login", json={
        "email": "nobody@example.com", "password": "Whatever1"
    }), 401)

resp = client.post("/api/auth/login", json={
    "email": "kofi@example.com", "password": "SecurePass1"
})
check("Login: valid", resp, 200)
token = resp.get_json()["token"]
auth = {"Authorization": f"Bearer {token}"}

# ==================== WALLET VALIDATION ====================

# Missing fields
check("Wallet: empty body",
    client.post("/api/wallets", json={}, headers=auth), 400)

check("Wallet: missing provider",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "wallet_name": "My Wallet"
    }, headers=auth), 400)

# Invalid wallet number (not 10 digits)
check("Wallet: short number",
    client.post("/api/wallets", json={
        "wallet_number": "024123", "provider": "MTN", "wallet_name": "X"
    }, headers=auth), 400)

# Invalid Ghana prefix
check("Wallet: bad prefix (031)",
    client.post("/api/wallets", json={
        "wallet_number": "0311234567", "provider": "MTN", "wallet_name": "X"
    }, headers=auth), 400)

# Prefix/provider mismatch (024 = MTN but declared as Telecel)
check("Wallet: MTN number + Telecel provider",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "provider": "Telecel", "wallet_name": "Mismatch"
    }, headers=auth), 400)

# Invalid provider name
check("Wallet: invalid provider",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "provider": "Vodafone", "wallet_name": "X"
    }, headers=auth), 400)

# Wallet name too long
check("Wallet: name too long",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "provider": "MTN",
        "wallet_name": "A" * 51
    }, headers=auth), 400)

# ==================== VALID WALLETS ====================

check("Wallet: valid MTN",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "provider": "MTN",
        "wallet_name": "My MTN MoMo", "is_primary": True
    }, headers=auth), 201)

check("Wallet: duplicate",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "provider": "MTN",
        "wallet_name": "My MTN MoMo"
    }, headers=auth), 409)

check("Wallet: valid Telecel (020 prefix)",
    client.post("/api/wallets", json={
        "wallet_number": "0201234567", "provider": "Telecel",
        "wallet_name": "Telecel Cash"
    }, headers=auth), 201)

check("Wallet: valid AirtelTigo (027 prefix)",
    client.post("/api/wallets", json={
        "wallet_number": "0271234567", "provider": "AirtelTigo",
        "wallet_name": "Tigo Cash"
    }, headers=auth), 201)

# ==================== LIST WALLETS ====================

check("List wallets", client.get("/api/wallets", headers=auth), 200)

# ==================== AUTH ERRORS ====================

check("Wallet: no token",
    client.get("/api/wallets"), 401)

check("Wallet: bad token",
    client.get("/api/wallets", headers={"Authorization": "Bearer garbage"}), 401)

check("Wallet: missing Bearer",
    client.get("/api/wallets", headers={"Authorization": token}), 401)

# ==================== SUMMARY ====================
print(f"\n{'='*55}")
total = passed + failed
print(f"RESULTS: {passed}/{total} passed, {failed}/{total} failed")
if failed == 0:
    print("All tests passed.")
else:
    print(f"*** {failed} test(s) FAILED ***")
    sys.exit(1)

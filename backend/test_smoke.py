"""Quick smoke test for all Phase 1 endpoints."""
import json, os, sys

# Ensure imports resolve when run from backend/
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


# ====================================================================
# 1. HEALTH CHECK
# ====================================================================
check("Health check", client.get("/api/health"), 200)

# ====================================================================
# 2. REGISTRATION - validation
# ====================================================================

check("Register: non-JSON body",
    client.post("/api/auth/register", data="not json",
                content_type="text/plain"), 400)

check("Register: empty body",
    client.post("/api/auth/register", json={}), 400)

check("Register: missing password",
    client.post("/api/auth/register", json={
        "full_name": "Kofi", "email": "k@x.com", "phone_number": "0241234567"
    }), 400)

check("Register: empty string fields",
    client.post("/api/auth/register", json={
        "full_name": "", "email": "", "phone_number": "", "password": ""
    }), 400)

check("Register: invalid email",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "not-an-email",
        "phone_number": "0241234567", "password": "Secure123"
    }), 400)

check("Register: non-Ghana phone",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "a@b.com",
        "phone_number": "+14155551234", "password": "Secure123"
    }), 400)

check("Register: invalid Ghana prefix",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "a@b.com",
        "phone_number": "0311234567", "password": "Secure123"
    }), 400)

check("Register: weak password (no uppercase)",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "a@b.com",
        "phone_number": "0241234567", "password": "weakpass1"
    }), 400)

check("Register: weak password (no digit)",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "a@b.com",
        "phone_number": "0241234567", "password": "WeakPasss"
    }), 400)

check("Register: weak password (too short)",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "a@b.com",
        "phone_number": "0241234567", "password": "Ab1"
    }), 400)

check("Register: bad role",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah", "email": "a@b.com",
        "phone_number": "0241234567", "password": "Secure123", "role": "hacker"
    }), 400)

check("Register: name too short",
    client.post("/api/auth/register", json={
        "full_name": "K", "email": "a@b.com",
        "phone_number": "0241234567", "password": "Secure123"
    }), 400)

check("Register: name with numbers",
    client.post("/api/auth/register", json={
        "full_name": "Kofi123", "email": "a@b.com",
        "phone_number": "0241234567", "password": "Secure123"
    }), 400)

# ====================================================================
# 3. REGISTRATION - success
# ====================================================================

resp = client.post("/api/auth/register", json={
    "full_name": "Kofi Mensah",
    "email": "kofi@example.com",
    "phone_number": "0241234567",
    "password": "SecurePass1",
    "role": "customer"
})
check("Register: valid MTN user", resp, 201)
# Verify response shape
body = resp.get_json()
assert body["success"] is True, "success must be True"
assert "token" in body, "token must be present"
assert "password_hash" not in body.get("user", {}), "password_hash must NOT be in response"

check("Register: valid Telecel user",
    client.post("/api/auth/register", json={
        "full_name": "Ama Darko",
        "email": "ama@example.com",
        "phone_number": "0201234567",
        "password": "StrongPwd9",
    }), 201)

check("Register: valid AirtelTigo user",
    client.post("/api/auth/register", json={
        "full_name": "Kwame Asante",
        "email": "kwame@example.com",
        "phone_number": "0261234567",
        "password": "GoodPass3",
    }), 201)

check("Register: duplicate email",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah",
        "email": "kofi@example.com",
        "phone_number": "0241234567",
        "password": "SecurePass1",
    }), 409)

check("Register: duplicate email (case-insensitive)",
    client.post("/api/auth/register", json={
        "full_name": "Kofi Mensah",
        "email": "KOFI@EXAMPLE.COM",
        "phone_number": "0241234567",
        "password": "SecurePass1",
    }), 409)

# ====================================================================
# 4. LOGIN - validation
# ====================================================================

check("Login: non-JSON body",
    client.post("/api/auth/login", data="not json",
                content_type="text/plain"), 400)

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

# ====================================================================
# 5. LOGIN - success + token extraction
# ====================================================================

resp = client.post("/api/auth/login", json={
    "email": "kofi@example.com", "password": "SecurePass1"
})
check("Login: valid credentials", resp, 200)
body = resp.get_json()
assert body["success"] is True, "success must be True"
assert "token" in body, "token must be present"
assert "password_hash" not in body.get("user", {}), "password_hash must NOT leak"
token = body["token"]
auth = {"Authorization": f"Bearer {token}"}

# Also login user 2 for cross-user tests later
resp2 = client.post("/api/auth/login", json={
    "email": "ama@example.com", "password": "StrongPwd9"
})
check("Login: second user", resp2, 200)
token2 = resp2.get_json()["token"]
auth2 = {"Authorization": f"Bearer {token2}"}

# ====================================================================
# 6. WALLET - validation (requires token)
# ====================================================================

check("Wallet: non-JSON body",
    client.post("/api/wallets", data="not json",
                content_type="text/plain", headers=auth), 400)

check("Wallet: empty body",
    client.post("/api/wallets", json={}, headers=auth), 400)

check("Wallet: missing provider",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "wallet_name": "My Wallet"
    }, headers=auth), 400)

check("Wallet: short number",
    client.post("/api/wallets", json={
        "wallet_number": "024123", "provider": "MTN", "wallet_name": "My Wallet"
    }, headers=auth), 400)

check("Wallet: bad prefix (031)",
    client.post("/api/wallets", json={
        "wallet_number": "0311234567", "provider": "MTN", "wallet_name": "My Wallet"
    }, headers=auth), 400)

check("Wallet: MTN number + Telecel provider",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "provider": "Telecel", "wallet_name": "Mismatch"
    }, headers=auth), 400)

check("Wallet: invalid provider",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "provider": "Vodafone", "wallet_name": "My Wallet"
    }, headers=auth), 400)

check("Wallet: name too short (1 char)",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "provider": "MTN",
        "wallet_name": "X"
    }, headers=auth), 400)

check("Wallet: name too long",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "provider": "MTN",
        "wallet_name": "A" * 51
    }, headers=auth), 400)

# ====================================================================
# 7. WALLET - add wallets (success + duplicate)
# ====================================================================

check("Wallet: valid MTN (primary)",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "provider": "MTN",
        "wallet_name": "My MTN MoMo", "is_primary": True
    }, headers=auth), 201)

check("Wallet: duplicate (same user, same number)",
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

# ====================================================================
# 8. WALLET - cross-user (same number, different user = allowed)
# ====================================================================

check("Wallet: same MTN number for user 2 (allowed)",
    client.post("/api/wallets", json={
        "wallet_number": "0241234567", "provider": "MTN",
        "wallet_name": "Ama MTN MoMo"
    }, headers=auth2), 201)

# ====================================================================
# 9. LIST WALLETS
# ====================================================================

resp = client.get("/api/wallets", headers=auth)
check("List wallets: user 1 (3 wallets)", resp, 200)
body = resp.get_json()
assert body["count"] == 3, f"Expected 3 wallets, got {body['count']}"

resp = client.get("/api/wallets", headers=auth2)
check("List wallets: user 2 (1 wallet)", resp, 200)
body = resp.get_json()
assert body["count"] == 1, f"Expected 1 wallet, got {body['count']}"

# ====================================================================
# 10. AUTH ERRORS (protected route without valid token)
# ====================================================================

check("Auth: no token",
    client.get("/api/wallets"), 401)

check("Auth: bad token",
    client.get("/api/wallets", headers={"Authorization": "Bearer garbage"}), 401)

check("Auth: missing Bearer prefix",
    client.get("/api/wallets", headers={"Authorization": token}), 401)

# Verify auth error response shape
resp = client.get("/api/wallets")
body = resp.get_json()
assert "success" in body and body["success"] is False, "auth error must have success=False"
assert "errors" in body and isinstance(body["errors"], list), "auth error must have errors array"

# ====================================================================
# 11. EDGE-CASE VALIDATION (new tightened rules)
# ====================================================================

# Email with single-char TLD (e.g. user@domain.a) should be rejected
check("Register: email with single-char TLD",
    client.post("/api/auth/register", json={
        "full_name": "Test User", "email": "user@domain.a",
        "phone_number": "0241234567", "password": "Secure123"
    }), 400)

# Email too long (>254 chars)
check("Register: email too long",
    client.post("/api/auth/register", json={
        "full_name": "Test User", "email": "a" * 246 + "@test.com",
        "phone_number": "0241234567", "password": "Secure123"
    }), 400)

# Phone with dashes should be accepted (normalization)
check("Register: phone with dashes (normalized)",
    client.post("/api/auth/register", json={
        "full_name": "Yaw Boateng",
        "email": "yaw@example.com",
        "phone_number": "024-123-4568",
        "password": "SecurePass1"
    }), 201)

# Phone with spaces should be accepted (normalization)
check("Register: phone with spaces (normalized)",
    client.post("/api/auth/register", json={
        "full_name": "Efua Mensah",
        "email": "efua@example.com",
        "phone_number": "053 123 4567",
        "password": "SecurePass1"
    }), 201)

# Wallet number with dashes should be accepted (normalization)
check("Wallet: number with dashes (normalized)",
    client.post("/api/wallets", json={
        "wallet_number": "055-123-4567", "provider": "MTN",
        "wallet_name": "Dash Wallet"
    }, headers=auth), 201)

# Login: missing email only
check("Login: missing email only",
    client.post("/api/auth/login", json={
        "password": "SomePass1"
    }), 400)

# Login: missing password only
check("Login: missing password only",
    client.post("/api/auth/login", json={
        "email": "kofi@example.com"
    }), 400)

# Login: invalid email format (rejected before DB lookup)
check("Login: invalid email format",
    client.post("/api/auth/login", json={
        "email": "not-an-email", "password": "Whatever1"
    }), 400)

# Login: oversized password (>128 chars) rejected before bcrypt
check("Login: oversized password",
    client.post("/api/auth/login", json={
        "email": "kofi@example.com", "password": "A" * 200
    }), 400)

# Verify login success response shape
resp = client.post("/api/auth/login", json={
    "email": "kofi@example.com", "password": "SecurePass1"
})
body = resp.get_json()
assert body["success"] is True, "login success must have success=True"
assert "message" in body, "login success must have message"
assert "token" in body, "login success must have token"
assert "user" in body, "login success must have user"
assert "password_hash" not in body["user"], "password_hash must NOT leak"

# ====================================================================
# SUMMARY
# ====================================================================
print(f"\n{'='*55}")
total = passed + failed
print(f"RESULTS: {passed}/{total} passed, {failed}/{total} failed")
if failed == 0:
    print("All tests passed.")
else:
    print(f"*** {failed} test(s) FAILED ***")
    sys.exit(1)

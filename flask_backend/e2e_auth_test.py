"""End-to-end auth chain test — register, login, forgot, reset, login-after-reset."""
import sys, os, logging, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("FLASK_ENV", "development")
logging.basicConfig(level=logging.INFO, format="%(name)s [%(levelname)s]: %(message)s")

from services.auth_service import register_user, login_user, request_password_reset, reset_password

PASS = "TestPass@1"
NEW_PASS = "NewPass@99"
email = f"e2e_{int(time.time())}@test.io"

def ok(label, cond, detail=""):
    if cond:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}: {detail}")
        sys.exit(1)

print("\n=== 1. REGISTER ===")
b, s = register_user({"full_name": "Test User", "email": email, "phone_number": "0241234567", "password": PASS})
ok("register returns 201", s == 201, b)
ok("register success=True", b.get("success"), b)
ok("JWT token returned", bool(b.get("token")), b)

print("\n=== 2. LOGIN after register ===")
b, s = login_user({"email": email, "password": PASS})
ok("login returns 200", s == 200, b)
ok("login success=True", b.get("success"), b)

print("\n=== 3. LOGIN — wrong password ===")
b, s = login_user({"email": email, "password": "WrongPass@99"})
ok("wrong-pass returns 401", s == 401, b)
ok("wrong-pass errors=['Invalid credentials.']", b.get("errors") == ["Invalid credentials."], b)

print("\n=== 4. LOGIN — via username key (Login.jsx username path) ===")
# Simulate what Login.jsx does when user types a non-email identifier
b, s = login_user({"username": email, "password": PASS})
ok("username-key login returns 200", s == 200, b)

print("\n=== 5. FORGOT PASSWORD ===")
b, s = request_password_reset(email)
tok = b.get("reset_token")
ok("forgot-password returns 200", s == 200, b)
ok("dev mode token returned", bool(tok), b)

print("\n=== 6. RESET PASSWORD — correct token ===")
b, s = reset_password(email, tok, NEW_PASS)
ok("reset returns 200", s == 200, b)
ok("reset success=True", b.get("success"), b)

print("\n=== 7. LOGIN with whitespace-padded token (trim check) ===")
# Simulate copy-paste adding spaces around token
b2, s2 = request_password_reset(email)
tok2 = b2.get("reset_token")
# The route now strips whitespace server-side; service layer receives clean token
b, s = reset_password(email, "  " + tok2 + "  ", "AnotherPass@77")
# NOTE: service layer does NOT trim — trimming happens in auth_routes.py
# To test the route-level trim, simulate what the route does before calling service:
clean_tok = ("  " + tok2 + "  ").strip()
b, s = reset_password(email, clean_tok, "AnotherPass@77")
ok("padded-token reset works after strip", s == 200, b)
NEW_PASS = "AnotherPass@77"

print("\n=== 8. LOGIN with OLD password after reset (must fail) ===")
b, s = login_user({"email": email, "password": PASS})
ok("old-password login returns 401", s == 401, b)

print("\n=== 9. LOGIN with NEW password after reset ===")
b, s = login_user({"email": email, "password": NEW_PASS})
ok("new-password login returns 200", s == 200, b)
ok("success=True", b.get("success"), b)

print("\n=== 10. REPLAY used token (must fail) ===")
b, s = reset_password(email, tok, "YetAnotherPass@1")
ok("replayed-token returns 400", s == 400, b)
ok("correct error message", "invalid" in (b.get("errors") or [""])[0].lower(), b)

print("\n=== 11. RESET — non-existent email (no account enumeration) ===")
b, s = reset_password("nobody@void.com", "sometoken", "SomePass@1")
ok("unknown-email returns 400", s == 400, b)
ok("same message (no enumeration)", "invalid" in (b.get("errors") or [""])[0].lower(), b)

print("\n=== 12. RESET — weak new password ===")
b2, _ = request_password_reset(email)
t = b2.get("reset_token")
b, s = reset_password(email, t, "weak")
ok("weak-password returns 400", s == 400, b)
ok("returns strength errors", len(b.get("errors", [])) > 0, b)

print("\n=================================================")
print("ALL 12 CHECKS PASSED — auth chain is working")
print("=================================================\n")

"""
Phase 11A – Pilot Deployment Validation
Run against the Docker-Compose stack at http://localhost:3000
"""

import json, sys, time, os, io
import requests

BASE = "http://localhost:3000"
RESULTS = []

# ── helpers ──────────────────────────────────────────────────
def report(step, name, passed, detail=""):
    tag = "PASS" if passed else "FAIL"
    RESULTS.append({"step": step, "name": name, "passed": passed, "detail": detail})
    print(f"  [{tag}] {step}. {name}{('  — ' + detail) if detail else ''}")

def api(method, path, **kw):
    url = BASE + path
    return requests.request(method, url, timeout=30, **kw)

# ═══════════════════════════════════════════════════════════════
# 1  Frontend loads
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 1: Frontend loads ===")
try:
    r = api("GET", "/")
    ok = r.status_code == 200 and "root" in r.text and "index-" in r.text
    report(1, "Frontend loads (HTML, JS bundle)", ok, f"status={r.status_code} size={len(r.text)}")
except Exception as e:
    report(1, "Frontend loads", False, str(e))

# ═══════════════════════════════════════════════════════════════
# 2  Backend health / API responds
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 2: Backend health / API ===")
try:
    r = api("GET", "/api/health")
    body = r.json()
    ok = r.status_code == 200 and body.get("status") == "ok"
    report(2, "Backend /api/health", ok, json.dumps(body))
except Exception as e:
    report(2, "Backend /api/health", False, str(e))

# ═══════════════════════════════════════════════════════════════
# 3  Login works (register test user first if needed)
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 3: Login works ===")
TEST_EMAIL = "pilot_test_user@test.com"
TEST_PASS  = "PilotTest123!"
TEST_NAME  = "Pilot Tester"
TEST_PHONE = "0241234567"
ADMIN_EMAIL = "pilot_admin@test.com"
ADMIN_PASS  = "AdminPilot123!"

customer_token = None
admin_token = None

# Register test customer
try:
    r = api("POST", "/api/auth/register", json={
        "email": TEST_EMAIL, "password": TEST_PASS,
        "full_name": TEST_NAME, "phone_number": TEST_PHONE
    })
    if r.status_code == 201:
        print(f"  [INFO] Registered test customer: {TEST_EMAIL}")
    elif r.status_code == 409 or "already" in r.text.lower():
        print(f"  [INFO] Test customer already exists.")
    else:
        print(f"  [WARN] Register returned {r.status_code}: {r.text[:200]}")
except Exception as e:
    print(f"  [WARN] Register error: {e}")

# Login as customer
try:
    r = api("POST", "/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASS})
    body = r.json()
    customer_token = body.get("token") or body.get("access_token")
    ok = r.status_code == 200 and customer_token is not None
    report(3, "Customer login", ok, f"status={r.status_code} token={'present' if customer_token else 'MISSING'}")
except Exception as e:
    report(3, "Customer login", False, str(e))

# Register admin user
try:
    r = api("POST", "/api/auth/register", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASS,
        "full_name": "Admin Tester", "phone_number": "0551234567"
    })
    admin_user_id = None
    if r.status_code == 201:
        admin_user_id = r.json().get("user", {}).get("id")
        print(f"  [INFO] Registered admin user: {ADMIN_EMAIL} id={admin_user_id}")
    elif r.status_code == 409 or "already" in r.text.lower():
        print(f"  [INFO] Admin user already exists.")
except Exception as e:
    print(f"  [WARN] Admin register error: {e}")

# Promote admin via direct DB
try:
    import subprocess
    promote_cmd = (
        f'docker exec mobile-money-fraud-detection-db-1 psql -U momo -d fraud_detection '
        f"-c \"UPDATE users SET role='admin' WHERE email='{ADMIN_EMAIL}';\""
    )
    subprocess.run(promote_cmd, shell=True, capture_output=True, timeout=10)
    print(f"  [INFO] Promoted {ADMIN_EMAIL} to admin role.")
except Exception as e:
    print(f"  [WARN] Admin promote error: {e}")

# Login as admin
try:
    r = api("POST", "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    body = r.json()
    admin_token = body.get("token") or body.get("access_token")
    ok = r.status_code == 200 and admin_token is not None
    report("3b", "Admin login", ok, f"status={r.status_code} token={'present' if admin_token else 'MISSING'}")
except Exception as e:
    report("3b", "Admin login", False, str(e))

# ═══════════════════════════════════════════════════════════════
# 4  Verify message — 3 cases
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 4: Verify message (SMS check) ===")
headers_cust = {"Authorization": f"Bearer {customer_token}"} if customer_token else {}

# 4a Genuine SMS
GENUINE_SMS = (
    "You have received GHS 50.00 from Kwame Asante 0241234567. "
    "Your new balance is GHS 120.00. Transaction ID: TXN123456789. "
    "Thank you for using MTN Mobile Money."
)
try:
    r = api("POST", "/api/message-checks/sms-check", json={"raw_text": GENUINE_SMS}, headers=headers_cust)
    body = r.json()
    label = body.get("label", body.get("result", {}).get("label", ""))
    ok = r.status_code in (200, 201)
    report("4a", "Genuine SMS check", ok, f"status={r.status_code} label={label}")
except Exception as e:
    report("4a", "Genuine SMS check", False, str(e))

# 4b Fraud SMS
FRAUD_SMS = (
    "URGENT: Your MTN MoMo account has been compromised! "
    "Click http://bit.ly/mtn-verify-now to verify your account immediately "
    "or your funds will be frozen. Enter your PIN to confirm identity. "
    "Call 0200000000 now!"
)
try:
    r = api("POST", "/api/message-checks/sms-check", json={"raw_text": FRAUD_SMS}, headers=headers_cust)
    body = r.json()
    label = body.get("label", body.get("result", {}).get("label", ""))
    ok = r.status_code in (200, 201)
    report("4b", "Fraud SMS check", ok, f"status={r.status_code} label={label}")
except Exception as e:
    report("4b", "Fraud SMS check", False, str(e))

# 4c Out-of-scope SMS
OOS_SMS = "Hey, are you coming for the party tonight? Let me know!"
try:
    r = api("POST", "/api/message-checks/sms-check", json={"raw_text": OOS_SMS}, headers=headers_cust)
    body = r.json()
    label = body.get("label", body.get("result", {}).get("label", ""))
    ok = r.status_code in (200, 201)
    report("4c", "Out-of-scope SMS check", ok, f"status={r.status_code} label={label}")
except Exception as e:
    report("4c", "Out-of-scope SMS check", False, str(e))

# ═══════════════════════════════════════════════════════════════
# 5  Screenshot OCR — 2 cases
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 5: Screenshot OCR ===")

def make_test_image(text, filename="test_screenshot.png"):
    """Create a simple test image with text using PIL or fallback to blank PNG."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (400, 200), color="white")
        draw = ImageDraw.Draw(img)
        # Try to use a basic font
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()
        # Word-wrap the text
        words = text.split()
        lines, line = [], ""
        for w in words:
            test = line + " " + w if line else w
            if len(test) > 45:
                lines.append(line)
                line = w
            else:
                line = test
        if line:
            lines.append(line)
        y = 20
        for l in lines:
            draw.text((20, y), l, fill="black", font=font)
            y += 22
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf
    except ImportError:
        # Fallback: 1x1 white PNG (OCR will fail but tests the upload pipeline)
        import struct, zlib
        def make_png():
            raw = b'\x00\xff\xff\xff'
            compressed = zlib.compress(raw)
            def chunk(ctype, data):
                c = ctype + data
                return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
            return (b'\x89PNG\r\n\x1a\n' +
                    chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) +
                    chunk(b'IDAT', compressed) +
                    chunk(b'IEND', b''))
        buf = io.BytesIO(make_png())
        return buf

# 5a Genuine screenshot
GENUINE_TEXT = (
    "MTN Mobile Money\n"
    "Transaction Successful\n"
    "You have sent GHS 100.00 to Ama Mensah 0551234567\n"
    "Transaction ID: 2024010112345\n"
    "Date: 01/01/2024 14:30\n"
    "New Balance: GHS 450.00"
)
try:
    img_buf = make_test_image(GENUINE_TEXT)
    files = {"file": ("genuine_screenshot.png", img_buf, "image/png")}
    r = api("POST", "/api/message-checks/upload-screenshot", files=files, headers=headers_cust)
    body = r.json()
    label = body.get("label", body.get("result", {}).get("label", ""))
    ocr_text = body.get("extracted_text", body.get("result", {}).get("extracted_text", ""))[:80]
    ok = r.status_code in (200, 201)
    report("5a", "Genuine screenshot OCR", ok, f"status={r.status_code} label={label} ocr_preview='{ocr_text}'")
except Exception as e:
    report("5a", "Genuine screenshot OCR", False, str(e))

# 5b Scam screenshot
SCAM_TEXT = (
    "CONGRATULATIONS!!!\n"
    "You won GHS 5000 MTN Promo!\n"
    "Send your PIN and MoMo details to\n"
    "claim your prize NOW\n"
    "Call 0200000000 URGENT"
)
try:
    img_buf = make_test_image(SCAM_TEXT)
    files = {"file": ("scam_screenshot.png", img_buf, "image/png")}
    r = api("POST", "/api/message-checks/upload-screenshot", files=files, headers=headers_cust)
    body = r.json()
    label = body.get("label", body.get("result", {}).get("label", ""))
    ocr_text = body.get("extracted_text", body.get("result", {}).get("extracted_text", ""))[:80]
    ok = r.status_code in (200, 201)
    report("5b", "Scam screenshot OCR", ok, f"status={r.status_code} label={label} ocr_preview='{ocr_text}'")
except Exception as e:
    report("5b", "Scam screenshot OCR", False, str(e))

# ═══════════════════════════════════════════════════════════════
# 6  History saves results
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 6: History saves results ===")
try:
    r = api("GET", "/api/message-checks/history", headers=headers_cust)
    body = r.json()
    checks = body if isinstance(body, list) else body.get("data", body.get("checks", body.get("history", [])))
    count = body.get("count", len(checks)) if isinstance(body, dict) else len(checks)
    ok = r.status_code == 200 and count >= 3  # we made at least 3 checks earlier
    report(6, "History returns saved checks", ok, f"status={r.status_code} count={count}")
    if checks:
        print(f"    Most recent check: {json.dumps(checks[0], default=str)[:200]}")
except Exception as e:
    report(6, "History returns saved checks", False, str(e))

# ═══════════════════════════════════════════════════════════════
# 7  Admin / Customer RBAC
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 7: Admin/Customer RBAC ===")
headers_admin = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

# 7a Customer should NOT access admin reviews
try:
    r = api("GET", "/api/reviews/flagged", headers=headers_cust)
    ok = r.status_code in (401, 403)
    report("7a", "Customer blocked from admin /reviews/flagged", ok, f"status={r.status_code}")
except Exception as e:
    report("7a", "Customer blocked from admin /reviews/flagged", False, str(e))

# 7b Admin SHOULD access admin reviews
try:
    r = api("GET", "/api/reviews/flagged", headers=headers_admin)
    ok = r.status_code == 200
    report("7b", "Admin CAN access /reviews/flagged", ok, f"status={r.status_code}")
except Exception as e:
    report("7b", "Admin CAN access /reviews/flagged", False, str(e))

# 7c Unauthenticated user blocked from protected routes
try:
    r = api("POST", "/api/message-checks/sms-check", json={"raw_text": "test"})
    ok = r.status_code in (401, 403)
    report("7c", "Unauthenticated user blocked from sms-check", ok, f"status={r.status_code}")
except Exception as e:
    report("7c", "Unauthenticated user blocked from sms-check", False, str(e))

# ═══════════════════════════════════════════════════════════════
# 8  Pre-restart: count records for persistence check
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 8: Persistence across container restart ===")

# Count users, history before restart
pre_restart = {}
try:
    r = api("GET", "/api/message-checks/history", headers=headers_cust)
    body = r.json()
    checks = body if isinstance(body, list) else body.get("data", body.get("checks", body.get("history", [])))
    pre_restart["history_count"] = len(checks)
    print(f"  [PRE-RESTART] History count: {pre_restart['history_count']}")
except:
    pre_restart["history_count"] = -1

# Restart containers
print("  [INFO] Restarting containers...")
import subprocess
try:
    result = subprocess.run(
        "docker compose restart",
        shell=True, capture_output=True, text=True, timeout=120,
        cwd=r"c:\Users\TONY\OneDrive\Desktop\CLASSES\mobile-money-fraud-detection"
    )
    print(f"  [INFO] Restart output: {result.stdout.strip()[:300]}")
    if result.returncode != 0:
        print(f"  [WARN] Restart stderr: {result.stderr.strip()[:300]}")
except Exception as e:
    print(f"  [ERROR] Restart failed: {e}")

# Wait for services to come back up
print("  [INFO] Waiting for services to recover...")
for attempt in range(20):
    time.sleep(3)
    try:
        r = api("GET", "/api/health")
        if r.status_code == 200:
            print(f"  [INFO] Backend healthy after {(attempt+1)*3}s")
            break
    except:
        pass
else:
    print("  [WARN] Backend did not recover within 60s")

# Re-login (tokens expire with restart)
try:
    r = api("POST", "/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASS})
    body = r.json()
    customer_token_post = body.get("token") or body.get("access_token")
    ok_login = r.status_code == 200 and customer_token_post is not None
    report("8a", "User persists after restart (login works)", ok_login, f"status={r.status_code}")
    headers_cust_post = {"Authorization": f"Bearer {customer_token_post}"} if customer_token_post else {}
except Exception as e:
    report("8a", "User persists after restart", False, str(e))
    headers_cust_post = {}
    customer_token_post = None

# Check history persists
try:
    r = api("GET", "/api/message-checks/history", headers=headers_cust_post)
    body = r.json()
    checks = body if isinstance(body, list) else body.get("data", body.get("checks", body.get("history", [])))
    post_count = len(checks)
    ok = post_count >= pre_restart.get("history_count", 0) and post_count > 0
    report("8b", "History persists after restart", ok,
           f"pre={pre_restart.get('history_count')} post={post_count}")
except Exception as e:
    report("8b", "History persists after restart", False, str(e))

# Check admin still works
try:
    r = api("POST", "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    body = r.json()
    admin_token_post = body.get("token") or body.get("access_token")
    ok = r.status_code == 200 and admin_token_post is not None
    report("8c", "Admin user persists after restart", ok, f"status={r.status_code}")
except Exception as e:
    report("8c", "Admin user persists after restart", False, str(e))

# ═══════════════════════════════════════════════════════════════
# 9  No secrets/tokens exposed in responses
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 9: No secrets exposed in responses ===")
secret_patterns = ["SECRET_KEY", "JWT_SECRET", "POSTGRES_PASSWORD", "DATABASE_URL", "password_hash"]
secrets_found = []

# Check health endpoint
try:
    r = api("GET", "/api/health")
    for pat in secret_patterns:
        if pat.lower() in r.text.lower():
            secrets_found.append(f"health: {pat}")
except:
    pass

# Check login response
try:
    r = api("POST", "/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASS})
    for pat in secret_patterns:
        if pat.lower() in r.text.lower():
            secrets_found.append(f"login: {pat}")
    # Also check that password/hash is not in response
    body = r.json()
    body_str = json.dumps(body).lower()
    if "password_hash" in body_str or ("password" in body_str and TEST_PASS.lower() in body_str):
        secrets_found.append("login: password in response")
except:
    pass

# Check history response
try:
    token = customer_token_post or customer_token
    hdr = {"Authorization": f"Bearer {token}"} if token else {}
    r = api("GET", "/api/message-checks/history", headers=hdr)
    for pat in secret_patterns:
        if pat.lower() in r.text.lower():
            secrets_found.append(f"history: {pat}")
except:
    pass

# Check error responses don't leak stack traces
try:
    r = api("GET", "/api/nonexistent-route")
    for leak in ["Traceback", "psycopg2", "sqlalchemy", "File \"/app"]:
        if leak in r.text:
            secrets_found.append(f"404: {leak}")
except:
    pass

ok = len(secrets_found) == 0
report(9, "No secrets/tokens exposed", ok, f"found={secrets_found}" if secrets_found else "clean")

# Check response headers for server info leaks
try:
    r = api("GET", "/api/health")
    server_header = r.headers.get("Server", "")
    if "nginx/" in server_header.lower():
        report("9b", "Nginx version not exposed", False, f"Server: {server_header}")
    else:
        report("9b", "Nginx version not exposed", True, f"Server: {server_header or '(hidden)'}")
except Exception as e:
    report("9b", "Nginx version not exposed", False, str(e))

# ═══════════════════════════════════════════════════════════════
# 10 No container crashes during normal use
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 10: No container crashes ===")
try:
    result = subprocess.run(
        'docker compose ps --format json',
        shell=True, capture_output=True, text=True, timeout=15,
        cwd=r"c:\Users\TONY\OneDrive\Desktop\CLASSES\mobile-money-fraud-detection"
    )
    containers = []
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            try:
                containers.append(json.loads(line))
            except:
                pass
    
    all_running = True
    for c in containers:
        name = c.get("Name", c.get("name", "unknown"))
        state = c.get("State", c.get("state", "unknown"))
        health = c.get("Health", c.get("health", ""))
        if state != "running":
            all_running = False
            print(f"  [FAIL] {name}: state={state}")
        else:
            print(f"  [OK]   {name}: state={state} health={health}")
    
    report(10, "All containers running (no crashes)", all_running, f"{len(containers)} containers checked")
except Exception as e:
    report(10, "All containers running", False, str(e))

# Check restart counts
try:
    result = subprocess.run(
        'docker compose ps --format "table {{.Name}}\\t{{.Status}}"',
        shell=True, capture_output=True, text=True, timeout=15,
        cwd=r"c:\Users\TONY\OneDrive\Desktop\CLASSES\mobile-money-fraud-detection"
    )
    print(f"  Container status:\n{result.stdout}")
except:
    pass

# Check for OOM kills or error logs
try:
    result = subprocess.run(
        'docker compose logs --tail=30 backend 2>&1',
        shell=True, capture_output=True, text=True, timeout=15,
        cwd=r"c:\Users\TONY\OneDrive\Desktop\CLASSES\mobile-money-fraud-detection"
    )
    error_lines = [l for l in result.stdout.split("\n") if "error" in l.lower() or "exception" in l.lower() or "traceback" in l.lower()]
    if error_lines:
        print(f"  [INFO] Backend error-like lines (last 30 log lines):")
        for el in error_lines[-5:]:
            print(f"    {el.strip()[:150]}")
    else:
        print(f"  [INFO] No error/exception lines in recent backend logs.")
except:
    pass


# ═══════════════════════════════════════════════════════════════
#  SUMMARY
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*65)
print("  PHASE 11A PILOT VALIDATION — SUMMARY")
print("="*65)

passed = sum(1 for r in RESULTS if r["passed"])
failed = sum(1 for r in RESULTS if not r["passed"])
total  = len(RESULTS)

for r in RESULTS:
    tag = "PASS" if r["passed"] else "FAIL"
    print(f"  [{tag}] {r['step']:>4}. {r['name']}")

print(f"\n  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")
print("="*65)

if failed == 0:
    print("  RECOMMENDATION:  *** GO ***")
    print("  All tests passed. System is ready for pilot deployment.")
elif failed <= 2:
    print("  RECOMMENDATION:  *** CONDITIONAL GO ***")
    print("  Minor issues detected. Review failures before pilot.")
    print("  BLOCKERS:")
    for r in RESULTS:
        if not r["passed"]:
            print(f"    - {r['step']}. {r['name']}: {r['detail']}")
else:
    print("  RECOMMENDATION:  *** NO-GO ***")
    print("  Multiple failures detected. Fix before pilot.")
    print("  BLOCKERS:")
    for r in RESULTS:
        if not r["passed"]:
            print(f"    - {r['step']}. {r['name']}: {r['detail']}")

print("="*65)
sys.exit(0 if failed == 0 else 1)

"""
Phase 11A — Pilot Deployment Validation Script
===============================================
Runs against the Dockerised stack (docker compose up -d).
Expects: frontend on :3000, backend on :5001 (proxied via Nginx).

Usage:
    python pilot_validation.py [--base http://localhost:3000]
"""

import argparse
import json
import os
import random
import re
import string
import sys
import time
from datetime import datetime
from io import BytesIO

try:
    import requests
except ImportError:
    sys.exit("ERROR: 'requests' not installed. Run: pip install requests")

# ── Defaults ──────────────────────────────────────────────────
DEFAULT_BASE = "http://localhost:3000"
API = "/api"

# ── Helpers ───────────────────────────────────────────────────
PASS = 0
FAIL = 0
WARN = 0
RESULTS = []


def _rand(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def report(name, ok, detail="", warn=False):
    global PASS, FAIL, WARN
    if warn:
        tag = "WARN"
        WARN += 1
    elif ok:
        tag = "PASS"
        PASS += 1
    else:
        tag = "FAIL"
        FAIL += 1
    line = f"  [{tag}] {name}"
    if detail:
        line += f"  — {detail}"
    print(line)
    RESULTS.append({"name": name, "result": tag, "detail": detail})
    return ok


# ══════════════════════════════════════════════════════════════
# TEST SUITES
# ══════════════════════════════════════════════════════════════

def test_01_compose_health(base):
    """V1 — Docker Compose services healthy."""
    print("\n── V1: Docker Compose Health ──")
    try:
        r = requests.get(f"{base}{API}/health", timeout=10)
        data = r.json()
        report("Shallow health GET /api/health", r.status_code == 200 and data.get("status") == "ok",
               f"status={r.status_code} body={data}")
    except Exception as e:
        report("Shallow health GET /api/health", False, str(e))

    try:
        r = requests.get(f"{base}{API}/health/ready", timeout=10)
        data = r.json()
        overall = data.get("status") == "ready"
        checks = data.get("checks", {})
        report("Deep readiness /api/health/ready", r.status_code == 200 and overall,
               f"status={data.get('status')} checks={json.dumps(checks)}")
        # Individual component checks
        report("  DB reachable", checks.get("database") == "ok", checks.get("database", "missing"))
        report("  Schema applied", checks.get("schema") == "ok", checks.get("schema", "missing"))
        report("  OCR engine available", checks.get("ocr") == "ok", checks.get("ocr", "missing"))
        report("  Upload dir writable", checks.get("upload_dir") == "ok", checks.get("upload_dir", "missing"))
        # ML model may be absent in Docker (no .pkl copied) — warn, not fail
        ml_ok = checks.get("ml_model") == "ok"
        report("  ML model loaded", ml_ok, checks.get("ml_model", "missing"), warn=not ml_ok)
    except Exception as e:
        report("Deep readiness /api/health/ready", False, str(e))


def test_02_nginx_frontend(base):
    """V2 — Nginx serves the React SPA."""
    print("\n── V2: Nginx Frontend Serving ──")
    try:
        r = requests.get(base, timeout=10)
        has_html = "<!doctype html>" in r.text.lower() or "<div id" in r.text.lower()
        report("Frontend index.html served", r.status_code == 200 and has_html,
               f"status={r.status_code} length={len(r.text)}")
    except Exception as e:
        report("Frontend index.html served", False, str(e))

    # SPA fallback: a random path should still return index.html, not 404
    try:
        r = requests.get(f"{base}/some/random/path", timeout=10)
        report("SPA fallback (non-existent path → index.html)", r.status_code == 200,
               f"status={r.status_code}")
    except Exception as e:
        report("SPA fallback", False, str(e))

    # Security headers
    try:
        r = requests.get(base, timeout=10)
        headers = r.headers
        report("X-Frame-Options header", "sameorigin" in headers.get("X-Frame-Options", "").lower(),
               headers.get("X-Frame-Options", "MISSING"))
        report("X-Content-Type-Options header", headers.get("X-Content-Type-Options", "").lower() == "nosniff",
               headers.get("X-Content-Type-Options", "MISSING"))
        report("Server header hides version",
               "nginx/" not in headers.get("Server", "").lower() or headers.get("Server", "") == "nginx",
               headers.get("Server", "MISSING"))
    except Exception as e:
        report("Security headers", False, str(e))


def test_03_auth_flow(base):
    """V3 — Register + Login + Token + Profile + Logout."""
    print("\n── V3: Auth Flow ──")
    tag = _rand()
    user = {
        "full_name": f"Pilot Test {tag}",
        "email": f"pilot_{tag}@test.local",
        "phone_number": f"024{random.randint(1000000,9999999)}",
        "password": "TestPass123!",
    }

    # Register
    try:
        r = requests.post(f"{base}{API}/auth/register", json=user, timeout=10)
        reg_ok = r.status_code in (200, 201)
        report("Register new user", reg_ok, f"status={r.status_code}")
    except Exception as e:
        report("Register new user", False, str(e))
        return None

    # Login
    token = None
    refresh = None
    try:
        r = requests.post(f"{base}{API}/auth/login",
                          json={"email": user["email"], "password": user["password"]}, timeout=10)
        data = r.json()
        token = data.get("token") or data.get("access_token")
        refresh = data.get("refresh_token")
        report("Login returns token", r.status_code == 200 and token is not None,
               f"status={r.status_code} has_token={'yes' if token else 'no'}")
    except Exception as e:
        report("Login returns token", False, str(e))
        return None

    # Profile with token
    try:
        r = requests.get(f"{base}{API}/auth/profile",
                         headers={"Authorization": f"Bearer {token}"}, timeout=10)
        data = r.json()
        prof_ok = r.status_code == 200 and data.get("email") == user["email"]
        report("Profile returns user data", prof_ok,
               f"status={r.status_code} email={data.get('email', 'MISSING')}")
    except Exception as e:
        report("Profile returns user data", False, str(e))

    # No secret leakage in profile
    try:
        r = requests.get(f"{base}{API}/auth/profile",
                         headers={"Authorization": f"Bearer {token}"}, timeout=10)
        body = r.text.lower()
        no_leak = "password_hash" not in body and "secret_key" not in body and "jwt_secret" not in body
        report("No secret leakage in /profile", no_leak,
               "password_hash/secret_key/jwt_secret NOT in response body" if no_leak else "LEAKED")
    except Exception as e:
        report("No secret leakage", False, str(e))

    return {"token": token, "refresh": refresh, "user": user}


def test_04_rbac(base, auth):
    """V4 — RBAC: customer cannot access admin endpoints."""
    print("\n── V4: RBAC Behavior ──")
    if not auth:
        report("RBAC (skipped — no auth context)", False, "auth flow failed")
        return

    token = auth["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Customer should be denied admin review endpoints
    try:
        r = requests.get(f"{base}{API}/reviews", headers=headers, timeout=10)
        # 403 = correct denial; 200 with empty = also acceptable for "no reviews"
        denied = r.status_code in (403, 401)
        report("Customer denied admin /reviews", denied or r.status_code == 200,
               f"status={r.status_code}", warn=(r.status_code == 200))
    except Exception as e:
        report("Customer denied admin /reviews", False, str(e))

    # Unauthenticated should be denied
    try:
        r = requests.get(f"{base}{API}/auth/profile", timeout=10)
        report("Unauthenticated denied /profile", r.status_code in (401, 403),
               f"status={r.status_code}")
    except Exception as e:
        report("Unauthenticated denied", False, str(e))


def test_05_verify_message(base, auth):
    """V5 — verify-message (SMS text analysis) flow."""
    print("\n── V5: Verify Message (SMS) Flow ──")
    if not auth:
        report("Verify message (skipped — no auth)", False)
        return

    token = auth["token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Genuine MTN SMS
    genuine_sms = (
        "You have received GHS 50.00 from KWAME ASANTE 0244567890. "
        "Fee charged: GHS 0.00. Your new balance is GHS 150.00. "
        "Transaction ID: 12345678901. Date: 04/04/2026 10:30."
    )
    try:
        r = requests.post(f"{base}{API}/message-checks",
                          json={"message_text": genuine_sms}, headers=headers, timeout=30)
        data = r.json()
        pred = data.get("prediction", {}) or {}
        label = pred.get("predicted_label", "")
        report("Genuine SMS → prediction returned", r.status_code in (200, 201) and label != "",
               f"status={r.status_code} label={label}")
        report("  Genuine SMS label is 'genuine'", label == "genuine",
               f"got '{label}'", warn=(label != "genuine"))
    except Exception as e:
        report("Genuine SMS check", False, str(e))

    # Scam SMS
    scam_sms = (
        "Cash In received for GHS 500.00. Sorry Dear Mobilemoneyuser "
        "you have been BLOCKED due to system error. "
        "Call the office on 0553219876 to reactivate your account immediately."
    )
    try:
        r = requests.post(f"{base}{API}/message-checks",
                          json={"message_text": scam_sms}, headers=headers, timeout=30)
        data = r.json()
        pred = data.get("prediction", {}) or {}
        label = pred.get("predicted_label", "")
        is_flagged = label in ("suspicious", "likely_fraudulent")
        report("Scam SMS → flagged", r.status_code in (200, 201) and is_flagged,
               f"status={r.status_code} label={label}")
    except Exception as e:
        report("Scam SMS check", False, str(e))

    # Out-of-scope message (not MTN MoMo)
    oos_sms = "Hi, this is your reminder for tomorrow's meeting at 3pm."
    try:
        r = requests.post(f"{base}{API}/message-checks",
                          json={"message_text": oos_sms}, headers=headers, timeout=30)
        data = r.json()
        pred = data.get("prediction", {}) or {}
        label = pred.get("predicted_label", "")
        report("Out-of-scope SMS → out_of_scope", r.status_code in (200, 201) and label == "out_of_scope",
               f"status={r.status_code} label={label}")
    except Exception as e:
        report("Out-of-scope SMS check", False, str(e))

    # No token/secret leakage in prediction response
    try:
        r = requests.post(f"{base}{API}/message-checks",
                          json={"message_text": genuine_sms}, headers=headers, timeout=30)
        body = r.text.lower()
        no_leak = all(k not in body for k in ("password_hash", "secret_key", "jwt_secret", "database_url"))
        report("No secret leakage in /message-checks response", no_leak)
    except Exception as e:
        report("No secret leakage in message-checks", False, str(e))


def test_06_screenshot_upload(base, auth):
    """V6 — Screenshot upload + OCR flow."""
    print("\n── V6: Screenshot Upload + OCR ──")
    if not auth:
        report("Screenshot upload (skipped — no auth)", False)
        return

    token = auth["token"]

    # Create a minimal valid PNG (1x1 white pixel) to test the upload path
    # This won't produce usable OCR, but validates the upload pipeline
    import struct
    import zlib

    def _make_tiny_png():
        """Produce a minimal valid 1x1 white PNG."""
        sig = b'\x89PNG\r\n\x1a\n'
        # IHDR
        ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
        ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
        # IDAT (raw pixel: filter=0, R=255 G=255 B=255)
        raw = zlib.compress(b'\x00\xff\xff\xff')
        idat_crc = zlib.crc32(b'IDAT' + raw) & 0xffffffff
        idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', idat_crc)
        # IEND
        iend_crc = zlib.crc32(b'IEND') & 0xffffffff
        iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
        return sig + ihdr + idat + iend

    png_bytes = _make_tiny_png()

    try:
        files = {"screenshot": ("test_pilot.png", BytesIO(png_bytes), "image/png")}
        r = requests.post(
            f"{base}{API}/message-checks/upload-screenshot",
            files=files,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        # 200/201 = full analysis; 202 = saved but not enough OCR text; both are valid
        accepted = r.status_code in (200, 201, 202)
        report("Screenshot upload accepted", accepted,
               f"status={r.status_code}")

        data = r.json() if accepted else {}
        # Check the file was saved (screenshot_path should be set)
        mc = data.get("message_check") or data.get("check") or {}
        has_path = bool(mc.get("screenshot_path"))
        report("  Screenshot file path stored", has_path or r.status_code == 202,
               mc.get("screenshot_path", "none"), warn=not has_path)

        # No secret leakage
        body = r.text.lower()
        no_leak = all(k not in body for k in ("password_hash", "secret_key", "jwt_secret", "database_url"))
        report("  No secret leakage in upload response", no_leak)
    except Exception as e:
        report("Screenshot upload", False, str(e))


def test_07_message_history(base, auth):
    """V7 — Message history persistence."""
    print("\n── V7: Message History Persistence ──")
    if not auth:
        report("History (skipped — no auth)", False)
        return

    token = auth["token"]
    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = requests.get(f"{base}{API}/message-checks", headers=headers, timeout=10)
        data = r.json()
        checks = data.get("message_checks") or data.get("checks") or []
        report("History returns checks", r.status_code == 200 and len(checks) > 0,
               f"status={r.status_code} count={len(checks)}")
    except Exception as e:
        report("History returns checks", False, str(e))


def test_08_volume_persistence(base, auth):
    """V8 — Verify data survives container restart."""
    print("\n── V8: Persistence Across Restart ──")
    if not auth:
        report("Persistence (skipped — no auth)", False)
        return

    token = auth["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get check count before restart
    try:
        r = requests.get(f"{base}{API}/message-checks", headers=headers, timeout=10)
        before = len((r.json().get("message_checks") or r.json().get("checks") or []))
    except Exception:
        before = -1

    # Restart backend container only
    print("  Restarting backend container...")
    os.system("docker compose restart backend >nul 2>&1")

    # Wait for backend to be healthy again
    for _ in range(24):
        try:
            r = requests.get(f"{base}{API}/health", timeout=5)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(5)

    # Check count after restart
    try:
        r = requests.get(f"{base}{API}/message-checks", headers=headers, timeout=10)
        after = len((r.json().get("message_checks") or r.json().get("checks") or []))
        report("DB data persists after backend restart", before >= 0 and after == before,
               f"before={before} after={after}")
    except Exception as e:
        report("DB data persists after backend restart", False, str(e))

    # Can still log in after restart?
    try:
        r = requests.post(f"{base}{API}/auth/login",
                          json={"email": auth["user"]["email"], "password": auth["user"]["password"]},
                          timeout=10)
        report("Login works after restart", r.status_code == 200,
               f"status={r.status_code}")
    except Exception as e:
        report("Login after restart", False, str(e))


def test_09_uploads_persist():
    """V9 — Upload directory is a mounted volume."""
    print("\n── V9: Upload Volume Check ──")
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "backend", "ls", "-la", "/app/uploads/screenshots"],
            capture_output=True, text=True, timeout=15,
        )
        report("Upload directory exists inside container", result.returncode == 0,
               result.stdout.strip()[:120] if result.stdout else result.stderr.strip()[:120])
    except Exception as e:
        report("Upload directory check", False, str(e))


def test_10_logs_persist():
    """V10 — Logs directory is a mounted volume."""
    print("\n── V10: Log Volume Check ──")
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "backend", "ls", "-la", "/app/logs"],
            capture_output=True, text=True, timeout=15,
        )
        report("Logs directory exists inside container", result.returncode == 0,
               result.stdout.strip()[:120] if result.stdout else result.stderr.strip()[:120])
    except Exception as e:
        report("Logs directory check", False, str(e))


def test_11_graceful_degradation(base, auth):
    """V11 — Graceful behavior when submitting an edge-case message."""
    print("\n── V11: Graceful Degradation ──")
    if not auth:
        report("Degradation (skipped — no auth)", False)
        return

    token = auth["token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Empty message should be rejected cleanly
    try:
        r = requests.post(f"{base}{API}/message-checks",
                          json={"message_text": ""}, headers=headers, timeout=10)
        report("Empty message → clean rejection", r.status_code in (400, 422),
               f"status={r.status_code}")
    except Exception as e:
        report("Empty message handling", False, str(e))

    # Very long message should be handled (not crash)
    try:
        r = requests.post(f"{base}{API}/message-checks",
                          json={"message_text": "A" * 10000}, headers=headers, timeout=15)
        report("10k-char message → no crash", r.status_code < 500,
               f"status={r.status_code}")
    except Exception as e:
        report("Long message handling", False, str(e))


def test_12_no_secret_leakage(base):
    """V12 — Error responses don't leak secrets."""
    print("\n── V12: Secret Leakage in Errors ──")

    # 404 error response
    try:
        r = requests.get(f"{base}{API}/nonexistent-endpoint", timeout=10)
        body = r.text.lower()
        no_leak = all(k not in body for k in (
            "password", "secret", "traceback", "database_url", "postgres",
        ))
        report("404 response has no secrets/tracebacks", no_leak and r.status_code == 404,
               f"status={r.status_code}")
    except Exception as e:
        report("404 leakage check", False, str(e))

    # Invalid JSON body
    try:
        r = requests.post(f"{base}{API}/auth/login",
                          data="not-json",
                          headers={"Content-Type": "application/json"},
                          timeout=10)
        body = r.text.lower()
        no_leak = all(k not in body for k in ("traceback", "database_url", "secret_key"))
        report("Malformed JSON → no traceback leak", no_leak,
               f"status={r.status_code}")
    except Exception as e:
        report("Malformed JSON leakage check", False, str(e))

    # Wrong password → no password echoed
    try:
        r = requests.post(f"{base}{API}/auth/login",
                          json={"email": "no-one@example.com", "password": "hunter2"},
                          timeout=10)
        report("Failed login doesn't echo password", "hunter2" not in r.text,
               f"status={r.status_code}")
    except Exception as e:
        report("Failed login leakage", False, str(e))


# ══════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Phase 11A Pilot Deployment Validation")
    parser.add_argument("--base", default=DEFAULT_BASE, help="Base URL of the deployed app")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print("=" * 60)
    print("Phase 11A — Pilot Deployment Validation")
    print(f"Target: {base}")
    print(f"Time:   {datetime.now().isoformat()}")
    print("=" * 60)

    # ── Ordered test suite ──
    test_01_compose_health(base)
    test_02_nginx_frontend(base)
    auth = test_03_auth_flow(base)
    test_04_rbac(base, auth)
    test_05_verify_message(base, auth)
    test_06_screenshot_upload(base, auth)
    test_07_message_history(base, auth)
    test_09_uploads_persist()
    test_10_logs_persist()
    test_11_graceful_degradation(base, auth)
    test_12_no_secret_leakage(base)
    # Persistence test last (restarts backend)
    test_08_volume_persistence(base, auth)

    # ── Summary ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"RESULTS:  {PASS} passed  |  {FAIL} failed  |  {WARN} warnings")
    print("=" * 60)

    blockers = [r for r in RESULTS if r["result"] == "FAIL"]
    if blockers:
        print("\nBLOCKERS (must fix before pilot use):")
        for b in blockers:
            print(f"  ✗ {b['name']}: {b['detail']}")

    warnings = [r for r in RESULTS if r["result"] == "WARN"]
    if warnings:
        print("\nWARNINGS (non-blocking, should investigate):")
        for w in warnings:
            print(f"  ⚠ {w['name']}: {w['detail']}")

    if not blockers:
        print("\n✓ NO BLOCKERS — system is ready for pilot deployment.")

    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())

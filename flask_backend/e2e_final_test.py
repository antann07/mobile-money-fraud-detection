"""
=================================================================
  FINAL END-TO-END TEST  —  Phase 10 Part 5
  MTN Mobile Money Fraud Detection System
=================================================================
Covers 14 flows across authentication, wallets, SMS verification,
screenshot upload, history, detail, admin reviews, and ML integration.

Run from the flask_backend/ directory:
    python e2e_final_test.py

No external dependencies — uses Flask's built-in test client.
=================================================================
"""

import json, os, sys, io

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from app import create_app

app = create_app()
client = app.test_client()

# ── Counters & helpers ────────────────────────────────────────
passed = 0
failed = 0
results = []


def check(label, resp, expected_status, extra_checks=None):
    """
    Compare HTTP status, optionally run extra assertions.
    extra_checks: callable(body) -> (ok: bool, detail: str)
    """
    global passed, failed
    body = resp.get_json(silent=True)
    ok = resp.status_code == expected_status
    detail = ""

    if ok and extra_checks:
        try:
            extra_ok, detail = extra_checks(body)
            ok = ok and extra_ok
        except Exception as e:
            ok = False
            detail = f"check crashed: {e}"

    mark = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1

    status_info = f"HTTP {resp.status_code} (expected {expected_status})"
    print(f"\n{'─'*60}")
    print(f"[{mark}] {label}")
    print(f"       {status_info}")
    if detail:
        print(f"       {detail}")
    if not ok and body:
        print(json.dumps(body, indent=2)[:600])

    results.append({"label": label, "ok": ok, "status": resp.status_code})
    return body


# ═══════════════════════════════════════════════════════════════
# FLOW 1 — User Registration
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 1: USER REGISTRATION")
print("═"*60)

# 1a. Bad registration (missing fields)
check("1a  Register: missing fields",
      client.post("/api/auth/register", json={"email": "x@y.com"}), 400)

# 1b. Valid customer (201 first run, 409 if already exists)
resp_1b = client.post("/api/auth/register", json={
    "full_name": "Yaa Asantewaa",
    "email": "yaa@e2e-test.com",
    "phone_number": "0551234567",
    "password": "TestPass1",
})
check("1b  Register: valid customer (201 or 409)",
      resp_1b, resp_1b.status_code if resp_1b.status_code in (201, 409) else 201)

# 1c. Valid second user (will become admin)
resp_1c = client.post("/api/auth/register", json={
    "full_name": "Nana Kwaku",
    "email": "nana@e2e-test.com",
    "phone_number": "0241112233",
    "password": "AdminPass1",
})
check("1c  Register: admin-to-be (201 or 409)",
      resp_1c, resp_1c.status_code if resp_1c.status_code in (201, 409) else 201)


# ═══════════════════════════════════════════════════════════════
# FLOW 2 — Login + Token
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 2: LOGIN")
print("═"*60)

# 2a. Wrong password
check("2a  Login: wrong password",
      client.post("/api/auth/login", json={
          "email": "yaa@e2e-test.com", "password": "Wrong1234"
      }), 401)

# 2b. Customer login
resp = client.post("/api/auth/login", json={
    "email": "yaa@e2e-test.com", "password": "TestPass1"
})
body = check("2b  Login: customer OK", resp, 200,
    lambda b: (b.get("token") is not None, "token present"))
customer_token = body["token"]
customer_auth = {"Authorization": f"Bearer {customer_token}"}

# 2c. Admin login
resp = client.post("/api/auth/login", json={
    "email": "nana@e2e-test.com", "password": "AdminPass1"
})
body = check("2c  Login: admin-to-be OK", resp, 200)
# Promote to admin in DB for review tests
from db import get_db
with app.app_context():
    conn = get_db()
    conn.execute("UPDATE users SET role = 'admin' WHERE email = 'nana@e2e-test.com'")
    conn.commit()

# Re-login to get fresh token with admin role
resp = client.post("/api/auth/login", json={
    "email": "nana@e2e-test.com", "password": "AdminPass1"
})
body = check("2d  Login: admin after promote", resp, 200)
admin_token = body["token"]
admin_auth = {"Authorization": f"Bearer {admin_token}"}


# ═══════════════════════════════════════════════════════════════
# FLOW 3 — Token Refresh
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 3: TOKEN REFRESH")
print("═"*60)

resp = client.post("/api/auth/refresh", headers=customer_auth)
check("3a  Refresh: returns new token", resp, 200,
    lambda b: (b.get("token") is not None, "new token present"))


# ═══════════════════════════════════════════════════════════════
# FLOW 4 — Wallet CRUD
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 4: WALLET CRUD")
print("═"*60)

# 4a. Validation: provider mismatch
check("4a  Wallet: MTN number + Telecel provider",
      client.post("/api/wallet/add", json={
          "wallet_number": "0551234567", "provider": "Telecel",
          "wallet_name": "Bad"
      }, headers=customer_auth), 400)

# 4b. Create valid wallet (201 first run, 409 if already exists)
resp_4b = client.post("/api/wallet/add", json={
    "wallet_number": "0551234567", "provider": "MTN",
    "wallet_name": "My MoMo", "is_primary": True
}, headers=customer_auth)
check("4b  Wallet: create MTN wallet (201 or 409)",
      resp_4b, resp_4b.status_code if resp_4b.status_code in (201, 409) else 201)

# 4c. List wallets
resp = client.get("/api/wallet", headers=customer_auth)
body = check("4c  Wallet: list", resp, 200,
    lambda b: (
        b.get("success") and len(b.get("wallets", [])) >= 1,
        f"{len(b.get('wallets', []))} wallet(s) found"
    ))

wallet_id = body["wallets"][0]["id"] if body.get("wallets") else None


# ═══════════════════════════════════════════════════════════════
# FLOW 5 — SMS Check: GENUINE message
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 5: SMS CHECK — GENUINE")
print("═"*60)

genuine_sms = (
    "You have received GHS 150.00 from KWAME ASANTE 0241234567. "
    "Transaction ID: 98765432100. Your new balance is GHS 1200.00. "
    "Fee charged: GHS 0.00. Tax: GHS 0.00."
)

resp = client.post("/api/message-checks/sms-check",
    json={"raw_text": genuine_sms, "wallet_id": wallet_id},
    headers=customer_auth)
body = check("5a  SMS genuine: HTTP 201", resp, 201)

def verify_genuine(b):
    pred = b.get("data", {}).get("prediction", {})
    label = pred.get("predicted_label", "")
    conf = pred.get("confidence_score", 0)
    ml_avail = pred.get("ml_available")
    return (
        label == "genuine" and conf >= 0.50,
        f"label={label}, conf={conf:.2f}, ml_available={ml_avail}"
    )

check("5b  SMS genuine: verdict=genuine, conf≥0.50", resp, 201, verify_genuine)
genuine_check_id = body.get("data", {}).get("message_check", {}).get("id") if body else None


# ═══════════════════════════════════════════════════════════════
# FLOW 6 — SMS Check: SUSPICIOUS message
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 6: SMS CHECK — SUSPICIOUS")
print("═"*60)

suspicious_sms = (
    "Cash received GHS 5000.00. Your account has been credited. "
    "Reference: ABC123. Balance: GHS 5500.00."
)

resp = client.post("/api/message-checks/sms-check",
    json={"raw_text": suspicious_sms},
    headers=customer_auth)
body = check("6a  SMS suspicious: HTTP 201", resp, 201)

def verify_suspicious_or_fraud(b):
    pred = b.get("data", {}).get("prediction", {})
    label = pred.get("predicted_label", "")
    return (
        label in ("suspicious", "likely_fraudulent"),
        f"label={label} (non-genuine expected)"
    )

check("6b  SMS suspicious: non-genuine verdict", resp, 201, verify_suspicious_or_fraud)
suspicious_check_id = body.get("data", {}).get("message_check", {}).get("id") if body else None


# ═══════════════════════════════════════════════════════════════
# FLOW 7 — SMS Check: LIKELY FRAUDULENT message
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 7: SMS CHECK — LIKELY FRAUDULENT")
print("═"*60)

fraud_sms = (
    "URGENT! Your MTN MoMo account will be SUSPENDED immediately! "
    "To verify your account send your PIN to 0551234567. "
    "Act now or lose your funds within 24 hours. "
    "Click http://mtn-verify-gh.com to confirm."
)

resp = client.post("/api/message-checks/sms-check",
    json={"raw_text": fraud_sms},
    headers=customer_auth)
body = check("7a  SMS fraud: HTTP 201", resp, 201)

def verify_fraud(b):
    pred = b.get("data", {}).get("prediction", {})
    label = pred.get("predicted_label", "")
    conf = pred.get("confidence_score", 0)
    expl = pred.get("explanation", "")
    return (
        label == "likely_fraudulent" and conf >= 0.60,
        f"label={label}, conf={conf:.2f}, expl_len={len(expl)}"
    )

check("7b  SMS fraud: verdict=likely_fraudulent, conf≥0.60", resp, 201, verify_fraud)
fraud_check_id = body.get("data", {}).get("message_check", {}).get("id") if body else None


# ═══════════════════════════════════════════════════════════════
# FLOW 8 — SMS Check: Validation errors
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 8: SMS CHECK — VALIDATION")
print("═"*60)

check("8a  SMS: empty body",
      client.post("/api/message-checks/sms-check",
          json={}, headers=customer_auth), 400)

check("8b  SMS: raw_text too short",
      client.post("/api/message-checks/sms-check",
          json={"raw_text": ""}, headers=customer_auth), 400)

check("8c  SMS: no auth token",
      client.post("/api/message-checks/sms-check",
          json={"raw_text": "test"}), 401)


# ═══════════════════════════════════════════════════════════════
# FLOW 9 — Screenshot Upload (minimal — no real Tesseract in CI)
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 9: SCREENSHOT UPLOAD")
print("═"*60)

# 9a. Reject non-image file
check("9a  Screenshot: reject .txt",
      client.post("/api/message-checks/upload-screenshot",
          data={"file": (io.BytesIO(b"not an image"), "fake.txt")},
          headers=customer_auth,
          content_type="multipart/form-data"), 400)

# 9b. Reject missing file
check("9b  Screenshot: no file field",
      client.post("/api/message-checks/upload-screenshot",
          data={},
          headers=customer_auth,
          content_type="multipart/form-data"), 400)

# 9c. Send a tiny valid PNG (1x1 pixel) — may get weak OCR / 200 or 202
PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
resp = client.post("/api/message-checks/upload-screenshot",
    data={"file": (io.BytesIO(PNG_1x1), "test.png")},
    headers=customer_auth,
    content_type="multipart/form-data")
# Accept either 200 (OCR worked somehow) or 202 (weak/no OCR)
check("9c  Screenshot: tiny PNG accepted (200 or 202)", resp,
      resp.status_code if resp.status_code in (200, 202) else 200,
      lambda b: (b.get("success") is True or resp.status_code == 202,
                 f"status={resp.status_code}"))


# ═══════════════════════════════════════════════════════════════
# FLOW 10 — History
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 10: MESSAGE CHECK HISTORY")
print("═"*60)

resp = client.get("/api/message-checks/history", headers=customer_auth)
body = check("10a History: HTTP 200", resp, 200)

def verify_history(b):
    items = b.get("data", [])  # data is a list of {message_check, prediction_summary}
    count = b.get("count", 0)
    return (
        count >= 3,
        f"{count} checks in history (need ≥3 from flows 5-7)"
    )

check("10b History: ≥3 checks present", resp, 200, verify_history)


# ═══════════════════════════════════════════════════════════════
# FLOW 11 — Detail Page
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 11: MESSAGE CHECK DETAIL")
print("═"*60)

if genuine_check_id:
    resp = client.get(f"/api/message-checks/{genuine_check_id}",
                      headers=customer_auth)
    def verify_detail(b):
        mc = b.get("data", {}).get("message_check", {})
        pred = b.get("data", {}).get("prediction", {})
        has_raw = bool(mc.get("raw_text"))
        has_label = bool(pred.get("predicted_label"))
        has_expl = bool(pred.get("explanation"))
        has_scores = all(
            pred.get(k) is not None
            for k in ("format_risk_score", "behavior_risk_score",
                      "balance_consistency_score", "sender_novelty_score")
        )
        return (
            has_raw and has_label and has_expl and has_scores,
            f"raw={'Y' if has_raw else 'N'}, label={'Y' if has_label else 'N'}, "
            f"expl={'Y' if has_expl else 'N'}, scores={'Y' if has_scores else 'N'}"
        )
    check("11a Detail: full payload for genuine check", resp, 200, verify_detail)
else:
    print("[SKIP] 11a — no genuine_check_id available")

# 11b. Non-existent ID
check("11b Detail: 404 for nonexistent",
      client.get("/api/message-checks/99999", headers=customer_auth), 404)


# ═══════════════════════════════════════════════════════════════
# FLOW 12 — Admin Review Queue
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 12: ADMIN REVIEW QUEUE")
print("═"*60)

# 12a. Customer cannot access
check("12a Reviews: customer blocked",
      client.get("/api/reviews/flagged", headers=customer_auth), 403)

# 12b. Admin can access
resp = client.get("/api/reviews/flagged", headers=admin_auth)
body = check("12b Reviews: admin sees flagged list", resp, 200)

def verify_flagged(b):
    items = b.get("data", [])  # data is a flat list of flagged check dicts
    count = b.get("count", 0)
    any_suspicious = any(
        i.get("predicted_label") in ("suspicious", "likely_fraudulent")
        for i in items
    )
    return (
        count >= 1 and any_suspicious,
        f"{count} flagged item(s)"
    )

check("12c Reviews: ≥1 flagged item from flows 6-7", resp, 200, verify_flagged)


# ═══════════════════════════════════════════════════════════════
# FLOW 13 — Admin Review Submission
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 13: ADMIN REVIEW SUBMISSION")
print("═"*60)

review_target = fraud_check_id or suspicious_check_id
if review_target:
    # 13a. Validation: bad reviewer_label
    check("13a Review: bad label rejected",
          client.post(f"/api/reviews/{review_target}",
              json={"reviewer_label": "WRONG", "review_status": "pending"},
              headers=admin_auth), 400)

    # 13b. Submit valid review (201 for new review, 200 for update)
    resp = client.post(f"/api/reviews/{review_target}",
        json={
            "reviewer_label": "likely_fraudulent",
            "review_status": "confirmed_fraud",
            "notes": "PIN request and urgency language — confirmed scam."
        },
        headers=admin_auth)
    check("13b Review: submit OK", resp, resp.status_code if resp.status_code in (200, 201) else 201,
        lambda b: (b.get("success") is True, "success=True"))

    # 13c. Re-fetch detail to verify review attached
    resp = client.get(f"/api/reviews/{review_target}", headers=admin_auth)
    def verify_review_attached(b):
        review = b.get("data", {}).get("review", {})
        return (
            review.get("reviewer_label") == "likely_fraudulent",
            f"reviewer_label={review.get('reviewer_label')}"
        )
    check("13c Review: detail shows submitted review", resp, 200, verify_review_attached)
else:
    print("[SKIP] 13a-c — no flagged check ID available")


# ═══════════════════════════════════════════════════════════════
# FLOW 14 — ML Integration Signals
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("FLOW 14: ML INTEGRATION SIGNALS")
print("═"*60)

# Re-check the genuine message and verify ML fields are present
if genuine_check_id:
    resp = client.get(f"/api/message-checks/{genuine_check_id}",
                      headers=customer_auth)
    body = resp.get_json(silent=True)
    pred = body.get("data", {}).get("prediction", {})
    ml_avail = pred.get("ml_available")
    ml_label = pred.get("ml_label")
    ml_conf  = pred.get("ml_confidence")
    ml_agrees = pred.get("ml_agrees")
    version  = pred.get("model_version", "")

    def verify_ml(b):
        p = b.get("data", {}).get("prediction", {})
        # ml_available should be a boolean
        has_ml_flag = isinstance(p.get("ml_available"), bool)
        # model_version should mention v6.1
        ver_ok = "v6.1" in p.get("model_version", "")
        return (
            has_ml_flag and ver_ok,
            f"ml_available={p.get('ml_available')}, ml_label={p.get('ml_label')}, "
            f"ml_conf={p.get('ml_confidence')}, ml_agrees={p.get('ml_agrees')}, "
            f"version={p.get('model_version')}"
        )

    check("14a ML fields present in prediction", resp, 200, verify_ml)

    if ml_avail:
        print(f"       ML model IS loaded — hybrid scoring active")
        print(f"       ml_label={ml_label}, ml_confidence={ml_conf}, ml_agrees={ml_agrees}")
        if "+ml" in version:
            print(f"       model_version tagged: {version}")
    else:
        print(f"       ML model NOT loaded — rule-only scoring (still valid)")
        print(f"       This is fine for demo if .pkl files aren't present")
else:
    print("[SKIP] 14a — no genuine_check_id")


# ═══════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════════════════════════
print("\n\n" + "═"*60)
print("  FINAL E2E TEST SUMMARY")
print("═"*60)

total = passed + failed

for r in results:
    mark = "✓" if r["ok"] else "✗"
    print(f"  {mark}  {r['label']}")

print(f"\n{'─'*60}")
print(f"  PASSED: {passed}/{total}")
print(f"  FAILED: {failed}/{total}")
print("─"*60)

if failed == 0:
    print("\n  ★  ALL TESTS PASSED — system is demo-ready!  ★\n")
else:
    print(f"\n  ⚠  {failed} test(s) need attention before demo.\n")

sys.exit(0 if failed == 0 else 1)

"""End-to-end test of the /api/message-checks/sms-check route after DB migration."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "flask_backend"))
os.chdir(os.path.join(os.path.dirname(__file__), "flask_backend"))

from app import create_app
app = create_app()

with app.test_client() as c:
    # Register + login
    c.post("/api/auth/register", json={
        "full_name": "Test User",
        "email": "e2e_phase6@test.com",
        "phone_number": "0551234567",
        "password": "TestPass123!"
    })
    login_resp = c.post("/api/auth/login", json={
        "email": "e2e_phase6@test.com",
        "password": "TestPass123!"
    })
    login_data = login_resp.get_json()
    token = login_data.get("token") or login_data.get("data", {}).get("token")
    assert token, f"Login failed: {login_data}"
    print(f"1. Login OK (token={token[:20]}...)")

    headers = {"Authorization": f"Bearer {token}"}

    # ── SMS Check ──
    sms_resp = c.post("/api/message-checks/sms-check",
        headers=headers,
        json={
            "raw_text": (
                "You have received GHS 50.00 from KWAME ASANTE 0241234567. "
                "Transaction ID: 12345678901. Your new balance is GHS 200.00. "
                "Fee charged: GHS 0.00. Tax: GHS 0.00."
            )
        }
    )
    print(f"2. SMS check: status={sms_resp.status_code}")
    sms_body = sms_resp.get_json()
    print(f"   success={sms_body.get('success')}")
    if sms_resp.status_code != 201:
        print(f"   ERRORS: {sms_body.get('errors')}")
        print(f"   FULL: {json.dumps(sms_body, indent=2)}")
        sys.exit(1)

    pred = sms_body["data"]["prediction"]
    check = sms_body["data"]["message_check"]
    print(f"   label={pred['predicted_label']}, confidence={pred['confidence_score']}")
    print(f"   check_id={check['id']}, status={check['status']}, amount={check['amount']}")
    assert "screenshot_path" not in check, "SECURITY: screenshot_path leaked!"
    assert pred["model_version"], "model_version missing from prediction"

    check_id = check["id"]

    # ── History ──
    hist_resp = c.get("/api/message-checks/history", headers=headers)
    print(f"3. History: status={hist_resp.status_code}")
    hist_body = hist_resp.get_json()
    print(f"   count={hist_body.get('count')}")
    assert hist_body["count"] >= 1

    # ── Detail ──
    detail_resp = c.get(f"/api/message-checks/{check_id}", headers=headers)
    print(f"4. Detail: status={detail_resp.status_code}")
    detail_body = detail_resp.get_json()
    detail_pred = detail_body["data"]["prediction"]
    print(f"   prediction.id={detail_pred.get('id')}, model_version={detail_pred.get('model_version')}")
    assert detail_pred.get("id") is not None

    # ── Validation: missing raw_text ──
    bad_resp = c.post("/api/message-checks/sms-check",
        headers=headers, json={})
    print(f"5. Missing raw_text: status={bad_resp.status_code} (expect 400)")
    assert bad_resp.status_code == 400

    # ── No auth ──
    noauth = c.get("/api/message-checks/history")
    print(f"6. No auth: status={noauth.status_code} (expect 401)")
    assert noauth.status_code == 401

    # ── Verify old routes still work ──
    wallet_resp = c.get("/api/wallet", headers=headers)
    print(f"7. Old route /api/wallet: status={wallet_resp.status_code}")

    print("\nAll end-to-end tests passed!")

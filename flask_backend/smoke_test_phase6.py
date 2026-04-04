"""Quick smoke test for Phase 6 Part 2 refinements."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

# Test imports
from services.sms_parser import parse_sms
from services.authenticity_engine import analyze_message
from services.message_check_service import check_sms, check_screenshot, get_user_history, get_check_detail
from routes.message_check_routes import message_check_bp
print("All imports OK")

# Test parser
sms = (
    "You have received GHS 50.00 from KWAME ASANTE 0241234567. "
    "Transaction ID: 12345678901. Your new balance is GHS 200.00. "
    "Fee charged: GHS 0.00. Tax: GHS 0.00."
)
parsed = parse_sms(sms)
pc = parsed["parser_confidence"]
tt = parsed.get("transaction_type")
amt = parsed.get("amount")
print(f"Parser OK: confidence={pc:.2f}, type={tt}, amount={amt}")
assert pc > 0.5, f"parser_confidence too low: {pc}"

# Test engine with mock profile
profile = {
    "total_checks_count": 5,
    "avg_incoming_amount": 40.0,
    "max_incoming_amount": 100.0,
    "usual_senders": ["0241234567"],
    "usual_transaction_types": ["transfer"],
}
result = analyze_message(sms, parsed, profile)
label = result["predicted_label"]
conf = result["confidence_score"]
print(f"Engine OK: label={label}, confidence={conf:.2f}")
assert 0 <= conf <= 1.0, f"confidence out of range: {conf}"
assert label in ("genuine", "suspicious", "likely_fraudulent"), f"unexpected label: {label}"

# Test Flask app boots
from app import create_app
app = create_app()
with app.test_client() as c:
    r = c.get("/api/message-checks/history")
    print(f"App boot OK: /history returned {r.status_code} (401 expected)")
    assert r.status_code == 401

print("\nAll smoke tests passed.")

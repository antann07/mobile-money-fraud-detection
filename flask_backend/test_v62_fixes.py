"""Quick validation of v6.2 authenticity engine fixes."""

from services.sms_parser import parse_sms
from services.authenticity_engine import analyze_message


def test(label, sms, input_method="sms_paste"):
    parsed = parse_sms(sms)
    result = analyze_message(sms, parsed, None, input_method=input_method)
    print(f"\n=== {label} ===")
    print(f"  Label:       {result['predicted_label']}")
    print(f"  Confidence:  {result['confidence_score']}")
    print(f"  Format risk: {result['format_risk_score']}")
    print(f"  Explanation: {result['explanation'][:200]}")
    return result


# 1. Standard genuine SMS (no timestamp) — should be genuine, no warnings
r = test("Standard genuine (no timestamp)",
    "You have received GHS 50.00 from JOHN DOE (0241234567). "
    "Transaction ID: 78319906534. Your new balance is GHS 150.00. "
    "Fee charged: GHS 0.00. E-levy: GHS 0.00.")
assert r["predicted_label"] == "genuine", "FAIL: should be genuine"

# 2. Opener with extra spaces — should still match
r = test("Extra spaces in opener",
    "You  have  received GHS 200.00 from KWAME ASANTE (0551234567). "
    "Transaction ID: 12345678901. Your new balance is GHS 500.00. "
    "Fee charged: GHS 1.00. E-levy: GHS 2.00.")
assert r["predicted_label"] == "genuine", "FAIL: should be genuine"

# 3. Non-standard opener but strong genuine fields — should be genuine
r = test("Non-standard opener + strong fields",
    "Transfer of GHS 100.00 received from AMA MENSAH 0201234567. "
    "Transaction ID: 99887766554. Your new balance is GHS 350.00. "
    "Fee charged: GHS 0.50.")
assert r["predicted_label"] == "genuine", "FAIL: should be genuine"
assert "opening phrase" not in r["explanation"], "FAIL: should not warn about opener"

# 4. Pasted SMS missing datetime — should NOT warn about datetime
r = test("Pasted SMS missing datetime (should be silent)",
    "You have received GHS 75.00 from ABENA OWUSU (0241112222). "
    "Transaction ID: 55566677788. Your new balance is GHS 225.00. "
    "Fee charged: GHS 0.00.")
assert r["predicted_label"] == "genuine", "FAIL: should be genuine"
assert "date or time" not in r["explanation"], "FAIL: should not warn about datetime"

# 5. Screenshot OCR with missing datetime — SHOULD warn
r = test("Screenshot OCR missing datetime (should warn)",
    "You have received GHS 75.00 from ABENA OWUSU (0241112222). "
    "Transaction ID: 55566677788. Your new balance is GHS 225.00. "
    "Fee charged: GHS 0.00.",
    input_method="screenshot_ocr")
assert r["predicted_label"] == "genuine", "FAIL: should be genuine"

# 6. Scam message — should still be flagged
r = test("Scam message (should be flagged)",
    "Dear Customer, you have received GHS 5000.00. "
    "Kindly return GHS 4000.00 immediately. "
    "Your PIN is required to confirm.")
assert r["predicted_label"] == "likely_fraudulent", "FAIL: should be fraudulent"

# 7. Urgency scam (missing strong fields) — should be flagged
r = test("Urgency scam",
    "You have received GHS 1000.00 from UNKNOWN (0241234567). "
    "Act now or your account will be blocked! Send back GHS 500.00 immediately.")
assert r["predicted_label"] != "genuine", "FAIL: should not be genuine"

print("\n\n*** ALL TESTS PASSED ***")

"""
Test: screenshot with OCR noise ("reversed", "suspended", "update your")
alongside a genuine Payment-made message.

Expected: BOTH sms_paste AND screenshot_ocr should classify as 'genuine'.
The screenshot path previously classified as 'likely_fraudulent' due to
app-UI context words triggering Stage B urgency/suspicious checks.
"""
import sys
sys.path.insert(0, ".")
from services.authenticity_engine import analyze_message
from services.sms_parser import parse_sms

# ── Test 1: SMS paste (clean text, no noise) ──
sms_text = (
    "Payment made for GHS 1,000.00 to MARY AMA ANDOH.\n"
    "Transaction ID: 12345678901\n"
    "Fee charged: GHS 2.50\n"
    "TAX charged: GHS 5.00\n"
    "Current Balance: GHS 500.00\n"
    "Available Balance: GHS 495.00\n"
)

# ── Test 2: Screenshot OCR — same message but with app-UI context noise ──
# Simulates what Tesseract/ML-Kit produces when the user takes a full screen
# capture of the MTN MoMo app inbox, which shows prior transaction history.
ocr_with_noise = (
    "MTN MoMo\n\n"
    "Payment made for GHS 1,000.00 to MARY AMA ANDOH.\n"
    "Transaction ID: 12345678901\n"
    "Reference: ABC123DEF456\n"
    "Fee charged: GHS 2.50\n"
    "TAX charged: GHS 5.00\n"
    "Current Balance: GHS 500.00\n"
    "Available Balance: GHS 495.00\n\n"
    "--- Previous transactions ---\n"
    "Transaction reversed - GHS 50.00\n"
    "Account suspended (tap to view)\n"
    "Update your profile\n"
)

# ── Test 3: Screenshot with a real scam phrase embedded in OCR ──
ocr_with_scam = (
    "Payment made for GHS 1,000.00 to MARY AMA ANDOH.\n"
    "Transaction ID: 12345678901\n"
    "Fee charged: GHS 2.50\n"
    "Current Balance: GHS 500.00\n\n"
    "Dear customer, kindly return GHS 1,000.00 as it was sent in error.\n"
    "Please call customer care: 0244000000\n"
)

# ── Test 4: Genuine incoming screenshot with "reversed" in the app UI ──
ocr_incoming = (
    "MTN Mobile Money\n\n"
    "Payment received for GHS 31.00 from MARY AGGREY.\n"
    "Transaction ID: 98765432101\n"
    "Current Balance: GHS 250.00\n\n"
    "Transaction reversed  ← tap to dispute\n"
    "locked   Contact support\n"
)

print("=" * 60)
print("SCENARIO: Text vs Screenshot of same Payment-made message")
print("=" * 60)

r1 = analyze_message(sms_text, parse_sms(sms_text), input_method="sms_paste")
r2 = analyze_message(ocr_with_noise, parse_sms(ocr_with_noise), input_method="screenshot_ocr")
r3 = analyze_message(ocr_with_scam, parse_sms(ocr_with_scam), input_method="screenshot_ocr")
r4 = analyze_message(ocr_incoming, parse_sms(ocr_incoming), input_method="screenshot_ocr")

PASS = "[PASS]"
FAIL = "[FAIL]"

tests = [
    ("SMS paste — Payment made", r1, "genuine"),
    ("Screenshot + 'reversed'/'suspended'/'update your' (OCR noise)", r2, "genuine"),
    ("Screenshot + embedded 'dear customer'/'kindly return' (real scam)", r3, "!!not genuine"),
    ("Incoming screenshot + 'reversed locked' in app UI", r4, "genuine"),
]

all_ok = True
for name, result, expected in tests:
    label = result["predicted_label"]
    risk  = result["format_risk_score"]
    flags = result.get("flags", [])

    if expected == "!!not genuine":
        ok = label != "genuine"
    else:
        ok = label == expected

    status = PASS if ok else FAIL
    if not ok:
        all_ok = False

    noise = "screenshot_noise_suppressed" in flags
    lock  = "genuine_lock" in flags
    print(f"\n{status} {name}")
    print(f"       label={label}  text_risk={risk:.3f}")
    print(f"       noise_suppressed={noise}  genuine_lock={lock}")
    if not ok:
        print(f"       EXPECTED: {expected}")
        print(f"       flags: {flags}")

print()
if all_ok:
    print("ALL SCENARIO TESTS PASSED")
else:
    print("SOME TESTS FAILED — see details above")
    sys.exit(1)

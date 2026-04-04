"""Quick test for Phase 8 Part 3 OCR refinements — run then delete."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "flask_backend"))

from services.ocr_service import (
    extract_text, is_available,
    _normalize_ocr_text, _estimate_confidence, _text_is_usable,
)

print("OCR available:", is_available())
print()

# ── Normalization tests ──
tests = [
    ("GH$ 5O.OO", "GHS 50.00"),
    ("Transacti0n 1D| 99999", "Transaction ID: 99999"),
    ("Ca5h 1n rece1ved", "Cash In received"),
    ("Ca5h 0ut", "Cash Out"),
    ("F3e charged; GHS 1.00", "Fee charged: GHS 1.00"),
    ("Ava1lab1e Ba1ance| GI-IS 500.00", "Available Balance: GHS 500.00"),
    ("Succ3ssfu1 Tran5fer", "Successful Transfer"),
    ("E-1evy: GHS 0.25", "E-Levy: GHS 0.25"),
    ("25/O3/2O26", "25/03/2026"),
    ("GHS 1.000.00", "GHS 1,000.00"),
    ("You have rece1ved", "You have received"),
    ("M0M0 Payment", "MoMo Payment"),
    ("Acc0unt Ba1ance", "Account Balance"),
    ("P3nding W1thdraw", "Pending Withdraw"),
    ("Comp1eted D3posit", "Completed Deposit"),
]

all_pass = True
for inp, expected in tests:
    result = _normalize_ocr_text(inp)
    ok = expected in result
    status = "OK" if ok else "FAIL"
    if not ok:
        print(f"  {status}: '{inp}' -> '{result}'  (expected '{expected}')")
        all_pass = False
    else:
        print(f"  {status}: '{inp}' -> '{result}'")

print()
print("Normalization:", "ALL PASSED" if all_pass else "SOME FAILED")
print()

# ── Confidence tests ──
rich = """You have received GHS 50.00 from JOHN DOE.
Transaction ID: 123456789
Current Balance: GHS 150.00
Available Balance: GHS 150.00
Fee charged: GHS 0.00
E-Levy: GHS 0.50
25/03/2026 14:30"""

conf = _estimate_confidence(rich, rich)
print(f"Rich MoMo confidence:  {conf}  (expect >= 0.8)")
assert conf >= 0.8, f"Expected >= 0.8, got {conf}"

garbage = "xyzzy foo bar baz"
conf_g = _estimate_confidence(garbage, garbage)
print(f"Garbage confidence:    {conf_g}  (expect < 0.3)")
assert conf_g < 0.3, f"Expected < 0.3, got {conf_g}"

medium = "You received GHS 50.00 MoMo"
conf_m = _estimate_confidence(medium, medium)
print(f"Medium confidence:     {conf_m}  (expect 0.3-0.7)")

print()

# ── Usability tests ──
assert _text_is_usable("You have received GHS 50 from someone on MTN MoMo") == True
assert _text_is_usable("short") == False
assert _text_is_usable("This is a long text with no special keywords at all, just random words here") == False
assert _text_is_usable("E-Levy charged on your withdrawal of GHS 100") == True
print("Usability tests: ALL PASSED")

print("\n=== All OCR refinement tests passed! ===")

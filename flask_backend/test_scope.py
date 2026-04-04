"""
test_scope.py — Regression test for fraud-detection scope correctness.

IN-SCOPE  (fraud model runs):
  - Incoming transfer received
  - Cash-in / deposit received
  - Payment received

OUT-OF-SCOPE (model returns out_of_scope, no analysis):
  - Payment made / outgoing payment confirmation
  - Cash-out / withdrawal
  - Airtime purchase

Scam messages that target incoming-credit scenarios must still be caught.
"""
import sys
sys.path.insert(0, ".")
from services.sms_parser import parse_sms, is_in_scope
from services.authenticity_engine import analyze_message

PASS = "[PASS]"
FAIL = "[FAIL]"

# ─────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────
def check(name: str, text: str, expect_in_scope: bool,
          expect_label: str | None = None) -> bool:
    parsed = parse_sms(text)
    in_scope, reason = is_in_scope(parsed)

    if in_scope != expect_in_scope:
        print(f"{FAIL} {name}")
        print(f"       in_scope={in_scope} expected={expect_in_scope} reason={reason!r}")
        print(f"       direction={parsed.get('direction')} type={parsed.get('transaction_type')}")
        return False

    if in_scope and expect_label is not None:
        result = analyze_message(text, parsed, None, input_method="sms_paste")
        actual_label = result["predicted_label"]
        if actual_label != expect_label:
            print(f"{FAIL} {name}")
            print(f"       in_scope=True but label={actual_label} expected={expect_label}")
            return False

    noise = f"  [{reason[:60]}]" if reason else ""
    label_note = ""
    if in_scope and expect_label:
        result = analyze_message(text, parsed, None, input_method="sms_paste")
        label_note = f"  label={result['predicted_label']}"
    print(f"{PASS} {name}{noise}{label_note}")
    return True


# ─────────────────────────────────────────────────
# Test cases
# ─────────────────────────────────────────────────
all_ok = True

print("=" * 60)
print("IN-SCOPE MESSAGES (should be analysed)")
print("=" * 60)

cases_in_scope = [
    (
        "Transfer received (classic)",
        "You have received GHS 50.00 from JOHN DOE (0241234567).\n"
        "Transaction ID: 12345678901. New Balance: GHS 150.00.\n"
        "Fee charged: GHS 0.00.",
        "genuine",
    ),
    (
        "Payment received",
        "Payment received for GHS 31.00 from MARY AGGREY.\n"
        "Transaction ID: 98765432101\nCurrent Balance: GHS 250.00",
        "genuine",
    ),
    (
        "Cash-in / deposit",
        "Cash In of GHS 200.00 credited to your account.\n"
        "Transaction ID: 55544433322\nNew Balance: GHS 700.00.",
        "genuine",
    ),
    (
        "Scam — fake incoming credit",
        "You have received GHS 500.00 from MTN HEAD OFFICE.\n"
        "Kindly call 0244000000 to confirm your PIN to process the transaction.",
        None,  # just check scope — scam message, don't assert specific label here
    ),
]

for name, text, expect_label in cases_in_scope:
    result = check(name, text, expect_in_scope=True, expect_label=expect_label)
    all_ok = all_ok and result


print()
print("=" * 60)
print("OUT-OF-SCOPE MESSAGES (should be saved but not analysed)")
print("=" * 60)

cases_out_of_scope = [
    (
        "Payment made for (outgoing)",
        "Payment made for GHS 1,000.00 to MARY AMA ANDOH.\n"
        "Transaction ID: 12345678901\nFee charged: GHS 2.50\n"
        "Current Balance: GHS 500.00",
    ),
    (
        "Payment to (outgoing)",
        "You have paid GHS 45.00 to SHOPRITE Ghana.\n"
        "Transaction ID: 67890\nBalance: GHS 350.00.",
    ),
    (
        "Cash-out / withdrawal",
        "Cash Out of GHS 100.00 processed.\n"
        "Transaction ID: 11223344. New Balance: GHS 600.00.",
    ),
    (
        "Airtime purchase",
        "Airtime top-up of GHS 10.00 for 0244123456 was successful.\n"
        "Transaction ID: 99887766. Balance: GHS 240.00.",
    ),
    (
        "Generic 'sent' outgoing",
        "You have sent GHS 200.00 to KWAME BOATENG (0261234567).\n"
        "Transaction ID: 33221100. New Balance: GHS 800.00.",
    ),
]

for name, text in cases_out_of_scope:
    result = check(name, text, expect_in_scope=False)
    all_ok = all_ok and result


print()
print("=" * 60)
print("SCAM MESSAGES IN-SCOPE (must still be caught)")
print("=" * 60)

scam_cases = [
    (
        "Fake incoming + PIN demand",
        "You have received GHS 500.00 from 0244000000.\n"
        "To confirm receipt enter your PIN. Call 0244000000 if not you.\n"
        "Transaction ID: 55566677.",
        "likely_fraudulent",
    ),
    (
        "Wrong transfer reversal scam",
        "You have received GHS 800.00 from MERCY (0271234567). "
        "I sent this in error, kindly return it. Your account will be "
        "blocked if you fail to return. Contact: 0271234567.",
        "likely_fraudulent",
    ),
    (
        "Blocked account + callback incoming",
        "You received GHS 1000 from MTN. Your account has been flagged. "
        "Call customer care now on 0264000000 to reverse the transaction "
        "or your account will be suspended.",
        "likely_fraudulent",
    ),
]

for name, text, expect_label in scam_cases:
    result = check(name, text, expect_in_scope=True, expect_label=expect_label)
    all_ok = all_ok and result


print()
print("=" * 60)
print("REGRESSION: FIXED ROUTING BUGS")
print("=" * 60)

regression_cases_in_scope = [
    # Bug 1: "deposited" (past tense) was undetected → unknown → OOS
    (
        "deposited past tense",
        "GHS 500.00 has been deposited into your account. "
        "Call 0244000000 to verify your identity.",
    ),
    # Bug 2: "transferred to your account" triggered generic outgoing → OOS
    (
        "transferred TO your account (passive)",
        "GHS 300.00 was transferred to your MoMo account. "
        "Transaction ID: 77665544.",
    ),
    # Bug 2b: "to your account" directional signal with no other keyword
    (
        "credit made to your account (no received/credited keyword)",
        "A credit of GHS 500 has been made to your MoMo account. "
        "Call 0501234567 to authorize.",
    ),
    # Bug 3: "sent to your number" → outgoing via 'sent'; should be incoming
    (
        "sent to your number (reversal scam phrasing)",
        "I sent GHS 500 to your number by mistake. "
        "Please return via 0271234567 immediately.",
    ),
    # Bug 4a: unknown direction + scam signal → now upgraded to in-scope
    (
        "mistaken transfer (no incoming keyword, scam signal only)",
        "Dear customer, a mistaken transfer of GHS 200 was made. "
        "Call 0500000000 to reverse.",
    ),
    # Bug 4b: 'reversal' scam phrase with unknown direction
    (
        "reversal scam language (unknown direction)",
        "GHS 400 reversal of transfer pending. Call MTN head office "
        "to confirm your pin.",
    ),
    # Bug 5: outgoing 'sent' + 'by mistake' scam signal → now upgraded
    (
        "outgoing 'sent' + by mistake (upgrades to in-scope)",
        "I sent you GHS 800 by mistake. Kindly return it immediately "
        "or your account will be blocked. Call 0244999888.",
    ),
]

for name, text in regression_cases_in_scope:
    result = check(name, text, expect_in_scope=True)
    all_ok = all_ok and result

# Regression: genuine outgoing must NOT be upgraded by scam check
regression_cases_out_of_scope = [
    (
        "genuine outgoing: you transferred to your savings (not a scam)",
        "You have transferred GHS 200.00 to your savings account. "
        "Transaction ID: 44556677. New Balance: GHS 1300.00.",
    ),
    (
        "genuine outgoing: 'sent' to named recipient (no scam signal)",
        "You have sent GHS 50.00 to AMA MENSAH (0241112233). "
        "New Balance: GHS 950.00.",
    ),
]

print()
print("  (Genuine outgoing — must stay OUT-OF-SCOPE):")
for name, text in regression_cases_out_of_scope:
    result = check(name, text, expect_in_scope=False)
    all_ok = all_ok and result


print()
print("=" * 60)
print("REGRESSION: PHASE 4 — bad-grammar incoming claims")
print("=" * 60)

# Bug: "Cash receive for X from NAME" was direction=unknown → OOS
# Fix: added \bcash\s+receive\b and \breceive\b rules to Group 3,
#      and _INCOMING_CLAIM_RE fallback in is_in_scope() unknown branch.

phase4_in_scope = [
    (
        "cash receive (exact bug report)",
        "Cash receive for 505.00 from REBECCA APPIAH CHRIST THE KING "
        "MOBlLE MONEY ENTERPRISEOPPOSlTE DANSOMAN OVER HEAD ID-245236251",
        "likely_fraudulent",   # homoglyphs + suspicious phrase + no balance
    ),
    (
        "payment receive (non-past-tense incoming)",
        "Payment receive of GHS 200.00 from KWAME ASANTE. "
        "Transaction ID: 998877. Verify with MTN.",
        None,   # scope check only
    ),
    (
        "money receive (non-past-tense incoming)",
        "Money receive GHS 350.00 from AMA OWUSU. "
        "Call 0244000000 to confirm receipt.",
        None,
    ),
    (
        "momo receive (scam template)",
        "Momo receive for GHS 700.00 from HEAD OFFICE. "
        "Please call 0277654321 to activate your account.",
        None,
    ),
    (
        "GHS+from pattern (no incoming verb — _INCOMING_CLAIM_RE fallback)",
        "GHS 505.00 from REBECCA APPIAH CHRIST THE KING ID-245236251",
        None,
    ),
]

for name, text, *rest in phase4_in_scope:
    expect_label = rest[0] if rest else None
    result = check(name, text, expect_in_scope=True, expect_label=expect_label)
    all_ok = all_ok and result

# Outgoing messages must NOT be caught by the generic \breceive\b rule
phase4_out_of_scope = [
    (
        "genuine outgoing: 'you sent' — must not be re-routed by receive rule",
        "You have sent GHS 100.00 to KOFI MENSAH (0261001001). "
        "New Balance: GHS 900.00.",
    ),
    (
        "genuine cash-out: no incoming signal, no scam signal",
        "Cash Out of GHS 200.00 processed at DANSOMAN AGENT. "
        "Transaction ID: 55443322. Balance: GHS 600.00.",
    ),
]

print()
print("  (Genuine outgoing — must stay OUT-OF-SCOPE):")
for name, text in phase4_out_of_scope:
    result = check(name, text, expect_in_scope=False)
    all_ok = all_ok and result

print()
if all_ok:
    print("ALL SCOPE TESTS PASSED")
else:
    print("SOME TESTS FAILED — see details above")
    sys.exit(1)

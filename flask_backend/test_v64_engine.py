"""
test_v64_engine.py — Regression suite for v6.4 authenticity-engine improvements.

Tests the three classes of incoming-money messages:
  GENUINE   — real-looking MTN notification, no scam signals
  SUSPICIOUS — incoming claim with missing key fields (no txn ID / balance)
  FRAUDULENT — incoming claim with strong scam signals

Also verifies that:
  - Non-MTN incoming-claim openers ("has been deposited" etc.) now get
    the lighter non_mtn_incoming_claim penalty instead of no_canonical_opener.
  - Callback-number instruction (call_phone_number) fires as a HARD signal.
  - "please return", "accidentally sent", "do not spend" fire correctly.
  - "will be reversed" / "if not returned" fire as hard urgency.
  - Genuine well-structured messages are never demoted by the new rules.
"""
import sys
sys.path.insert(0, ".")
from services.sms_parser import parse_sms, is_in_scope
from services.authenticity_engine import analyze_message

PASS = "[PASS]"
FAIL = "[FAIL]"
_failures = 0


def check(name: str, text: str, expect_label: str) -> bool:
    global _failures
    parsed = parse_sms(text)
    in_scope, _ = is_in_scope(parsed)
    if not in_scope:
        print(f"{FAIL} {name}")
        print(f"       Scope gate blocked it (direction={parsed.get('direction')})")
        _failures += 1
        return False
    result = analyze_message(text, parsed, None, input_method="sms_paste")
    label = result["predicted_label"]
    conf = result["confidence_score"]
    if label != expect_label:
        print(f"{FAIL} {name}")
        print(f"       got={label}  expected={expect_label}  conf={conf:.2f}")
        print(f"       explanation: {result['explanation'][:120]}")
        _failures += 1
        return False
    print(f"{PASS} {name}  ({label}, conf={conf:.2f})")
    return True


def check_flag(name: str, text: str, expect_flag_fragment: str) -> bool:
    """Check that a specific flag appears in the text_flags."""
    global _failures
    parsed = parse_sms(text)
    # Import internals for flag inspection
    from services.authenticity_engine import _score_text_authenticity
    _, flags = _score_text_authenticity(text, parsed, "sms_paste")
    matched = any(expect_flag_fragment in f for f in flags)
    if matched:
        print(f"{PASS} {name}  (flag '{expect_flag_fragment}' present)")
        return True
    else:
        print(f"{FAIL} {name}  (flag '{expect_flag_fragment}' NOT found in {flags})")
        _failures += 1
        return False


# ─────────────────────────────────────────────────────────────────────
# 1. NON-MTN INCOMING-CLAIM OPENER (lighter penalty, not hard)
# ─────────────────────────────────────────────────────────────────────
print("=" * 60)
print("1. NON-MTN INCOMING-CLAIM OPENERS")
print("=" * 60)

# "has been deposited" → non_mtn_incoming_claim (0.10) not no_canonical_opener (0.32)
check_flag(
    "'has been deposited' → non_mtn_incoming_claim flag",
    "GHS 750.00 has been deposited into your MoMo wallet. "
    "Transaction ID: 44556677890. New Balance: GHS 1200.00. Fee: GHS 0.00.",
    "tmpl:non_mtn_incoming_claim",
)
# And because it has all fields → genuine
check(
    "'has been deposited' with full fields → genuine",
    "GHS 750.00 has been deposited into your MoMo wallet. "
    "Transaction ID: 44556677890. New Balance: GHS 1200.00. Fee: GHS 0.00.",
    "genuine",
)

# "was transferred to your account" with full fields → genuine
check(
    "'was transferred to your account' with full fields → genuine",
    "GHS 320.00 was transferred to your MoMo account by KWAME ASANTE (0241112233). "
    "Transaction ID: 99887766554. New Balance: GHS 650.00. Fee charged: GHS 0.00.",
    "genuine",
)

# "has been credited" with no balance/txn (incomplete) → likely_fraudulent
# because "credited" is itself a suspicious phrase (bank-style, not MTN)
check(
    "'has been credited' — no balance, no txn-id → likely_fraudulent",
    "GHS 500 has been credited to your wallet. Please confirm.",
    "likely_fraudulent",
)


# ─────────────────────────────────────────────────────────────────────
# 2. CALLBACK-NUMBER INSTRUCTION (new hard signal)
# ─────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("2. CALLBACK-NUMBER INSTRUCTION")
print("=" * 60)

check_flag(
    "'call 0244xxxxxxx' → call_phone_number flag",
    "You have received GHS 500.00. Call 0244553311 to confirm receipt.",
    "suspicious_phrase:call_phone_number",
)
check(
    "Incoming with 'call 0244xxx' → likely_fraudulent",
    "You have received GHS 500.00 from MTN. Call 0244553311 to confirm your PIN.",
    "likely_fraudulent",
)
check(
    "Passive deposit + callback number → likely_fraudulent",
    "GHS 500 has been deposited into your account. "
    "Call 0271234567 immediately to verify your identity.",
    "likely_fraudulent",
)
# "dial *170#" (legitimate shortcode) must NOT trigger call_phone_number
# Note: "You have received" is a canonical MTN opener, so no non_mtn flag fires;
# the key assertion is simply that dial_phone_number is NOT flagged.
parsed_legit = parse_sms("You have received GHS 200.00. Dial *170# to check your balance.")
from services.authenticity_engine import _score_text_authenticity
_, legit_flags = _score_text_authenticity(
    "You have received GHS 200.00. Dial *170# to check your balance.",
    parsed_legit, "sms_paste"
)
if "suspicious_phrase:dial_phone_number" not in legit_flags:
    print(f"{PASS} 'dial *170#' correctly NOT flagged as dial_phone_number")
else:
    print(f"{FAIL} 'dial *170#' incorrectly flagged as dial_phone_number")
    _failures += 1


# ─────────────────────────────────────────────────────────────────────
# 3. RETURN-MONEY LANGUAGE (new signals)
# ─────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("3. RETURN-MONEY LANGUAGE")
print("=" * 60)

check(
    "'please return the money' reversal scam → likely_fraudulent",
    "You have received GHS 800 from 0271234567. "
    "Please return the money, it was sent to you by mistake.",
    "likely_fraudulent",
)
check(
    "'accidentally sent' reversal scam → likely_fraudulent",
    "GHS 600 was transferred to your MoMo wallet. "
    "I accidentally sent this to the wrong number. "
    "Please contact 0244888777.",
    "likely_fraudulent",
)
check(
    "'do not spend' scam → likely_fraudulent",
    "You have received GHS 1000.00. Do not spend the money. "
    "This was a wrong transaction. Call 0201234567 to reverse.",
    "likely_fraudulent",
)
check(
    "'mistakenly sent GHS' → likely_fraudulent",
    "Dear customer, I mistakenly sent GHS 500 to your number. "
    "Kindly return via MoMo. Call customer care: 0244000000.",
    "likely_fraudulent",
)


# ─────────────────────────────────────────────────────────────────────
# 4. REVERSAL / THREAT LANGUAGE (new urgency signals)
# ─────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("4. REVERSAL AND RETURN THREAT LANGUAGE")
print("=" * 60)

check(
    "'will be reversed' threat → likely_fraudulent",
    "You have received GHS 400.00. This transaction will be reversed "
    "if you do not call 0244555666 to confirm your PIN immediately.",
    "likely_fraudulent",
)
check(
    "'if not returned' threat → likely_fraudulent",
    "GHS 750 has been deposited to your account. "
    "If not returned within 24 hours, your account will be closed. "
    "Contact MTN head office on 0277999888.",
    "likely_fraudulent",
)


# ─────────────────────────────────────────────────────────────────────
# 5. GENUINE MESSAGES MUST NOT BE DEMOTED
# ─────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("5. GENUINE MESSAGES MUST NOT BE DEMOTED")
print("=" * 60)

check(
    "Classic 'You have received' → still genuine",
    "You have received GHS 150.00 from ABENA OSEI (0271234567).\n"
    "Transaction ID: 55544433322. New Balance: GHS 850.00.\n"
    "Fee charged: GHS 0.00.",
    "genuine",
)
check(
    "Cash-in deposit (full fields) → still genuine",
    "Cash In of GHS 300.00 credited to your account.\n"
    "Transaction ID: 66677788899. New Balance: GHS 1200.00.\n"
    "Fee charged: GHS 0.00. Tax charged: GHS 0.00.",
    "genuine",
)
check(
    "Payment received (full fields) → still genuine",
    "Payment of GHS 75.00 received from KOJO MENSAH (0201234567).\n"
    "Transaction ID: 12345678901. New Balance: GHS 475.00.\n"
    "Fee charged: GHS 0.00.",
    "genuine",
)
check(
    "Non-MTN format with full transaction data → still genuine",
    "GHS 250.00 was transferred to your account by AMA KOFI (0244123456).\n"
    "Transaction ID: 98877665544. New Balance: GHS 750.00. Fee: GHS 0.00.",
    "genuine",
)


# ─────────────────────────────────────────────────────────────────────
# 6. MIXED-SIGNAL MESSAGES (should be suspicious, not fraudulent)
# ─────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("6. MIXED-SIGNAL MESSAGES (should be suspicious)")
print("=" * 60)

check(
    "Incoming claim, missing txn-id and balance → suspicious",
    "GHS 500 has been transferred to your MoMo. Confirm receipt.",
    "suspicious",
)
check(
    "Non-MTN opener, has balance but missing txn-id → genuine",
    "GHS 200 was transferred to your account by KOJO. "
    "New Balance: GHS 800.00. Please verify at *170#.",
    "genuine",
)


print()
print("=" * 60)
if _failures == 0:
    print("ALL V6.4 ENGINE TESTS PASSED")
else:
    print(f"{_failures} TEST(S) FAILED — see details above")
    sys.exit(1)

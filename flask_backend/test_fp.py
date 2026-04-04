"""
False-positive regression test for MTN MoMo parser + authenticity engine.
Run from flask_backend/: python test_fp.py
"""
import sys
sys.path.insert(0, ".")
from services.sms_parser import parse_sms
from services.authenticity_engine import analyze_message

GENUINE_MSGS = [
    (
        "Payment made — full fields (GHS 1000)",
        """Payment made for GHS 1,000.00 to MARY AMA ANDOH.
Transaction ID: 12345678901
Reference: ABC123DEF456
Fee charged: GHS 2.50
TAX charged: GHS 5.00
Current Balance: GHS 500.00
Available Balance: GHS 495.00""",
    ),
    (
        "Payment received — full fields (GHS 31)",
        """Payment received for GHS 31.00 from MARY AGGREY (0241234567).
Transaction ID: 98765432101
Reference: GHX987DEF
Fee charged: GHS 0.00
TAX charged: GHS 0.00
Current Balance: GHS 250.00
Available Balance: GHS 250.00""",
    ),
    (
        "Payment made + MTN promo footer with click link",
        """Payment made for GHS 500.00 to JOHN MENSAH.
Transaction ID: 11223344556
Reference: REF789XYZ
Fee charged: GHS 1.00
TAX charged: GHS 2.50
Current Balance: GHS 1200.00
Available Balance: GHS 1195.00
Download the MTN MoMo app on Google Play or App Store. Click here: mtn.com.gh/momo""",
    ),
    (
        "Payment received + Current vs Available balance differ (normal)",
        """Payment received for GHS 200.00 from KWAME ASANTE (0244567890).
Transaction ID: 55667788990
Fee charged: GHS 0.00
TAX charged: GHS 0.00
Current Balance: GHS 1500.00
Available Balance: GHS 1480.00""",
    ),
    (
        "Classic transfer received (traditional format)",
        """You have received GHS 50.00 from JOHN DOE (0241234567).
Transaction ID: 12345678901. Your new balance is GHS 150.00.
Fee charged: GHS 0.00. Tax: GHS 0.00.""",
    ),
    (
        "Payment made — large amount",
        """Payment made for GHS 5,000.00 to ABENA MENSAH (0205551234).
Transaction ID: 90123456789
Reference: PAY20260403
Fee charged: GHS 10.00
TAX charged: GHS 25.00
Current Balance: GHS 2000.00
Available Balance: GHS 1980.00""",
    ),
]

SCAM_MSGS = [
    (
        "PIN + block + urgency scam",
        "You have received GHS 500 from SENDER. "
        "Your account will be blocked. Send back immediately. "
        "Enter your PIN to confirm.",
    ),
    (
        "Prize + customer care scam",
        "Dear Customer, you have won GHS 5000. "
        "Call our customer care to verify your account and release your funds.",
    ),
    (
        "Wrong-transfer reversal social engineering",
        "GHS 200 was sent in error. Kindly return to 0244000000. This is urgent.",
    ),
    (
        "Maintenance fee + reversal threat",
        "Your account has a maintenance fee. Failure to pay will result in reversal. "
        "Contact customer service immediately.",
    ),
]


def run():
    genuine_ok = 0
    scam_ok = 0
    any_failure = False

    print("=" * 60)
    print("GENUINE MESSAGES — all must classify as 'genuine'")
    print("=" * 60)
    for label, msg in GENUINE_MSGS:
        parsed = parse_sms(msg)
        result = analyze_message(msg, parsed)
        verdict = result["predicted_label"]
        text_risk = result["format_risk_score"]
        is_passing = verdict == "genuine"
        status = "PASS" if is_passing else "FAIL"
        print(f"  [{status}] {label}")
        print(f"         verdict={verdict}  text_risk={text_risk:.3f}")
        # Show parsed fields relevant to trust path
        tid = parsed.get("mtn_transaction_id")
        bal = parsed.get("balance_after")
        fee = parsed.get("fee")
        tax = parsed.get("tax")
        txn_type = parsed.get("transaction_type")
        direction = parsed.get("direction")
        print(f"         parsed: txn_id={tid} bal={bal} fee={fee} tax={tax} type={txn_type} dir={direction}")
        if not is_passing:
            print(f"         *** explanation: {result['explanation'][:200]}")
            any_failure = True
        else:
            genuine_ok += 1

    print()
    print("=" * 60)
    print("SCAM MESSAGES — all must NOT classify as 'genuine'")
    print("=" * 60)
    for label, msg in SCAM_MSGS:
        parsed = parse_sms(msg)
        result = analyze_message(msg, parsed)
        verdict = result["predicted_label"]
        text_risk = result["format_risk_score"]
        is_passing = verdict != "genuine"
        status = "PASS" if is_passing else "FAIL"
        print(f"  [{status}] {label}")
        print(f"         verdict={verdict}  text_risk={text_risk:.3f}")
        if not is_passing:
            any_failure = True
        else:
            scam_ok += 1

    print()
    print("=" * 60)
    total_genuine = len(GENUINE_MSGS)
    total_scam = len(SCAM_MSGS)
    print(f"Genuine pass rate: {genuine_ok}/{total_genuine}")
    print(f"Scam block rate:   {scam_ok}/{total_scam}")
    if not any_failure:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED — review above")
    return not any_failure


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)

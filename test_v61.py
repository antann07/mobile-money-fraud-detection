"""Quick validation of v6.1 authenticity engine against 5 reference messages."""
import sys
sys.path.insert(0, "flask_backend")
from services.authenticity_engine import analyze_message

tests = [
    ("Genuine1", 
     "Payment received for GHS 360.00 from SHIELLA ARTHUR Current Balance: GHS 2903.72 . Available Balance: GHS 2903.72. Reference: . Transaction ID: 78319906534. TRANSACTION FEE: 0.00",
     {"amount": 360.0, "balance_after": 2903.72, "available_balance": 2903.72, "mtn_transaction_id": "78319906534", "transaction_type": "payment", "direction": "incoming"},
     "genuine"),
    ("Genuine2",
     "Payment received for GHS 335.00 from VERONICA BOAKYE Current Balance: GHS 2553.72 . Available Balance: GHS 2553.72. Reference: 1. Transaction ID: 78302846773. TRANSACTION FEE: 0.00",
     {"amount": 335.0, "balance_after": 2553.72, "available_balance": 2553.72, "mtn_transaction_id": "78302846773", "transaction_type": "payment", "direction": "incoming"},
     "genuine"),
    ("Genuine3",
     "Cash In received for GHS 1500.00 from GLORIOUS GERSHON ENTERPRISE . Current Balance GHS 2218.72 Available Balance GHS 2218.72. Transaction ID: 78296092459. Fee charged: GHS 0. Cash in (Deposit) is a free transaction on MTN Mobile Money. Please do not pay any fees for it.",
     {"amount": 1500.0, "balance_after": 2218.72, "available_balance": 2218.72, "mtn_transaction_id": "78296092459", "transaction_type": "cash_in", "direction": "incoming"},
     "genuine"),
    ("Fraud1",
     "Cash receive for 505.00 from REBECCA APPIAH CHRIST THE KING MOBlLE MONEY ENTERPRISEOPPOSlTE DANSOMAN OVER HEAD ID-245236251",
     {"amount": 505.0, "transaction_type": "cash_in", "direction": "incoming"},
     "likely_fraudulent"),
    ("Fraud2",
     'Yello"Your MTN Acount has been B\'LOCK by the MTN for 3months 2week by Merchant Report don\'t attempt your pin THANK YOU',
     {"transaction_type": "unknown", "direction": "incoming"},
     "likely_fraudulent"),
]

all_pass = True
for name, raw, parsed, expected in tests:
    r = analyze_message(raw, parsed)
    label = r["predicted_label"]
    status = "PASS" if label == expected else "FAIL"
    if status == "FAIL":
        all_pass = False
    print(f"{status} {name}: {label}  conf={r['confidence_score']}  fmt={r['format_risk_score']}  struct={r['balance_consistency_score']}  behav={r['behavior_risk_score']}  sender={r['sender_novelty_score']}")

print(f"\nAll pass: {all_pass}")
print(f"Model version: {r['model_version']}")

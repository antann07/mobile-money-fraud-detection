"""
QA Regression Suite — Full Pre-Deployment Validation
=====================================================
Covers seven buckets:
  1. Genuine incoming alerts
  2. Fake / scam incoming alerts
  3. Outgoing / payment-made confirmations
  4. OCR vs SMS-paste consistency
  5. Malformed / edge-case incoming alerts
  6. Result-state (predicted_label + confidence) contract checks
  7. History & review-queue behaviour (logic / serialisation)

Run from flask_backend/:
    python qa_regression_full.py

Exit 0 = all pass.  Exit 1 = failures found.
"""

import sys
import json
import re

sys.path.insert(0, ".")

from services.sms_parser import parse_sms, is_in_scope
from services.authenticity_engine import analyze_message

# ─── Utilities ────────────────────────────────────────────────────────────────

PASS = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"
WARN = "\033[33m[WARN]\033[0m"

_failures: list[dict] = []
_passes: int = 0
_warns: int = 0


def _record(ok: bool, bucket: str, name: str, detail: str = ""):
    global _passes, _warns
    tag = PASS if ok else FAIL
    print(f"  {tag} [{bucket}] {name}")
    if detail:
        print(f"         {detail}")
    if ok:
        _passes += 1
    else:
        _failures.append({"bucket": bucket, "name": name, "detail": detail})


def check(
    bucket: str,
    name: str,
    text: str,
    expect_in_scope: bool,
    expect_label: str | None = None,
    expect_flags_any: list[str] | None = None,
    expect_flags_none: list[str] | None = None,
    input_method: str = "sms_paste",
    min_confidence: float = 0.0,
    max_confidence: float = 1.0,
    expect_direction: str | None = None,
    expect_type: str | None = None,
) -> bool:
    parsed = parse_sms(text)
    in_scope, reason = is_in_scope(parsed)
    result = None
    flags_flat = []

    # Direction / type assertions
    if expect_direction and parsed.get("direction") != expect_direction:
        _record(False, bucket, name,
                f"direction={parsed.get('direction')!r} expected={expect_direction!r}")
        return False

    if expect_type and parsed.get("transaction_type") != expect_type:
        _record(False, bucket, name,
                f"type={parsed.get('transaction_type')!r} expected={expect_type!r}")
        return False

    # Scope assertion
    if in_scope != expect_in_scope:
        _record(False, bucket, name,
                f"in_scope={in_scope} expected={expect_in_scope} reason={reason!r} "
                f"direction={parsed.get('direction')} type={parsed.get('transaction_type')}")
        return False

    # Label / flags checks
    if expect_label is not None or expect_flags_any or expect_flags_none or min_confidence > 0:
        if not in_scope:
            # Can't check engine output for OOS messages
            _record(True, bucket, name, f"out_of_scope (as expected)")
            return True

        result = analyze_message(text, parsed, None, input_method)
        label = result["predicted_label"]
        conf = result["confidence_score"]

        # Collect all flags from engine internals
        # (flags are surfaced via explanation; use the key sub-fields for checks)
        # We re-invoke internal scorer to get flags (not exposed in public API)
        from services.authenticity_engine import _score_text_authenticity
        _, text_flags = _score_text_authenticity(text, parsed, input_method)
        flags_flat = text_flags

        if expect_label and label != expect_label:
            _record(False, bucket, name,
                    f"label={label!r} expected={expect_label!r} conf={conf}")
            return False

        if not (min_confidence <= conf <= max_confidence):
            _record(False, bucket, name,
                    f"conf={conf} not in [{min_confidence},{max_confidence}] label={label}")
            return False

        if expect_flags_any:
            found = [f for f in expect_flags_any if any(f in fl for fl in flags_flat)]
            if not found:
                _record(False, bucket, name,
                        f"expected one of {expect_flags_any} in flags={flags_flat}")
                return False

        if expect_flags_none:
            bad = [f for f in expect_flags_none if any(f in fl for fl in flags_flat)]
            if bad:
                _record(False, bucket, name,
                        f"expected NONE of {bad} but found in flags={flags_flat}")
                return False

    label_note = ""
    if result:
        label_note = f"label={result['predicted_label']} conf={result['confidence_score']}"
    _record(True, bucket, name, label_note)
    return True


def section(title: str):
    print(f"\n{'='*64}")
    print(f"  {title}")
    print(f"{'='*64}")


# ════════════════════════════════════════════════════════════════════
# BUCKET 1 — GENUINE INCOMING ALERTS
# ════════════════════════════════════════════════════════════════════
section("BUCKET 1 — Genuine Incoming Alerts")

B1 = "B1:Genuine"

# Classic full-template transfer
check(B1, "Classic transfer (full fields)",
    "You have received GHS 50.00 from JOHN MENSAH (0241234567).\n"
    "Transaction ID: 78319906534. Your new balance is GHS 150.00.\n"
    "Fee charged: GHS 0.00. E-levy: GHS 0.00.",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.90)

# Payment received
check(B1, "Payment received (full fields)",
    "Payment received for GHS 120.00 from KWAME ASANTE (0271234567).\n"
    "Transaction ID: 55443322110. New Balance: GHS 450.00.\n"
    "Fee charged: GHS 0.00. Tax: GHS 1.50.",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.90)

# Cash-in / deposit
check(B1, "Cash In (ATM deposit)",
    "Cash In of GHS 200.00 has been credited to your account by AGENT ONE (0241001001).\n"
    "Transaction ID: 99887766554. New Balance: GHS 700.00.\n"
    "Fee charged: GHS 0.00.",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.80)

# Transfer with E-levy (>100 GHS, tax > 0)
check(B1, "Transfer >GHS100 with E-levy",
    "You have received GHS 500.00 from AKOSUA BOATENG (0261234567).\n"
    "Transaction ID: 11223344556. New Balance: GHS 1200.00.\n"
    "Fee charged: GHS 0.00. E-levy: GHS 2.50.",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.90)

# No E-levy on small transfer (< GHS 100)
check(B1, "Small transfer <GHS100 — no E-levy (correct)",
    "You have received GHS 50.00 from AMA OWUSU.\n"
    "Transaction ID: 44332211009. New Balance: GHS 200.00.\n"
    "Fee charged: GHS 0.00.",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.80)

# Transfer with TAX CHARGED format (alternative fee label)
check(B1, "Transfer with 'TAX charged' label (real MTN variant)",
    "You have received GHS 80.00 from PETER DARKO (0551234567).\n"
    "Transaction ID: 33221100998. New Balance: GHS 380.00.\n"
    "Fee charged: GHS 0.00. TAX charged: GHS 0.00.",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.80)

# Momo received (app-generated variant)
check(B1, "MoMo received app notification",
    "MoMo received GHS 75.00 from GRACE APPIAH (0244001122).\n"
    "Transaction ID: 87654321098. New Balance: GHS 175.00.\n"
    "Fee charged: GHS 0.00.",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.80)

# Transfer from (abbreviated format)
check(B1, "Transfer from NAME (short format)",
    "Transfer from KOFI MENSAH GHS 30.00.\n"
    "Transaction ID: 12345678901. New Balance: GHS 230.00.\n"
    "Fee charged: GHS 0.00.",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.70)

# Non-MTN format but all fields present (genuine-looking third-party alert)
check(B1, "Non-MTN opener with all transaction data — genuine",
    "Amount deposited: GHS 300.00 from DANIEL OWUSU (0231234567).\n"
    "Transaction ID: 99001122334. Available Balance: GHS 800.00.\n"
    "Fee charged: GHS 0.00. Tax: GHS 1.50.",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.80)

# "You've received" contraction
check(B1, "You've received (apostrophe contraction)",
    "You've received GHS 60.00 from EDWARD YEBOAH (0241231231).\n"
    "Transaction ID: 11001100110. New Balance: GHS 260.00.\n"
    "Fee charged: GHS 0.00.",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.80)


# ════════════════════════════════════════════════════════════════════
# BUCKET 2 — FAKE / SCAM INCOMING ALERTS
# ════════════════════════════════════════════════════════════════════
section("BUCKET 2 — Fake / Scam Incoming Alerts")

B2 = "B2:Scam"

# PIN harvesting
check(B2, "PIN-harvesting scam",
    "You have received GHS 500.00 from MTN GHANA HEAD OFFICE.\n"
    "Transaction ID: 55556666777. To verify receipt, enter your MoMo PIN to confirm.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["pin_request"])

# Reversal / wrong-transfer scam
check(B2, "Wrong transfer reversal scam",
    "You have received GHS 800.00 from MERCY AMPONSAH (0271234567). "
    "I sent this in error. Kindly return it. Your account will be "
    "blocked if you fail to return. Contact: 0271234567.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["suspicious_phrase:kindly return"])

# Homoglyph attack (MOBlLE MONEY)
check(B2, "Homoglyph attack (MOBlLE MONEY)",
    "Cash receive for 505.00 from REBECCA APPIAH CHRIST THE KING "
    "MOBlLE MONEY ENTERPRISEOPPOSlTE DANSOMAN OVER HEAD ID-245236251",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["homoglyph_suspect"])

# Callback-phone-number scam
check(B2, "Callback phone number instruction",
    "You received GHS 1000.00 from MTN Head Office. "
    "Call 0244001122 to activate your payment.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["suspicious_phrase:call_phone_number"])

# Congratulations prize scam
check(B2, "Congratulations / lottery prize scam",
    "Congratulations! You have won GHS 5000.00. "
    "You have received GHS 5000.00. "
    "Call customer care 0277123456 to claim your prize.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["suspicious_phrase:congratulations"])

# Dear customer greeting
check(B2, "Dear customer greeting (non-MTN)",
    "Dear Customer, GHS 200.00 has been deposited into your account. "
    "Reference: XY123456. Call our verification helpline 0244567890.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["suspicious_phrase:dear customer"])

# Account suspension threat
check(B2, "Account suspension threat + urgency",
    "You have received GHS 750.00. Your account will be blocked immediately "
    "if you do not call 0261234567. Failure to respond will result in reversal.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["urgency"])

# "Do not spend" scam instruction
check(B2, "Do-not-spend scam (fake receipt + instruction)",
    "You have received GHS 240.00 from JOHN DOE. "
    "Do not spend before calling 0244999888 to verify the transaction.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["suspicious_phrase:do not spend"])

# "Please return" / "accidentally sent"
check(B2, "Accidentally-sent return-demand scam",
    "GHS 400.00 has been transferred to your account from ISAAC BOATENG. "
    "I accidentally sent this. Please return via 0271234567 immediately.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["suspicious_phrase:accidentally sent"])

# Will-be-reversed threat
check(B2, "Will-be-reversed threat language",
    "You received GHS 300.00 from ABENA MENSAH. "
    "This transfer will be reversed if not returned within 24 hours. "
    "Call MTN head office: 0553219876.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["urgency:will be reversed"])

# System-upgrade fee-collection scam (no real amount received)
check(B2, "System upgrade / maintenance fee scam",
    "Dear valued customer, your account is flagged for a system upgrade. "
    "A maintenance fee of GHS 10.00 has been deducted. "
    "Call customer service 0241234567 to reverse the transaction.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["suspicious_phrase:system upgrade"])

# Scam with no balance, no txn ID (typical bare scam)
check(B2, "Bare scam — no balance, no txn ID",
    "GHS 500.00 has been deposited to your MoMo account. "
    "Contact us immediately at 0244998877 to verify and claim.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["suspicious_phrase"])

# OCR-tolerant scam phrase (regex path: OCR garbled 'kindly return')
check(B2, "OCR-tolerant 'k1ndly r3turn' phrase",
    "You have received GHS 300.00. K1ndly r3turn to 0241234567.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["suspicious_phrase:kindly return"],
    input_method="sms_paste")

# Mistaken transfer with reversal threat (compound scam)
check(B2, "Mistaken transfer + reversal threat (compound)",
    "GHS 600.00 was transferred to your account. "
    "This was mistaken transfer. The amount will be reversed if not returned. "
    "Send back via 0244001122 urgently.",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_flags_any=["suspicious_phrase:wrong transfer", "suspicious_phrase:send back"])


# ════════════════════════════════════════════════════════════════════
# BUCKET 3 — OUTGOING / PAYMENT-MADE (must be OUT-OF-SCOPE)
# ════════════════════════════════════════════════════════════════════
section("BUCKET 3 — Outgoing / Payment-Made (out-of-scope)")

B3 = "B3:Outgoing"

check(B3, "Payment made for (classic outgoing)",
    "Payment made for GHS 120.00 to ABENA DARKO (0241234567).\n"
    "Transaction ID: 12345678901. Fee charged: GHS 2.00.\n"
    "Current Balance: GHS 500.00.",
    expect_in_scope=False, expect_direction="outgoing")

check(B3, "You have sent (peer transfer out)",
    "You have sent GHS 200.00 to KWAME BOATENG (0261234567).\n"
    "Transaction ID: 33221100. New Balance: GHS 800.00.",
    expect_in_scope=False, expect_direction="outgoing")

check(B3, "Cash Out withdrawal",
    "Cash Out of GHS 100.00 processed.\n"
    "Transaction ID: 11223344. New Balance: GHS 600.00.",
    expect_in_scope=False, expect_direction="outgoing")

check(B3, "Airtime top-up",
    "Airtime top-up of GHS 10.00 for 0244123456 was successful.\n"
    "Transaction ID: 99887766. Balance: GHS 240.00.",
    expect_in_scope=False, expect_direction="outgoing")

check(B3, "Bill payment",
    "Bill payment of GHS 50.00 to ECG was successful.\n"
    "Transaction ID: 77665544. Balance: GHS 190.00.",
    expect_in_scope=False, expect_direction="outgoing")

check(B3, "Merchant payment debit",
    "Merchant payment of GHS 85.00 to SHOPRITE GHANA.\n"
    "Transaction ID: 55443322. New Balance: GHS 415.00.",
    expect_in_scope=False, expect_direction="outgoing")

check(B3, "You withdrew (withdrawal verb)",
    "You have withdrawn GHS 300.00 from your MoMo wallet.\n"
    "Transaction ID: 87654321. New Balance: GHS 700.00.",
    expect_in_scope=False, expect_direction="outgoing")

check(B3, "Genuine outgoing: transferred to your savings (not in-scope)",
    "You have transferred GHS 200.00 to your savings account.\n"
    "Transaction ID: 44556677. New Balance: GHS 1300.00.",
    expect_in_scope=False)

check(B3, "Genuine outgoing: Payment to NAME",
    "You have paid GHS 45.00 to KOFI ASANTE.\n"
    "Transaction ID: 67890. Balance: GHS 350.00.",
    expect_in_scope=False, expect_direction="outgoing")

# Scam upgrade: outgoing verb + social-engineering language → still IN-SCOPE
check(B3, "Scam outgoing phrasing 'I sent by mistake' → UPGRADES to in-scope",
    "I sent you GHS 800 by mistake. Kindly return it immediately "
    "or your account will be blocked. Call 0244999888.",
    expect_in_scope=True,  # social-engineering overrides outgoing label
    expect_label="likely_fraudulent")

# Genuine outgoing with no social signal — must stay OUT
check(B3, "Genuine sent — no scam signal — stays out-of-scope",
    "You have sent GHS 50.00 to AMA MENSAH (0241112233).\n"
    "New Balance: GHS 950.00.",
    expect_in_scope=False)


# ════════════════════════════════════════════════════════════════════
# BUCKET 4 — OCR PATH vs SMS-PASTE CONSISTENCY
# ════════════════════════════════════════════════════════════════════
section("BUCKET 4 — OCR vs SMS-Paste Consistency")

B4 = "B4:OCR"

# For each case: run both as sms_paste and screenshot_ocr,
# assert the label is consistent (same bucket direction).

_ocr_pairs = [
    (
        "Genuine transfer — OCR vs paste",
        "You have received GHS 50.00 from JOHN MENSAH (0241234567).\n"
        "Transaction ID: 78319906534. Your new balance is GHS 150.00.\n"
        "Fee charged: GHS 0.00. E-levy: GHS 0.00.",
        "genuine",
    ),
    (
        "PIN-harvesting scam — OCR vs paste",
        "You have received GHS 500.00 from MTN HEAD OFFICE. "
        "Enter your MoMo PIN to confirm.",
        "likely_fraudulent",
    ),
    (
        "Wrong-transfer reversal scam — OCR vs paste",
        "You have received GHS 800.00 from MERCY AMPONSAH. "
        "Kindly return it. Call 0271234567.",
        "likely_fraudulent",
    ),
]

for name, text, expected_label in _ocr_pairs:
    parsed = parse_sms(text)
    in_scope, _ = is_in_scope(parsed)
    if not in_scope:
        _record(False, B4, name, "unexpectedly out-of-scope for OCR consistency test")
        continue

    res_paste = analyze_message(text, parsed, None, "sms_paste")
    res_ocr   = analyze_message(text, parsed, None, "screenshot_ocr")

    paste_label = res_paste["predicted_label"]
    ocr_label   = res_ocr["predicted_label"]

    # Both must agree on fraud direction (genuine vs non-genuine)
    paste_is_genuine = (paste_label == "genuine")
    ocr_is_genuine   = (ocr_label == "genuine")

    if paste_is_genuine != ocr_is_genuine:
        _record(False, B4, name,
                f"INCONSISTENCY paste={paste_label} ocr={ocr_label}")
    elif paste_label != expected_label:
        _record(False, B4, name,
                f"paste={paste_label!r} expected={expected_label!r}")
    else:
        _record(True, B4, name,
                f"paste={paste_label} ocr={ocr_label} (consistent)")

# OCR with extra status-bar noise (status bar text prepended)
_ocr_noise = (
    "14:35  ▶ 4G  ■■■\n"
    "MTN MoMo\n"
    "You have received GHS 50.00 from JOHN MENSAH (0241234567).\n"
    "Transaction ID: 78319906534. Your new balance is GHS 150.00.\n"
    "Fee charged: GHS 0.00."
)
parsed = parse_sms(_ocr_noise)
in_scope, _ = is_in_scope(parsed)
if in_scope:
    res = analyze_message(_ocr_noise, parsed, None, "screenshot_ocr")
    ok = res["predicted_label"] == "genuine"
    _record(ok, B4, "OCR with phone status-bar noise — still genuine",
            f"label={res['predicted_label']} conf={res['confidence_score']}")
else:
    _record(False, B4, "OCR with phone status-bar noise — should be in-scope",
            f"direction={parsed.get('direction')}")

# OCR where Tesseract produces mixed-case (homoglyph-like)
# Real message, not a scam — OCR engine should NOT flag as homoglyph
_ocr_case_noise = (
    "You have received GHs 50.00 from jOHN MENSAH (0241234567).\n"
    "Transaction lD: 78319906534. Your new balance is GHS 150.00.\n"
    "Fee charged: GHS 0.00."
)
check(B4, "OCR mixed-case artefact — homoglyphs skipped for screenshot_ocr",
    _ocr_case_noise,
    expect_in_scope=True,
    expect_label="genuine",
    input_method="screenshot_ocr",
    expect_flags_none=["homoglyph_suspect"])

# OCR scam — hard scam phrase survives screenshot_ocr noise suppression
check(B4, "OCR scam — hard phrase not suppressed by screenshot noise gate",
    "You have received GHS 500. Enter your MOMO PIN to confirm.\n"
    "Transaction ID: 78319906534. Balance: GHS 150.00.",
    expect_in_scope=True,
    expect_label="likely_fraudulent",
    expect_flags_any=["pin_request"],
    input_method="screenshot_ocr")


# ════════════════════════════════════════════════════════════════════
# BUCKET 5 — MALFORMED / EDGE-CASE INCOMING ALERTS
# ════════════════════════════════════════════════════════════════════
section("BUCKET 5 — Malformed / Edge-Case Incoming Alerts")

B5 = "B5:EdgeCase"

# Empty string
empty_parsed = parse_sms("")
b5_empty_scope, _ = is_in_scope(empty_parsed)
_record(not b5_empty_scope, B5, "Empty string — out-of-scope",
        f"in_scope={b5_empty_scope}")

# Whitespace only
ws_parsed = parse_sms("   \n\t  ")
ws_scope, _ = is_in_scope(ws_parsed)
_record(not ws_scope, B5, "Whitespace-only — out-of-scope",
        f"in_scope={ws_scope}")

# Very short text (< 30 chars but has 'received')
check(B5, "Too short to be a real notification",
    "You received GHS 5.",
    expect_in_scope=True,
    expect_label="suspicious")  # short + missing TxnID/balance/fee

# GHC instead of GHS (wrong currency code)
check(B5, "Wrong currency code GHC",
    "You have received GHC 100.00 from JAMES ASANTE (0241234567).\n"
    "Transaction ID: 33221100998. New Balance: GHC 300.00.\n"
    "Fee charged: GHC 0.00.",
    expect_in_scope=True,
    expect_label="suspicious",
    expect_flags_any=["tmpl:wrong_currency"])

# Balance < amount (structural inconsistency)
check(B5, "Balance < amount — structural inconsistency",
    "You have received GHS 500.00 from KWAME ASANTE (0261001001).\n"
    "Transaction ID: 11223344556. New Balance: GHS 50.00.\n"
    "Fee charged: GHS 0.00.",
    expect_in_scope=True,
    expect_flags_any=["balance_less_than_amount"])

# Fee/E-levy in wrong order (E-levy before Fee)
check(B5, "Field ordering: E-levy before Fee (wrong_field_order)",
    "You have received GHS 150.00 from AMA BOATENG (0241234567).\n"
    "Transaction ID: 99887766554. New Balance: GHS 650.00.\n"
    "E-levy: GHS 0.75. Fee charged: GHS 0.00.",
    expect_in_scope=True,
    expect_flags_any=["tmpl:wrong_field_order"])

# Unexpected Ref: field
check(B5, "Unexpected Ref: field",
    "You have received GHS 80.00 from PETER DARKO.\n"
    "Transaction ID: 55443322110. New Balance: GHS 280.00.\n"
    "Ref: XY009988 Fee charged: GHS 0.00.",
    expect_in_scope=True,
    expect_flags_any=["tmpl:unexpected_ref_field"])

# All-same-digit txn ID (fabricated)
check(B5, "Fabricated all-same-digit Transaction ID",
    "You have received GHS 200.00 from MARY QUAYE (0241001122).\n"
    "Transaction ID: 1111111111. New Balance: GHS 700.00.\n"
    "Fee charged: GHS 0.00.",
    expect_in_scope=True,
    expect_flags_any=["fabricated_txn_id"])

# No amount (amount=None from parser)
check(B5, "No GHS amount in message",
    "You have received money from AKOSUA MENSAH.\n"
    "Transaction ID: 55443322110. New Balance: GHS 550.00.\n"
    "Fee charged: GHS 0.00.",
    expect_in_scope=True)

# Amount with comma-separators (GHS 1,500.00)
check(B5, "Comma-formatted large amount GHS 1,500.00",
    "You have received GHS 1,500.00 from KOFI BOAFO (0261234567).\n"
    "Transaction ID: 44332211009. New Balance: GHS 5,200.00.\n"
    "Fee charged: GHS 0.00. E-levy: GHS 7.50.",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.80)

# Zero-width char injection (copy-paste artefact)
check(B5, "Zero-width char (copy-paste artefact) — genuine not penalised",
    "You\u200b have received GHS 50.00 from JOHN MENSAH (0241234567).\n"
    "Transaction ID: 78319906534. New Balance: GHS 150.00.\n"
    "Fee charged: GHS 0.00.",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.80)

# Bad-grammar "cash receive" (Phase 4 regression)
check(B5, "Bad-grammar 'cash receive' — in-scope and flagged fraudulent",
    "Cash receive for 505.00 from REBECCA APPIAH CHRIST THE KING "
    "MOBlLE MONEY ENTERPRISEOPPOSlTE DANSOMAN OVER HEAD ID-245236251",
    expect_in_scope=True, expect_label="likely_fraudulent",
    expect_direction="incoming")

# 'GHS X from NAME' (no verb — _INCOMING_CLAIM_RE fallback)
check(B5, "GHS amount + 'from' — _INCOMING_CLAIM_RE fallback",
    "GHS 505.00 from REBECCA APPIAH CHRIST THE KING",
    expect_in_scope=True)

# Known misspelling: "recieved"
check(B5, "Known misspelling: recieved",
    "You have recieved GHS 50.00 from JOHN MENSAH.\n"
    "Transaction ID: 78319906534. New Balance: GHS 150.00.\n"
    "Fee charged: GHS 0.00.",
    expect_in_scope=True,
    expect_flags_any=["tmpl:misspelling:recieved"])

# Deposited (past-tense — was an earlier bug)
check(B5, "Deposited past tense — in-scope",
    "GHS 500.00 has been deposited into your account. "
    "Call 0244000000 to verify your identity.",
    expect_in_scope=True, expect_direction="incoming")

# Message with only whitespace noise + genuine content
check(B5, "Leading whitespace and trailing newlines",
    "\n  \n  You have received GHS 50.00 from JOHN MENSAH (0241234567).\n"
    "Transaction ID: 78319906534. New Balance: GHS 150.00.\n"
    "Fee charged: GHS 0.00.  \n",
    expect_in_scope=True, expect_label="genuine", min_confidence=0.80)


# ════════════════════════════════════════════════════════════════════
# BUCKET 6 — RESULT-STATE CONTRACT CHECKS
# ════════════════════════════════════════════════════════════════════
section("BUCKET 6 — Result-State / Label Contract")

B6 = "B6:Contract"

# All expected keys present in the result dict
_canonical_keys = {
    "predicted_label", "confidence_score", "explanation",
    "format_risk_score", "behavior_risk_score",
    "balance_consistency_score", "sender_novelty_score", "model_version",
}

_contract_cases = [
    ("Genuine", "You have received GHS 50.00 from JOHN MENSAH (0241234567).\n"
                "Transaction ID: 78319906534. New Balance: GHS 150.00.\n"
                "Fee charged: GHS 0.00."),
    ("Scam",    "You have received GHS 500.00 from MTN HEAD OFFICE. "
                "Enter your MoMo PIN to confirm."),
    ("OOS",     "You have sent GHS 50.00 to AMA MENSAH. New Balance: GHS 900.00."),
]

for name, text in _contract_cases:
    parsed = parse_sms(text)
    in_scope, reason = is_in_scope(parsed)
    if in_scope:
        r = analyze_message(text, parsed, None, "sms_paste")
    else:
        from services.message_check_service import _build_out_of_scope_result
        r = _build_out_of_scope_result(parsed, reason)

    missing = _canonical_keys - set(r.keys())
    ok = len(missing) == 0
    _record(ok, B6, f"All contract keys present — {name}",
            f"missing={missing}" if missing else "")

# predicted_label is always one of the 4 valid values
_valid_labels = {"genuine", "suspicious", "likely_fraudulent", "out_of_scope"}

_label_cases = [
    ("genuine", "You have received GHS 50.00 from JOHN MENSAH (0241234567).\n"
                "Transaction ID: 78319906534. New Balance: GHS 150.00.\nFee charged: GHS 0.00."),
    ("suspicious", "You have received GHS 50.00. No balance shown.\n"
                   "Transaction ID: 55443322110."),
    ("likely_fraudulent",  "You have received GHS 500.00 from MTN HEAD OFFICE. "
                           "Enter your MoMo PIN NOW."),
    ("out_of_scope", "Cash Out of GHS 100.00 processed. Balance: GHS 600.00."),
]

for expected_label, text in _label_cases:
    parsed = parse_sms(text)
    in_scope, reason = is_in_scope(parsed)
    if in_scope:
        r = analyze_message(text, parsed, None, "sms_paste")
        label = r["predicted_label"]
    else:
        from services.message_check_service import _build_out_of_scope_result
        r = _build_out_of_scope_result(parsed, reason)
        label = r["predicted_label"]

    ok = label in _valid_labels
    ok2 = (label == expected_label)
    _record(ok and ok2, B6, f"Label is valid and correct — {expected_label}",
            f"got={label!r}" if not ok2 else "")

# confidence_score in [0.0, 1.0]
check(B6, "Confidence always in [0.0, 1.0] — genuine",
    "You have received GHS 50.00 from JOHN MENSAH (0241234567).\n"
    "Transaction ID: 78319906534. New Balance: GHS 150.00.\nFee charged: GHS 0.00.",
    expect_in_scope=True, min_confidence=0.0, max_confidence=1.0)

check(B6, "Confidence always in [0.0, 1.0] — scam",
    "You received GHS 1000.00. Call 0244001122. Enter your MoMo PIN.",
    expect_in_scope=True, min_confidence=0.0, max_confidence=1.0)

# model_version always starts with "v"
_mv_text = ("You have received GHS 50.00 from JOHN MENSAH (0241234567).\n"
            "Transaction ID: 78319906534. New Balance: GHS 150.00.\nFee charged: GHS 0.00.")
_mv_parsed = parse_sms(_mv_text)
_mv_result = analyze_message(_mv_text, _mv_parsed, None, "sms_paste")
_record(_mv_result["model_version"].startswith("v"), B6,
        "model_version starts with 'v'",
        f"got={_mv_result['model_version']!r}")

# explanation is a non-empty string for every label
_exp_cases = [
    ("Explanation non-empty — genuine",
     "You have received GHS 50.00 from JOHN MENSAH (0241234567).\n"
     "Transaction ID: 78319906534. New Balance: GHS 150.00.\nFee charged: GHS 0.00."),
    ("Explanation non-empty — scam",
     "You received GHS 500. Call 0244001122 immediately. Enter your MoMo PIN."),
]
for name, text in _exp_cases:
    parsed = parse_sms(text)
    in_scope, _ = is_in_scope(parsed)
    if in_scope:
        r = analyze_message(text, parsed, None, "sms_paste")
        ok = bool(r.get("explanation", "").strip())
        _record(ok, B6, name, f"explanation empty!" if not ok else "")


# ════════════════════════════════════════════════════════════════════
# BUCKET 7 — HISTORY & REVIEW-QUEUE BEHAVIOUR (logic / serialisation)
# ════════════════════════════════════════════════════════════════════
section("BUCKET 7 — History & Review-Queue Logic")

B7 = "B7:History"

from services.message_check_service import (
    _LABEL_TO_STATUS,
    _build_out_of_scope_result,
    _serialize_prediction,
)

# Label → status mapping
_expected_status = {
    "genuine":           "verified",
    "suspicious":        "flagged",
    "likely_fraudulent": "flagged",
    "out_of_scope":      "out_of_scope",
}
for label, expected in _expected_status.items():
    got = _LABEL_TO_STATUS.get(label)
    _record(got == expected, B7, f"Label→status map: {label} → {expected}",
            f"got={got!r}" if got != expected else "")

# _build_out_of_scope_result includes 'scope_reason' key
_oos_text = "Cash Out of GHS 100.00 processed. Balance: GHS 600.00."
_oos_parsed = parse_sms(_oos_text)
_, _oos_reason = is_in_scope(_oos_parsed)
_oos_result = _build_out_of_scope_result(_oos_parsed, _oos_reason)
_record("scope_reason" in _oos_result, B7, "OOS result has scope_reason key",
        f"keys={list(_oos_result.keys())}")

# _serialize_prediction preserves all 4 score keys
_ser = _serialize_prediction(_oos_result)
_score_keys = ["format_risk_score", "behavior_risk_score",
               "balance_consistency_score", "sender_novelty_score"]
_missing_ser = [k for k in _score_keys if k not in _ser]
_record(not _missing_ser, B7, "_serialize_prediction preserves score keys",
        f"missing={_missing_ser}" if _missing_ser else "")

# OOS result predicted_label must be "out_of_scope"
_record(_oos_result["predicted_label"] == "out_of_scope", B7,
        "OOS result label = 'out_of_scope'",
        f"got={_oos_result['predicted_label']!r}")

# Genuine result has confidence > 0.50
_gen_text = ("You have received GHS 50.00 from JOHN MENSAH (0241234567).\n"
             "Transaction ID: 78319906534. New Balance: GHS 150.00.\nFee charged: GHS 0.00.")
_gen_parsed = parse_sms(_gen_text)
_gen_result = analyze_message(_gen_text, _gen_parsed, None, "sms_paste")
_record(_gen_result["confidence_score"] > 0.50, B7,
        "Genuine result confidence > 0.50",
        f"conf={_gen_result['confidence_score']}")

# Fraudulent result has confidence > 0.50
_fraud_text = ("You received GHS 1000. Call 0244001122. Enter your MoMo PIN.")
_fraud_parsed = parse_sms(_fraud_text)
_fraud_result = analyze_message(_fraud_text, _fraud_parsed, None, "sms_paste")
_record(_fraud_result["confidence_score"] > 0.50, B7,
        "Fraudulent result confidence > 0.50",
        f"conf={_fraud_result['confidence_score']}")

# Verify verdictUtils labels cover all 4 labels (static check on known values)
_vu_labels = {"genuine", "suspicious", "likely_fraudulent", "out_of_scope"}
for lbl in _vu_labels:
    # This is a logic/contract check — the Python engine must emit these exact strings
    _record(lbl in _LABEL_TO_STATUS or lbl == "out_of_scope", B7,
            f"verdictUtils label '{lbl}' is a known engine output")


# ════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ════════════════════════════════════════════════════════════════════

total = _passes + len(_failures)
print(f"\n{'='*64}")
print(f"  RESULTS: {_passes}/{total} passed, {len(_failures)} failed")
print(f"{'='*64}")

if _failures:
    print(f"\n\033[31mFAILURES:\033[0m")
    for i, f in enumerate(_failures, 1):
        print(f"  {i:2d}. [{f['bucket']}] {f['name']}")
        if f['detail']:
            print(f"       {f['detail']}")
    sys.exit(1)
else:
    print("\n\033[32m  ALL TESTS PASSED\033[0m")
    sys.exit(0)

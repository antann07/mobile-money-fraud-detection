"""
SMS Parser — rule-based extraction of fields from MTN MoMo SMS messages.

Scope (v2+):
  The fraud detection model covers INCOMING money alerts only.
  Outgoing transactions (payment made, cash-out, airtime purchase, bill
  payment) are recorded but skipped by the fraud classifier — those
  message types are not the target fraud problem.

  Use `is_in_scope(parsed)` after `parse_sms()` to decide whether to run
  analysis.

IN-SCOPE (fraud model applies):
  - Transfer received / Payment received
  - Cash-in / Deposit / Cash received

OUT-OF-SCOPE (saved, not analysed):
  - Payment made / Payment to / Cash-out
  - Airtime purchase
  - Bill payment / merchant debit

Each MTN MoMo SMS follows predictable patterns like:
  "You have received GHS 50.00 from JOHN DOE (0241234567).
   Transaction ID: 123456789. Your new balance is GHS 150.00.
   Fee charged: GHS 0.00. Tax: GHS 0.00."

This parser uses regex rules to pull out structured fields.

Returns:
  A dict with extracted fields + parser_confidence (0.0–1.0).
"""

import re


# ═══════════════════════════════════════════════
# Regex patterns for MTN Ghana MoMo SMS formats
# ═══════════════════════════════════════════════

# Amount pattern: matches GHS followed by a number (e.g. GHS 50.00, GHS50.00, GHS 1,000.00)
_AMOUNT_RE = re.compile(
    r"GHS\s?([\d,]+\.?\d*)", re.IGNORECASE
)

# Transaction ID: MTN internal ID (numeric, typically 10+ digits)
_TXN_ID_RE = re.compile(
    r"(?:Transaction\s*(?:ID|Id|id)|Trans(?:action)?\s*#|TxnId|Txn\s*ID)[:\s]*(\d{6,})",
    re.IGNORECASE,
)

# Reference code: alphanumeric reference
_REF_RE = re.compile(
    r"(?:Ref(?:erence)?|ref)[:\s]*([A-Za-z0-9]+)",
    re.IGNORECASE,
)

# Phone number: Ghana format 0XX XXXX XXX or 0XXXXXXXXX or +233XXXXXXXXX
_PHONE_RE = re.compile(
    r"(?:\+233|0)([2-5]\d{8})",
)

# Name pattern: words in UPPERCASE or Title Case near "from" / "to"
#
# Terminator alternatives (in order of preference):
#   \s*[\(\.,]   — opening paren, period, or comma immediately after name
#   \s*Trans     — "Transaction ID" or "Transfer"
#   \s*Fee       — "Fee charged"
#   \s*Tax       — "Tax:" or "Tax charged"
#   \s*Your\b    — "Your new balance is..."
#   \s*Bal       — "Balance:" or "Balance is"
#   \s*Avail     — "Available balance"
#   \s+\d        — phone number or amount following with at least one space
#                  (digit isn't in the name char class, so lazy-match stops here
#                   but we also need the lookahead to succeed at that position)
#   \s*[\r\n]    — newline (copy-pasted text often loses periods)
#   \s*$         — end of string
#
# Length cap {1,60}? prevents catastrophic backtracking on malformed text
# while still covering long names like "AKOSUA BOATEMAA KYEREMANTENG".
_NAME_FROM_RE = re.compile(
    r"from\s+([A-Z][A-Za-z\s.'-]{1,60}?)"
    r"(?:"
    r"\s*[\(\.,]"       # ( or . or ,
    r"|\s*Trans"        # Transaction / Transfer
    r"|\s*Fee"          # Fee charged
    r"|\s*Tax"          # Tax
    r"|\s*Your\b"       # "Your new balance"
    r"|\s*Bal"          # Balance / Bal:
    r"|\s*Avail"        # Available balance
    r"|\s+\d"           # space(s) + digit (phone / amount follows the name)
    r"|\s+to\b"         # "from NAME to RECIPIENT" — stop before recipient
    r"|\s*[\r\n]"       # newline
    r"|\s*$"            # end of string
    r")",
    re.IGNORECASE,
)

_NAME_TO_RE = re.compile(
    r"to\s+([A-Z][A-Za-z\s.'-]{1,60}?)"
    r"(?:"
    r"\s*[\(\.,]"
    r"|\s*Trans"
    r"|\s*Fee"
    r"|\s*Tax"
    r"|\s*Your\b"
    r"|\s*Bal"
    r"|\s*Avail"
    r"|\s+\d"
    r"|\s+from\b"       # "to NAME from SENDER" — stop before sender clause
    r"|\s*[\r\n]"
    r"|\s*$"
    r")",
    re.IGNORECASE,
)

# Date/time: common MTN formats like "25/03/2026 14:30" or "2026-03-25 14:30:00"
_DATETIME_RE = re.compile(
    r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}[\s,]*\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)",
)

# Balance: "balance is GHS xxx", "new balance: GHS xxx", or "Current Balance: GHS xxx"
_BALANCE_RE = re.compile(
    r"(?:(?:current|new)\s+)?balance\s*(?:is|:)\s*GHS\s?([\d,]+\.?\d*)",
    re.IGNORECASE,
)

_AVAIL_BALANCE_RE = re.compile(
    r"available\s+balance\s*(?:is|:)\s*GHS\s?([\d,]+\.?\d*)",
    re.IGNORECASE,
)

# Fee: "Fee charged: GHS x.xx" or "Fee: GHS x.xx"
_FEE_RE = re.compile(
    r"(?:Fee\s*(?:charged)?)[:\s]*GHS\s?([\d,]+\.?\d*)",
    re.IGNORECASE,
)

# Tax: "Tax: GHS x.xx", "Tax charged: GHS x.xx", "TAX charged: GHS x.xx", or "E-levy: GHS x.xx"
# Note: "TAX charged: GHS" has the word "charged" between Tax and the colon —
# the (?:\s+charged)? group handles that.
_TAX_RE = re.compile(
    r"(?:Tax(?:\s+charged)?|E-?levy)[:\s]*GHS\s?([\d,]+\.?\d*)",
    re.IGNORECASE,
)


# ═══════════════════════════════════════════════
# Transaction type detection keywords
# ═══════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# Direction detection rules
# ═══════════════════════════════════════════════════════════════════
#
# A single ordered list of (compiled_regex, transaction_type, direction).
# _detect_type_and_direction() walks the list and returns on the FIRST match.
#
# Priority scheme (four groups evaluated top-to-bottom):
#
#   GROUP 1 — Unambiguous OUTGOING phrases.
#     Specific multi-word or subject-verb constructs that NEVER appear in a
#     genuine incoming credit alert.  Word boundaries (\b) prevent matching
#     inside longer words (e.g. \bpaid\b won't match "prepaid").
#
#   GROUP 2 — Unambiguous INCOMING phrases.
#     "payment received", "cash in/cash-in", "sent to you", explicit
#     "you have received" — all uniquely incoming.
#
#   GROUP 3 — Generic INCOMING single-word signals.
#     "received", "credited", "deposit" — checked BEFORE generic outgoing
#     verbs so scam texts that mix "received" with "sent by mistake" resolve
#     correctly as incoming instead of outgoing.
#
#   GROUP 4 — Generic OUTGOING verbs (last resort).
#     "transferred", "sent", "paid" — only reached after all incoming
#     checks fail.  Using \b stops "paid" matching "prepaid", "sent"
#     matching in "consented", etc.
#
_DIRECTION_RULES: list[tuple[re.Pattern, str, str]] = [

    # ── GROUP 1: Unambiguous outgoing ───────────────────────────────────
    # Subject + verb constructs: "you (have) sent/transferred/paid/withdrawn"
    (re.compile(r"\byou\s+(?:have\s+)?(?:sent|transferred|paid|withdrawn|withdrew)\b", re.I),
     "transfer", "outgoing"),
    # "payment made" / "payment made for" / "payment to"
    (re.compile(r"\bpayment\s+(?:made(?:\s+for)?|to)\b", re.I),
     "payment", "outgoing"),
    # Cash-out / cash withdrawal
    (re.compile(r"\bcash[- ]out\b", re.I),
     "withdrawal", "outgoing"),
    # Explicit withdrawal / debit language
    (re.compile(r"\b(?:withdrawn|debited)\b", re.I),
     "withdrawal", "outgoing"),
    # Airtime, top-up, recharge (all outgoing purchases)
    (re.compile(r"\b(?:airtime|top[- ]up|recharge)\b", re.I),
     "airtime", "outgoing"),
    # Bill payment / utility payment
    (re.compile(r"\bbill\s+payment\b", re.I),
     "bill", "outgoing"),
    # Merchant payment / merchant debit
    (re.compile(r"\bmerchant\s+(?:payment|debit)\b", re.I),
     "payment", "outgoing"),

    # ── GROUP 2: Unambiguous incoming ───────────────────────────────────
    # "payment received" — before the generic "received" pattern below
    (re.compile(r"\bpayment\s+received\b", re.I),
     "payment", "incoming"),
    # "cash in" / "cash-in" / "cash received"
    (re.compile(r"\bcash[- ]in\b", re.I),
     "deposit", "incoming"),
    (re.compile(r"\bcash\s+received\b", re.I),
     "deposit", "incoming"),
    # "sent to you" — peer sent money to this wallet
    (re.compile(r"\bsent\s+to\s+you\b", re.I),
     "transfer", "incoming"),
    # "transfer received"
    (re.compile(r"\btransfer\s+received\b", re.I),
     "transfer", "incoming"),
    # "momo received" — app-generated variant
    (re.compile(r"\bmomo\s+received\b", re.I),
     "transfer", "incoming"),
    # Explicit subject: "you (have/'ve) received"
    (re.compile(r"\byou(?:'ve|\s+have)?\s+received\b", re.I),
     "transfer", "incoming"),
    # "transferred to your account/wallet/momo" — incoming despite the word
    # "transferred".  Placed in Group 2 so it takes priority over the generic
    # \btransferred\b outgoing catcher in Group 4.
    (re.compile(r"\btransferred\s+to\s+your\b", re.I),
     "transfer", "incoming"),
    # "to your account / wallet / momo / number" — any phrase directing money
    # at the user's own wallet is an incoming-credit claim regardless of verb.
    # Group 1's "you + VERB" patterns take priority for genuine outgoing
    # confirmations (e.g. "You transferred X to your account").
    (re.compile(r"\bto\s+your\s+(?:account|wallet|momo|number)\b", re.I),
     "transfer", "incoming"),

    # ── GROUP 3: Generic incoming (must come before generic outgoing) ─────
    # "received" as a standalone word covers all remaining incoming formats
    (re.compile(r"\breceived\b", re.I),
     "transfer", "incoming"),
    # "credited" — bank-style phrasing but still an incoming-credit claim
    (re.compile(r"\bcredited\b", re.I),
     "deposit", "incoming"),
    # "deposit" standalone
    (re.compile(r"\bdeposit\b", re.I),
     "deposit", "incoming"),
    # "deposited" — past tense of deposit.  \bdeposit\b does NOT match
    # "deposited" (the word boundary falls after the 'd' in "deposit",
    # not after the 't') so we need a separate rule.
    (re.compile(r"\bdeposited\b", re.I),
     "deposit", "incoming"),
    # Passive incoming — "has been credited/deposited into your account".
    (re.compile(r"\bhas\s+been\s+(?:credited|deposited)\b", re.I),
     "deposit", "incoming"),
    # "cash receive" — non-past-tense / bad-grammar variant of the correct
    # "cash received" / "cash in received" format.  Appears in forwarded
    # scam alerts, OCR-extracted fake receipts, and manually typed fakes.
    # Placed in Group 3 so it fires before the generic outgoing catchers
    # in Group 4 (sent\b, \bpaid\b, \btransferred\b).
    (re.compile(r"\bcash\s+receive\b", re.I),
     "deposit", "incoming"),
    # Generic "receive" verb (present / infinitive) — catches
    # "payment receive", "money receive", "momo receive" and any other
    # incoming claim where the past-tense "-d" suffix was dropped.
    # Only reached after all specific outgoing (Group 1) and incoming
    # (Groups 2-3 above) patterns have been checked, so genuine outgoing
    # confirmations (“You sent GHS X”, “Payment made for”, etc.) are
    # never re-routed by this rule.
    (re.compile(r"\breceive\b", re.I),
     "transfer", "incoming"),

    # ── GROUP 4: Generic outgoing (last resort) ──────────────────────────
    # Only reached if no incoming signal matched — prevents scam phrases
    # like "sent by mistake" from overriding "received" in the same message.
    (re.compile(r"\btransferred\b", re.I), "transfer", "outgoing"),
    (re.compile(r"\bsent\b",        re.I), "transfer", "outgoing"),
    (re.compile(r"\bpaid\b",        re.I), "payment",  "outgoing"),
]


def _parse_all_amounts(text: str) -> list[float]:
    """Extract all GHS amounts found in the text."""
    matches = _AMOUNT_RE.findall(text)
    amounts = []
    for m in matches:
        try:
            amounts.append(float(m.replace(",", "")))
        except ValueError:
            continue
    return amounts


def _detect_type_and_direction(text: str) -> tuple[str | None, str]:
    """
    Determine transaction type and direction from message text.

    Walks _DIRECTION_RULES in order and returns on the first match.
    See the rule table's inline comments for the four-group priority.

    Returns (transaction_type, direction) where direction is:
      'incoming' — money arrived in the wallet (in scope for fraud analysis)
      'outgoing' — money left the wallet (out of scope)
      'unknown'  — no recognisable direction signal (treated as out of scope)
    """
    for pattern, txn_type, direction in _DIRECTION_RULES:
        if pattern.search(text):
            return txn_type, direction
    return None, "unknown"


def _detect_category(txn_type: str | None) -> str:
    """Map transaction type to a high-level category."""
    if txn_type in ("transfer", "deposit", "withdrawal"):
        return "mobile_money"
    if txn_type == "payment":
        return "merchant"
    if txn_type in ("airtime", "bill"):
        return "utility"
    return "mobile_money"


def _extract_phone(text: str) -> str | None:
    """Extract the first Ghana phone number from text."""
    match = _PHONE_RE.search(text)
    if match:
        return "0" + match.group(1)
    return None


def _normalize_name(raw: str) -> str:
    """
    Clean a raw extracted name string.

    - Strip leading/trailing whitespace
    - Strip trailing punctuation noise (dots, commas, dashes, colons)
    - Collapse any internal double-spaces caused by OCR artifacts
    - Return empty string if nothing meaningful remains
    """
    name = raw.strip()
    # Remove trailing punctuation / noise chars that regex may include
    name = re.sub(r"[\s.,\-:;]+$", "", name)
    # Collapse internal multiple spaces (common in OCR output)
    name = re.sub(r"\s{2,}", " ", name)
    return name


def _extract_name(text: str, direction: str) -> str | None:
    """Extract counterparty name based on direction."""
    # For incoming and unknown direction, try "from NAME" first
    if direction in ("incoming", "unknown"):
        match = _NAME_FROM_RE.search(text)
    else:
        match = _NAME_TO_RE.search(text)

    if match:
        name = _normalize_name(match.group(1))
        # Sanity check: must be at least 2 characters and contain a letter
        if len(name) >= 2 and re.search(r"[A-Za-z]", name):
            return name

    # Fallback 2: "by NAME" pattern — scam / reversal variants
    # e.g. "GHS 50 sent to you by KWAME MENSAH"
    if direction in ("incoming", "unknown"):
        by_match = re.search(
            r"by\s+([A-Z][A-Za-z\s.'-]{1,60}?)"
            r"(?:\s*[\(\.,]|\s*Trans|\s*Fee|\s+\d|\s*[\r\n]|\s*$)",
            text,
            re.IGNORECASE,
        )
        if by_match:
            name = _normalize_name(by_match.group(1))
            if len(name) >= 2 and re.search(r"[A-Za-z]", name):
                return name

    # Fallback 3: subject-verb — "NAME sent/transferred GHS X to your wallet"
    # Handles incoming alerts where the sender is the grammatical subject.
    # Direction must already be confirmed incoming (via "to your wallet/account"
    # or "sent to you" direction rules) before this pattern fires.
    # Uses re.match (anchored at string start) to avoid matching "You sent".
    if direction in ("incoming", "unknown"):
        _SUBJECT_VERB_RE = re.compile(
            r"([A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,4})\s+"
            r"(?:sent|transferred|paid|deposited)\b",
            re.IGNORECASE,
        )
        sv_match = _SUBJECT_VERB_RE.match(text)  # match = anchored at start
        if sv_match:
            candidate = _normalize_name(sv_match.group(1))
            # Reject common non-name subjects (pronouns, brand names)
            _STOP = frozenset(
                ["you", "your", "the", "a", "an", "my",
                 "mtn", "mobile", "money", "mo", "momo"]
            )
            if (
                len(candidate) >= 2
                and re.search(r"[A-Za-z]", candidate)
                and candidate.lower() not in _STOP
            ):
                return candidate

    return None


def _extract_datetime(text: str) -> str | None:
    """Extract a datetime string from the message."""
    match = _DATETIME_RE.search(text)
    if match:
        return match.group(1).strip()
    return None


def _calculate_confidence(fields: dict) -> float:
    """
    Score how confident we are in the parse result.
    More extracted fields = higher confidence.
    """
    weights = {
        "amount": 0.25,
        "transaction_type": 0.15,
        "counterparty_name": 0.10,
        "counterparty_number": 0.10,
        "mtn_transaction_id": 0.10,
        "balance_after": 0.10,
        "fee": 0.05,
        "tax": 0.05,
        "transaction_datetime": 0.05,
        "transaction_reference": 0.05,
    }

    score = 0.0
    for field, weight in weights.items():
        if fields.get(field) is not None:
            score += weight

    return round(min(score, 1.0), 2)


# ═══════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════

def parse_sms(raw_text: str) -> dict:
    """
    Parse an MTN MoMo SMS message and extract structured fields.

    Parameters
    ----------
    raw_text : str
        The raw SMS body pasted by the user.

    Returns
    -------
    dict with keys:
        extracted_text        — cleaned text (same as raw for SMS)
        mtn_transaction_id    — MTN internal transaction ID
        transaction_reference — reference code
        transaction_datetime  — datetime string from the message
        transaction_type      — 'transfer' | 'deposit' | 'payment' |
                                 'withdrawal' | 'airtime' | 'bill' | None
        transaction_category  — 'mobile_money' | 'merchant' | 'utility'
        direction             — 'incoming' | 'outgoing' | 'unknown'
        counterparty_name     — sender / receiver name
        counterparty_number   — sender / receiver phone
        amount                — transaction amount (GHS)
        fee                   — fee charged (GHS)
        tax                   — tax / e-levy (GHS)
        total_amount          — amount + fee + tax (when calculable)
        balance_after         — wallet balance after the transaction
        available_balance     — available balance (when shown)
        provider              — always 'MTN' for v1
        parser_confidence     — 0.0–1.0
    """
    if not raw_text or not raw_text.strip():
        return {
            "extracted_text": None,
            "mtn_transaction_id": None,
            "transaction_reference": None,
            "transaction_datetime": None,
            "transaction_type": None,
            "transaction_category": None,
            "direction": "unknown",   # empty text has no recognisable direction
            "counterparty_name": None,
            "counterparty_number": None,
            "amount": None,
            "fee": None,
            "tax": None,
            "total_amount": None,
            "balance_after": None,
            "available_balance": None,
            "provider": "MTN",
            "parser_confidence": 0.0,
        }

    text = raw_text.strip()

    # --- Extract transaction type and direction ---
    txn_type, direction = _detect_type_and_direction(text)
    txn_category = _detect_category(txn_type)

    # --- Extract transaction ID ---
    txn_id_match = _TXN_ID_RE.search(text)
    mtn_transaction_id = txn_id_match.group(1) if txn_id_match else None

    # --- Extract reference ---
    ref_match = _REF_RE.search(text)
    transaction_reference = ref_match.group(1) if ref_match else None

    # --- Extract datetime ---
    transaction_datetime = _extract_datetime(text)

    # --- Extract counterparty ---
    counterparty_name = _extract_name(text, direction)
    counterparty_number = _extract_phone(text)

    # --- Extract amounts ---
    all_amounts = _parse_all_amounts(text)
    amount = all_amounts[0] if all_amounts else None

    # --- Extract fee ---
    fee_match = _FEE_RE.search(text)
    fee = float(fee_match.group(1).replace(",", "")) if fee_match else None

    # --- Extract tax ---
    tax_match = _TAX_RE.search(text)
    tax = float(tax_match.group(1).replace(",", "")) if tax_match else None

    # --- Extract balances ---
    balance_match = _BALANCE_RE.search(text)
    balance_after = float(balance_match.group(1).replace(",", "")) if balance_match else None

    avail_match = _AVAIL_BALANCE_RE.search(text)
    available_balance = float(avail_match.group(1).replace(",", "")) if avail_match else None

    # --- Calculate total ---
    total_amount = None
    if amount is not None:
        total_amount = amount + (fee or 0.0) + (tax or 0.0)

    # --- Build result ---
    fields = {
        "extracted_text": text,
        "mtn_transaction_id": mtn_transaction_id,
        "transaction_reference": transaction_reference,
        "transaction_datetime": transaction_datetime,
        "transaction_type": txn_type,
        "transaction_category": txn_category,
        "direction": direction,
        "counterparty_name": counterparty_name,
        "counterparty_number": counterparty_number,
        "amount": amount,
        "fee": fee,
        "tax": tax,
        "total_amount": total_amount,
        "balance_after": balance_after,
        "available_balance": available_balance,
        "provider": "MTN",
        "parser_confidence": 0.0,  # placeholder, calculated below
    }

    fields["parser_confidence"] = _calculate_confidence(fields)

    return fields


# ═══════════════════════════════════════════════
# Scope classification
# ═══════════════════════════════════════════════

# Transaction types that are within scope for the fraud detector.
# These are messages confirming money has ARRIVED in the wallet.
_IN_SCOPE_TYPES = frozenset({"transfer", "deposit", "payment"})

# Transaction types that are ALWAYS out of scope regardless of direction.
_ALWAYS_OUT_OF_SCOPE_TYPES = frozenset({"airtime", "bill", "withdrawal"})

# Human-readable out-of-scope reasons (kept calm and informative).
_SCOPE_REASON = {
    "outgoing":  "Outgoing transaction confirmation — the fraud detector covers incoming credit alerts only.",
    "airtime":   "Airtime purchase confirmation — not within the incoming-fraud detection scope.",
    "bill":      "Bill payment confirmation — not within the incoming-fraud detection scope.",
    "withdrawal":"Cash withdrawal confirmation — not within the incoming-fraud detection scope.",
    "unknown":   "Message type could not be identified as an incoming credit alert — no fraud analysis was run.",
}

# Social-engineering phrases that appear exclusively in fake incoming-credit
# scams (reversal scams, wrong-transfer scams, mistake-transfer scams).
# When a message carries these phrases but the direction parser labelled it
# "outgoing" (e.g. because the scammer wrote "I sent you GHS X") or
# "unknown", it must still go through fraud analysis rather than being
# silently discarded as out-of-scope.
_SCAM_SOCIAL_RE = re.compile(
    r"""
    \b(?:
        sent\s+(?:(?:in\s+)?by\s+)?(?:error|mistake)   # sent in error / sent by mistake
      | kindly\s+return                                  # kindly return the money
      | send\s+back                                      # send it back
      | wrong\s+(?:transaction|transfer)                 # wrong transaction / wrong transfer
      | accidental(?:ly)?\s+transfer(?:red)?             # accidental / accidentally transferred
      | mistaken(?:ly)?\s+(?:transfer(?:red)?|payment)  # mistaken transfer / mistakenly sent
      | return\s+(?:the\s+)?(?:money|amount|funds)       # return the money / return the amount
      | (?:reverse|reversal\s+of)\s+(?:the\s+)?          # reverse the transaction / reversal of
        (?:transfer|transaction|payment)
      | by\s+mistake                                     # "transferred by mistake", "sent by mistake to you"
      | in\s+error                                       # "paid in error", "transferred in error"
      | please\s+return                                  # "please return the funds/amount"
      | do\s+not\s+spend                                 # "do not spend before calling us"
      | don't\s+spend                                    # "don't spend it"
    )\b
    """,
    re.I | re.VERBOSE,
)

# General incoming-money CLAIM patterns for the is_in_scope() fallback.
# These cover messages that still reach direction="unknown" even after the
# expanded _DIRECTION_RULES walk — for example, a message that uses a
# currency amount + "from SENDER" structure with no verb, or uses bad-
# grammar phrasing that the regex table doesn\'t recognise.
# Any message that CLAIMS incoming money must be analysed for fraud;
# marking it out-of-scope would silently suppress genuine scam detection.
_INCOMING_CLAIM_RE = re.compile(
    r"""
    \b(?:
        # Bad-grammar / non-past-tense incoming-credit verb forms
        (?:cash|payment|money|amount|transfer|momo)\s+receive\b

        # Currency amount immediately followed by \u201cfrom\u201d — e.g. \u201c505.00 from REBECCA”.
        # This structure appears in forwarded fake-receipt alerts where the
        # scammer omits a verb entirely.
      | (?:GHS?\s*[\d,.]+|[\d,.]+\s*GHS)\s+from\b
    )
    """,
    re.I | re.VERBOSE,
)


def is_in_scope(parsed: dict) -> tuple[bool, str]:
    """
    Decide whether a parsed message should go through fraud analysis.

    Scope rule: ONLY messages where money is claimed to have ARRIVED in the
    wallet (incoming transfers, payments received, cash-in / deposits) are
    in scope.  Everything else — outgoing payments, airtime, bill payments,
    cash withdrawals, and unrecognised message types — is out of scope.

    Returns
    -------
    (in_scope, reason)
    in_scope : bool
        True  → incoming-credit alert; run fraud analysis.
        False → out of scope; skip the fraud classifier.
    reason : str
        One-sentence explanation returned in the API response.
    """
    direction = parsed.get("direction", "unknown")
    txn_type  = parsed.get("transaction_type")

    # Always-out-of-scope types (airtime, bill, withdrawal) regardless of direction
    if txn_type in _ALWAYS_OUT_OF_SCOPE_TYPES:
        reason_key = txn_type if txn_type in _SCOPE_REASON else "outgoing"
        return False, _SCOPE_REASON[reason_key]

    # Outgoing direction is normally out of scope.  However, scammers
    # sometimes phrase their pitch as "I sent GHS X to your account by
    # mistake — please return it", which causes the word 'sent' to trigger
    # the outgoing label even though the message is a fake incoming-credit
    # scenario.  If the message carries hard social-engineering language
    # that is exclusive to such scams, upgrade it to in-scope so that the
    # fraud classifier can flag it correctly.
    if direction == "outgoing":
        raw_text = parsed.get("extracted_text") or ""
        if _SCAM_SOCIAL_RE.search(raw_text) and txn_type not in _ALWAYS_OUT_OF_SCOPE_TYPES:
            return True, ""
        return False, _SCOPE_REASON["outgoing"]

    # Unknown direction — normally out of scope to avoid flooding the
    # classifier with unrelated messages.  But if the message contains
    # social-engineering language that exclusively accompanies fake
    # incoming-credit scams (reversal, wrong-transfer, etc.), OR if it
    # makes a general incoming-money claim (even with bad grammar or
    # non-standard phrasing), treat it as in-scope so fraud analysis
    # can run.
    if direction == "unknown":
        raw_text = parsed.get("extracted_text") or ""
        if _SCAM_SOCIAL_RE.search(raw_text) or _INCOMING_CLAIM_RE.search(raw_text):
            return True, ""
        return False, _SCOPE_REASON["unknown"]

    # Incoming with a recognised in-scope transaction type → in scope
    if direction == "incoming" and txn_type in _IN_SCOPE_TYPES:
        return True, ""

    # Incoming but transaction type not specifically recognised — still
    # in scope (e.g. novel MTN format with 'received' keyword).  Better
    # to analyse an ambiguous incoming message than to silently skip it.
    if direction == "incoming":
        return True, ""

    # Fallback: anything not handled above is out of scope.
    return False, _SCOPE_REASON["unknown"]

"""
Authenticity Engine v6.1 — Phase 7 Part 3B calibration refinement.

RECALIBRATION GOAL (v6.1):
  Maximise genuine-bias for messages matching known MTN structure.
  Optional-field penalties at near-zero.  Scam wording and broken
  authenticity patterns carry the strongest penalties.

Three weighted components decide whether an SMS is genuine, suspicious,
or likely fraudulent:

  1. TEXT AUTHENTICITY  (weight 0.60)  — primary decision driver
     Checks the raw SMS against the canonical MTN machine-generated
     template and scans for scam-specific language.
     v6.1: trust bonus at -0.25 and genuine lock forces text_risk
     to 0.0 when core markers pass with no fraud flags.

  2. STRUCTURAL CONSISTENCY  (weight 0.35)  — strong supporting signal
     Verifies parsed fields form a valid transaction.
     v6.1: structural cap widens (text_risk <= 0.20) and caps at 0.02.

  3. BEHAVIOR  (weight 0.05)  — soft confirming signal only
     Compares the transaction against user history.
     Behaviour CANNOT override a text+structure verdict.

Decision thresholds on the weighted composite:
  genuine            composite <= 0.32
  suspicious         0.32 < composite <= 0.45
  likely_fraudulent  composite > 0.45

Calibration principles (v6.1)
  - Genuine-first bias: when core MTN markers (opener + balance + txn ID)
    are present, a trust bonus (-0.25) plus the genuine lock ensure
    optional-field gaps NEVER flip a genuine message to suspicious.
  - A single weak anomaly (missing datetime, blank reference, new sender,
    slight parser miss) ALWAYS stays genuine.
  - Suspicious requires MORE THAN ONE clear anomaly — not optional-
    field gaps or parser misses.
  - Likely-fraudulent requires strong scam signals (urgency, PIN request,
    wrong wording, character manipulation) or multiple stacked clear
    fraud indicators.
  - Fraud penalties carry the heaviest weights — scam phrases, urgency
    language, PIN requests, and homoglyphs are decisive.

Output keys match the contract in message_check_service.py:
  predicted_label, confidence_score, explanation,
  format_risk_score, behavior_risk_score,
  balance_consistency_score, sender_novelty_score, model_version
"""

import re


# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

MODEL_VERSION = "v6.5-rule-based"

# ── Component weights (sum = 1.0) ──
_W_TEXT       = 0.60   # text authenticity — primary
_W_STRUCTURE  = 0.35   # structural consistency — strong support
_W_BEHAVIOR   = 0.05   # user behaviour — confirming signal only

# ── Classification thresholds (on the weighted composite) ──
# v6.1: genuine band widened to 0.32.  Combined with the trust bonus
# (-0.25), the genuine lock, and the structural cap (text_risk <= 0.20
# → cap 0.02), real MTN messages with optional-field gaps comfortably
# stay genuine.
_THRESHOLD_GENUINE    = 0.32   # composite ≤ 0.32 → genuine
_THRESHOLD_SUSPICIOUS = 0.45   # 0.32 < composite ≤ 0.45 → suspicious
                               # composite > 0.45 → likely_fraudulent

# ── Ghana mobile phone prefixes (MTN + other networks for interop) ──
_GHANA_MOBILE_PREFIXES = {
    "020", "023", "024", "025", "026", "027", "028",
    "050", "053", "054", "055", "056", "057", "059",
}

# ── Canonical MTN MoMo opening phrases (case-insensitive) ──
# IN-SCOPE openers only — outgoing message formats have been removed.
# The scope gate (is_in_scope) is the primary enforcement point; this
# list provides a secondary defence inside the authenticity engine:
# an outgoing message that somehow passes the gate will get a
# no_canonical_opener violation (+0.32 risk) rather than a trust bonus.
_CANONICAL_OPENERS = [
    # Incoming transfer — the most common real MTN format
    "you have received",
    "you received",
    "you've received",
    # Cash-in / deposit
    "cash in of",
    "cash in received",
    "cash-in of",
    "cash received",
    # Payment received
    "payment of",
    "payment received",
    # Transfer / deposit received
    "transfer received",    # e.g. "Transfer received: GHS X from NAME"
    "deposit of",
    "transfer from",        # "Transfer from NAME"
    # Generic incoming notification openers
    "transaction alert",
    "momo transaction",
    "momo received",        # app-generated incoming variant
]

# ── Non-MTN incoming-money claim openers ──
# Phrases that CLAIM money arrived, even though they do NOT match a genuine
# MTN machine-generated template.  Messages with one of these openers receive
# a lighter template penalty (0.10) than messages with no incoming-money
# signal at all (0.32).  The reduced penalty reflects that we know the
# message is ABOUT an incoming transfer — the fraud analysis (Stage B) then
# decides whether the claim is genuine or a scam.  This implements the
# product rule: every incoming-money claim must be analysed; only the
# certainty of the opener affects the initial risk weight.
_INCOMING_CLAIM_OPENERS = [
    # Passive deposit / credit claims (common in forged messages)
    "has been deposited",   # "GHS X has been deposited into your account"
    "was deposited",        # "GHS X was deposited to your wallet"
    "has been credited",    # bank-style passive credit claim
    "was credited to",      # "GHS X was credited to your account"
    "has been transferred",
    "was transferred to",
    # Nominal / announcement patterns
    "a credit of",          # "A credit of GHS X has been made..."
    "amount credited",
    "amount deposited",
    "amount received",
    "funds received",
    "money received",
    # Directional incoming phrasing
    "sent to your",         # "GHS X was sent to your number/wallet"
    # v6.4 phase 2: bad-grammar / non-past-tense incoming claim openers.
    # These appear in forwarded scam alerts, OCR-extracted fake receipts,
    # and manually typed fake payment notifications.  They receive the
    # lighter non_mtn_incoming_claim penalty (0.10) — Stage B signal
    # detection (suspicious phrases, homoglyphs, etc.) then decides
    # genuine vs scam.
    "cash receive",         # "Cash receive for GHS 505.00 from NAME"
    "cash receive for",     # even more specific variant
    "payment receive",      # "payment receive of GHS X"
    "money receive",        # "money receive from NAME"
    "amount receive",       # "amount receive: GHS X"
    "transfer receive",     # "transfer receive from NAME"
    "momo receive",         # "momo receive for GHS X"
    "receive for",          # "receive for 505.00 from" (verb-object pattern)
]


def _normalize_for_matching(text: str) -> str:
    """Normalize text for opener/phrase matching.

    Collapses whitespace, strips zero-width and non-word leading chars,
    lowercases.  Used so minor spacing, punctuation, or casing
    differences in pasted SMS don't cause false opener mismatches.
    """
    t = text.lower().strip()
    # Remove zero-width characters (common copy-paste artefacts)
    t = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', t)
    # Collapse all whitespace runs to a single space
    t = re.sub(r'\s+', ' ', t)
    # Strip leading non-word characters (stray punctuation from paste)
    t = re.sub(r'^[^\w]+', '', t)
    return t

# ── Suspicious / non-MTN wording ──
# Phrases that real MTN SMS never uses.
_SUSPICIOUS_PHRASES = [
    "cash receive",       # bad grammar — MTN says "received" not "receive"
    "credited",           # bank-style, not MTN
    "has been made",      # passive voice scam template
    "dear customer",      # MTN uses no greeting
    "dear valued",
    "kindly return",
    "send back",
    "sent in error",
    "sent by mistake",
    "confirm your identity",
    "verify your account",
    "call our verification",
    "release your funds",
    "mtn momo:",          # scam prefix (real MTN has no colon prefix)
    "mtn mobile money:",  # another scam prefix
    "has been b'lock",    # scam block language with apostrophe
    "has been block",     # scam account block language
    "don't attempt",      # scam PIN/account threat
    "do not attempt",     # variant threat language
    "merchant report",    # fake merchant report scam
    "by the mtn",         # awkward grammar in scam messages
    # Phase 9: Ghana-specific scam phrases
    "head office",        # scam: "call head office to verify"
    "customer care",      # scam impersonation of support
    "customer service",   # variant
    "call centre",        # scam: "contact our call centre"
    "call center",        # US spelling variant
    "you have won",       # prize/lottery scam
    "congratulations",    # prize/lottery scam opener
    "click here",         # phishing link prompt
    "click the link",     # phishing variant
    "security alert",     # fake security notification
    "update your",        # scam: "update your details/account"
    "system upgrade",     # fake maintenance scam
    "maintenance fee",    # fee collection scam
    "reversal transaction",  # fake reversal scam
    "contact us immediately", # urgent scam call-to-action
    "temporarily blocked",   # account threat scam
    "temporary hold",        # account threat variant
    "call to verify",        # scam verification prompt
    "call to confirm",       # scam confirmation prompt
    # Phase 9.1: wrong-transaction and additional patterns
    "wrong transaction",  # scam: "wrong transaction, send back"
    "wrong transfer",     # variant
    "accidental transfer",   # social-engineering variant
    "mistaken transfer",     # variant
    "account will be closed", # account closure threat
    "account closure",       # variant
    "enter your pin",        # scam PIN harvesting (also in PIN list)
    # v6.4: expanded return-money and reversal language
    "please return",         # "please return the money" — never in real MTN
    "return the money",      # explicit return demand
    "return my money",       # ownership framing before demand
    "reverse the transfer",  # explicit reversal request
    "reverse the transaction", # variant
    "to reverse it",         # "contact us to reverse it"
    # v6.4: accidental-send adverb+verb variants
    "accidentally sent",     # "I accidentally sent GHS X"
    "mistakenly sent",       # "I mistakenly sent GHS X"
    # v6.4: "don't spend" — classic scam instruction before asking for return
    "do not spend",          # "do not spend the money before calling"
    "don't spend",           # apostrophe variant
    # v6.5: multi-message screenshot scam patterns
    # These appear in screenshots that capture a SEQUENCE of SMS bubbles:
    #   Msg 1: fake payment claim  →  Msg 2: reversal demand  →  Msg 3: threat
    "dear value subscriber",  # scam greeting — typo variant of "dear valued subscriber"
    "due to report",          # "due to REPORT" authority-threat claim
    "dear valued subscriber", # canonical scam greeting — MTN never greets by name
    # v6.5b: "Dear MobileMoneyUser" blocking scam + call-the-office coercion
    "have been block",        # "you have been BLOCKED" — variant of "has been block"
    "dear mobilemoneyuser",   # "Dear Mobilemoneyuser you have been BLOCKED"
    "dear mobile money user", # variant with spaces
    "call the office",        # scam: "Call the office to unblock your account"
    "call office",            # shorter variant
    "sorry dear",             # scam opener: "Sorry Dear Mobilemoneyuser" — MTN never apologises
]

# ── OCR-tolerant suspicious-phrase regexes (Phase 9.1) ──
# Compiled patterns that catch common OCR misreads of scam phrases.
# These are checked in addition to the plain-text list above.
_SUSPICIOUS_PHRASE_REGEXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"b[il1!]?[o0]ck[e3]d\s+acc[o0]unt", re.I), "blocked account"),
    (re.compile(r"acc[o0]unt\s+b[il1!]?[o0]ck[e3]d", re.I), "account blocked"),
    (re.compile(r"acc[o0]unt\s+su[s5]p[e3]nd[e3]d", re.I), "account suspended"),
    (re.compile(r"h[e3]ad\s+[o0]ff[il1!]c[e3]", re.I), "head office"),
    (re.compile(r"cust[o0]m[e3]r\s+car[e3]", re.I), "customer care"),
    (re.compile(r"cust[o0]m[e3]r\s+s[e3]rv[il1!]c[e3]", re.I), "customer service"),
    (re.compile(r"v[e3]r[il1!]fy\s+y[o0]ur", re.I), "verify your"),
    (re.compile(r"c[o0]nf[il1!]rm\s+y[o0]ur", re.I), "confirm your"),
    (re.compile(r"wr[o0]ng\s+transact[il1!][o0]n", re.I), "wrong transaction"),
    (re.compile(r"wr[o0]ng\s+transf[e3]r", re.I), "wrong transfer"),
    (re.compile(r"r[e3]v[e3]rsa[il1!]\s+transact[il1!][o0]n", re.I), "reversal transaction"),
    (re.compile(r"w[il1!]{2}\s+be\s+r[e3]v[e3]rs[e3]d", re.I), "will be reversed"),
    (re.compile(r"s[e3]nt\s+[il1!]n\s+[e3]rr[o0]r", re.I), "sent in error"),
    (re.compile(r"k[il1!]nd[il1!]y\s+r[e3]turn", re.I), "kindly return"),
    (re.compile(r"d[e3]ar\s+(?:va[il1!]u[e3]d\s+)?cust[o0]m[e3]r", re.I), "dear customer"),
    (re.compile(r"c[o0]ngratulat[il1!][o0]n", re.I), "congratulations"),
    (re.compile(r"r[e3][il1!][e3]as[e3]\s+y[o0]ur\s+fund", re.I), "release your funds"),
    (re.compile(r"ma[il1!]nt[e3]nanc[e3]\s+f[e3]{2}", re.I), "maintenance fee"),
    (re.compile(r"syst[e3]m\s+upgrad[e3]", re.I), "system upgrade"),
    (re.compile(r"c[il1!][il1!]ck\s+h[e3]r[e3]", re.I), "click here"),
    (re.compile(r"[e3]nt[e3]r\s+y[o0]ur\s+p[il1!]n", re.I), "enter your pin"),
    # v6.4: scammer instructs recipient to call a specific Ghana mobile number.
    # Real MTN transaction alerts NEVER include a callback number.
    # Ghana mobile prefixes: 020/023/024/025/026/027/028/050/053/054/055/056/057/059
    (re.compile(r"\bcall\s+0[2-5]\d{8}\b", re.I), "call_phone_number"),
    (re.compile(r"\bcontact\s+0[2-5]\d{8}\b", re.I), "contact_phone_number"),
    # "dial 024XXXXXXX" — note: "dial *170#" (shortcode) is legitimate and NOT matched
    (re.compile(r"\bdial\s+0[2-5]\d{8}\b", re.I), "dial_phone_number"),
    # v6.4: OCR-tolerant reversal and return patterns
    (re.compile(r"r[e3]v[e3]rs[e3]\s+(?:th[e3]\s+)?(?:transf[e3]r|transact[il1!][o0]n)", re.I), "reverse the transfer"),
    (re.compile(r"pl[e3]as[e3]\s+r[e3]turn", re.I), "please return"),
    (re.compile(r"acc[il1!]d[e3]ntal[il1!]y\s+s[e3]nt", re.I), "accidentally sent"),
    (re.compile(r"m[il1!]stak[e3]n[il1!]y\s+s[e3]nt", re.I), "mistakenly sent"),
    (re.compile(r"d[o0]\s+n[o0]t\s+sp[e3]nd", re.I), "do not spend"),
    # v6.5b: "Dear MobileMoneyUser" and "call the office" OCR-tolerant patterns
    (re.compile(r"d[e3]ar\s+m[o0]b[il1!][il1!][e3]\s*m[o0]n[e3]y\s*us[e3]r", re.I), "dear mobilemoneyuser"),
    (re.compile(r"ca[il1!]{2}\s+(?:th[e3]\s+)?[o0]ff[il1!]c[e3]", re.I), "call the office"),
    (re.compile(r"(?:has|have)\s+been\s+b[il1!]?[o0]ck", re.I), "have been block"),
]

# ── Urgency / manipulation keywords ──
_URGENCY_WORDS = [
    "immediately", "urgent", "urgently", "expire", "act now",
    "within 24", "within 48", "account being blocked",
    "will be blocked", "avoid", "failure to", "result in reversal",
    "suspended", "locked",
    "b'lock",             # apostrophe evasion of "block"
    # Phase 9: additional urgency patterns
    "reversed",           # threat: "transaction will be reversed"
    "as soon as possible", # urgency variant
    "account will be closed", # account closure threat
    # v6.4: explicit reversal and return-demand threat phrases
    "will be reversed",   # "the transaction will be reversed if not returned"
    "must be returned",   # "funds must be returned immediately"
    "if not returned",    # "if not returned within 24 hours"
]

# ── OCR-tolerant urgency regexes (Phase 9.1) ──
_URGENCY_REGEXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"[il1!]mm[e3]d[il1!]at[e3][il1!]y", re.I), "immediately"),
    (re.compile(r"urg[e3]nt[il1!]y", re.I), "urgently"),
    (re.compile(r"fa[il1!][il1!]ur[e3]\s+t[o0]", re.I), "failure to"),
    (re.compile(r"w[il1!]{2}\s+be\s+b[il1!]?[o0]ck[e3]d", re.I), "will be blocked"),
    (re.compile(r"acc[o0]unt\s+b[e3][il1!]ng\s+b[il1!]?[o0]ck", re.I), "account being blocked"),
    (re.compile(r"su[s5]p[e3]nd[e3]d", re.I), "suspended"),
    (re.compile(r"r[e3]su[il1!]t\s+[il1!]n\s+r[e3]v[e3]rsa[il1!]", re.I), "result in reversal"),
    # v6.5: suspension duration and report-threat patterns
    # “Suspended for 91 DAYS” / “suspended for 30 days” — specific numeric threat
    (re.compile(r"su[s5]p[e3]nd[e3]d\s+f[o0]r\s+\d{1,3}", re.I), "suspended_for_days"),
    # “due to REPORT” — authority-claim threat used in subscriber-blocking scams
    (re.compile(r"d[ue3]+\s+t[o0]\s+r[e3]p[o0]rt", re.I), "due_to_report"),
]

# ── PIN / credential harvesting keywords ──
_PIN_REQUEST_WORDS = [
    "your pin", "momo pin", "your password", "your otp",
    "date of birth", "dob", "secret code",
    "attempt your pin",   # scam PIN threat pattern
]

# ── OCR-tolerant PIN regexes (Phase 9.1) ──
_PIN_REGEXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"y[o0]ur\s+p[il1!]n", re.I), "your pin"),
    (re.compile(r"m[o0]m[o0]\s+p[il1!]n", re.I), "momo pin"),
    (re.compile(r"y[o0]ur\s+pa[s5]{2}w[o0]rd", re.I), "your password"),
    (re.compile(r"y[o0]ur\s+[o0]tp", re.I), "your otp"),
    (re.compile(r"s[e3]cr[e3]t\s+c[o0]d[e3]", re.I), "secret code"),
    (re.compile(r"dat[e3]\s+[o0]f\s+b[il1!]rth", re.I), "date of birth"),
]

# ── Hard vs soft scam signal classification ────────────────────────────────
# Hard phrases are DEFINITIVE fraud evidence.  A real MTN transaction
# notification NEVER contains these in any context — neither in the message
# body nor in the surrounding app UI.  They override all trust paths.
#
# Soft/ambient phrases may legitimately appear in app UI captured by
# screenshot OCR (e.g. "reversed" shows as a transaction status in the
# MoMo app history, "suspended" is used in legitimate MTN security notices,
# "locked" appears on phone lock-screen overlays).  When these are the ONLY
# Stage B matches and core genuine transaction markers are confirmed, they
# are treated as OCR context noise rather than fraud evidence.
_HARD_SCAM_PHRASE_SET = frozenset({
    # Personalised greeting — MTN never greets
    "dear customer", "dear valued",
    # Social-engineering action demands
    "kindly return", "send back",
    "sent in error", "sent by mistake",
    # Account/identity demands
    "confirm your identity", "verify your account",
    "call our verification", "release your funds",
    # Credential harvesting
    "your pin", "momo pin", "your otp", "secret code", "enter your pin",
    # Wrong-transaction / reversal scams
    "wrong transaction", "wrong transfer",
    "accidental transfer", "mistaken transfer",
    "reversal transaction",
    # Impersonation phrases (MTN never names its own support channel in SMS)
    "head office", "customer care", "customer service",
    "call centre", "call center",
    "call to verify", "call to confirm",
    "contact us immediately",
    # Prize / phishing openers
    "you have won", "congratulations",
    # Fee-collection scams
    "maintenance fee",
    # Threat language (explicit)
    "don't attempt", "do not attempt",
    "has been b'lock", "has been block",
    "merchant report",
    # Account closure threats
    "account will be closed", "account closure",
    "temporarily blocked", "temporary hold",
    # v6.4: return-money demands and reversal phrases
    "please return", "return the money", "return my money",
    "accidentally sent", "mistakenly sent",
    "do not spend", "don't spend",
    "reverse the transfer", "reverse the transaction", "to reverse it",
    # v6.4: callback-number instruction labels (set by regex match in Stage B)
    "call_phone_number", "contact_phone_number", "dial_phone_number",
    # v6.5: multi-message screenshot scam markers
    # ‘cash receive’ is definitively non-MTN grammar — MTN always says ‘received’.
    # When it appears in Stage B, _hard_stage_b_fired must be True so the
    # screenshot_ocr_noise_only suppression path cannot silently absorb it.
    "cash receive",
    "dear value subscriber",
    "dear valued subscriber",
    "due to report",
    # v6.5b: "Dear MobileMoneyUser" blocking scam + call-the-office coercion
    "have been block",
    "dear mobilemoneyuser",
    "dear mobile money user",
    "call the office",
    "call office",
    "sorry dear",
})

# Hard urgency phrases — specific scam threat constructs.
# Single urgency words ("immediately", "urgent") are LEFT as soft because
# MTN itself uses them in legitimate notifications ("credited immediately").
_HARD_URGENCY_WORD_SET = frozenset({
    "account being blocked",    # compound threat
    "will be blocked",          # explicit block threat
    "result in reversal",       # reversal threat pattern
    "failure to",               # "failure to pay/respond" scam formula
    "b'lock",                   # apostrophe obfuscation of "block"
    "act now",                  # scam call-to-action
    # v6.4: explicit reversal and return-demand constructs
    "will be reversed",         # "the transaction will be reversed"
    "must be returned",         # "funds must be returned within X hours"
    "if not returned",          # "if not returned, account will be closed"
    # v6.5: numeric suspension threat + report-threat construct
    "suspended_for_days",       # "suspended for 91 days" — specific blocking threat
    "due_to_report",            # "due to REPORT" — authority-claim scam phrase
})


_KNOWN_MISSPELLINGS = [
    "recieved", "recevied", "recived",
    "acount", "acccount",
    "maintanance", "maintenace",
    "transfered", "transafer",
    "deposite",
]

# ── Per-violation weights for template checks ──
# Hard fraud indicators at highest levels.  Soft/optional-field
# penalties reduced to near-zero — the trust bonus (-0.25) plus the
# genuine lock make them irrelevant when core markers pass.
_VIOLATION_WEIGHTS = {
    # Hard violations — strong fraud indicators (each alone pushes
    # the score past the genuine threshold)
    "no_canonical_opener": 0.32,     # message doesn't start like MTN
    # v6.4: lighter penalty for non-MTN but incoming-claim openers.
    # The message is clearly about an incoming transfer; Stage B signal
    # detection determines whether it is genuine or a scam.
    "non_mtn_incoming_claim": 0.10,  # claims incoming money, not MTN format
    "no_balance_mention":  0.28,     # all real MTN SMS mention balance
    "wrong_currency":      0.15,     # GHC instead of GHS
    "wrong_field_order":   0.12,     # E-levy before Fee (reversed)
    "unexpected_ref_field": 0.10,    # "Ref:" never appears in real MTN

    # Medium violations — notable but not conclusive alone
    "missing_txn_id_label": 0.06,    # "Transaction ID:" absent
    "elevy_math_wrong":    0.06,     # E-levy=0 on a >GHS100 transfer

    # Soft violations — near-zero.  The trust bonus (-0.25) fully
    # absorbs these when core markers pass, and the genuine lock
    # forces risk to 0.0 when no fraud flags fire.
    "missing_fee_elevy_text": 0.001, # no fee/e-levy text
    "non_standard_txn_id": 0.003,    # ID present but unusual format
    "no_datetime":         0.001,    # many real MTN SMS lack timestamps
    "name_not_all_caps":   0.001,    # edge cases exist in real msgs
    # v6.4: compound penalty — non-MTN opener AND no balance evidence.
    # Fires only when the message CLAIMS incoming money (non-MTN format)
    # but provides zero balance proof.  Ensures such bare claims reach
    # at least the 'suspicious' threshold rather than scoring as genuine.
    "bare_incoming_claim": 0.12,     # non-MTN opener + no balance
}
# Note: misspellings are handled separately at 0.12 per occurrence.

# ── Compiled regexes ──
# Field ordering: Real MTN always prints "Fee charged: …" BEFORE "E-levy: …".
_FEE_BEFORE_ELEVY_RE = re.compile(
    r"Fee\s+charged.*?E-?levy", re.IGNORECASE | re.DOTALL
)
_ELEVY_BEFORE_FEE_RE = re.compile(
    r"E-?levy.*?Fee\s+charged", re.IGNORECASE | re.DOTALL
)

# Transaction ID in raw text: "Transaction ID: XXXXXXXXXX"
_RAW_TXN_ID_RE = re.compile(
    r"Transaction\s+ID:\s*(\S+)", re.IGNORECASE
)

# ── v6.2: Promotional footer detector ──────────────────────────────────────
# Real MTN transaction SMS sometimes include a marketing/app-download footer.
# These footer phrases are NOT fraud signals.  If detected, context-sensitive
# phrases like "click here" and "click the link" are excluded from Stage B
# scoring — they refer to a download link, not a phishing action.
_PROMO_FOOTER_RE = re.compile(
    r"(?:download|install|get\s+the\s+app|mtn\s+momo\s+app|mtn\.com"
    r"|momo\.mtn|app\s+store|google\s+play|play\s+store|manage\s+your\s+money"
    r"|experience\s+more)",
    re.IGNORECASE,
)
# Suspicious-phrase labels that are safe in a promo/download context
_PROMO_SAFE_PHRASES = {"click here", "click the link"}

# Name after "from" followed by a Ghana phone number
_NAME_PHONE_RE = re.compile(
    r"from\s+([A-Za-z][A-Za-z\s]+?)\s+0[2-5]\d{8}"
)

# Unexpected "Ref:" field — real MTN never includes this
# Note: "Reference:" (full word) is a legitimate MTN field and is NOT matched.
_REF_FIELD_RE = re.compile(r"\bRef:\s*\S+", re.IGNORECASE)

# Datetime in DD/MM/YYYY HH:MM format
_DATETIME_RE = re.compile(r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}")

# Wrong currency code
_WRONG_CURRENCY_RE = re.compile(r"\bGHC\b")

# Spacing anomalies
_MULTI_SPACE_RE = re.compile(r"[ ]{2,}")
_TAB_RE = re.compile(r"\t")

# Parser's Transaction ID — purely numeric, 10-11 digits
# Real MTN IDs (e.g. 78319906534) can be 11 digits.
_PURE_NUMERIC_RE = re.compile(r"^\d{10,11}$")

# ── OCR-tolerant genuine-indicator patterns (Phase 9.2) ──
# When text comes from screenshot OCR, exact keyword matching may fail
# due to Tesseract character substitution.  These regexes catch common
# OCR variants of genuine MTN MoMo indicators.
_OCR_BALANCE_RE    = re.compile(r"(?:current|available)?\s*ba[il1!]?a?nc[e3]", re.I)
_OCR_TXN_ID_RE     = re.compile(r"transact[il1!]?[o0]n\s*[il1!]?d", re.I)
_OCR_GHS_AMOUNT_RE = re.compile(r"GHS\s*[\d,.]+", re.I)
_OCR_FEE_RE        = re.compile(r"(?:f[e3]{2}\s*(?:charg[e3]d)?|transact[il1!]?[o0]n\s*f[e3]{2})", re.I)
_OCR_PAYMENT_RE    = re.compile(r"(?:paym[e3]nt|r[e3]c[e3][il1!]v[e3]d|cash\s*[il1!]n|you\s+(?:have\s+)?r[e3]c[e3][il1!]v[e3]d)", re.I)


def _has_ocr_genuine_indicators(text: str) -> tuple[bool, int]:
    """Check if OCR text has strong genuine MoMo indicators despite garbling.

    Returns (is_genuine_looking, indicator_count).
    Requires >= 2 of 5 indicators to consider it genuine-looking.
    This lower threshold (vs 3) accounts for heavy OCR garbling on
    genuine screenshots while still filtering out non-MoMo images.
    """
    count = sum([
        bool(_OCR_BALANCE_RE.search(text)),
        bool(_OCR_TXN_ID_RE.search(text)),
        bool(_OCR_GHS_AMOUNT_RE.search(text)),
        bool(_OCR_FEE_RE.search(text)),
        bool(_OCR_PAYMENT_RE.search(text)),
    ])
    return count >= 2, count


# ─── v6.5 Multi-message scam combo detection (module-level regexes) ─────────
# Detects the classic cash-receive → reversal → suspension-threat sequence.
# This scam captures multiple SMS bubbles from a scammer in one screenshot.
#
# Pattern:
#   Msg 1: "Cash receive for GHS 200.00 from NAME"      (fake payment claim)
#   Msg 2: "Reversal of GHS 200.00 have been made"       (reversal demand)
#   Msg 3: "You have been suspended for 91 DAYS due to REPORT"  (threat)
#
# Any two of these present together is a hard fraud signal.
_COMBO_FAKE_RECEIVE_RE = re.compile(
    r"cash\s+rec[e3][il1!]ve(?:\s+for|\s+of)?"   # "Cash receive for/of"
    r"|rec[e3][il1!]ve\s+for",                    # bare "receive for"
    re.IGNORECASE,
)
_COMBO_REVERSAL_CLAIM_RE = re.compile(
    # "Reversal of GHS X …" or "reversal have been made"
    r"r[e3]v[e3]rsa[il1!]\s+of\s+"
    r"|r[e3]v[e3]rsa[il1!]\s+(?:have|has)\s+been",
    re.IGNORECASE,
)
_COMBO_SUSPENSION_DAYS_RE = re.compile(
    # "suspended for 91 DAYS" or "suspended for 30 days" — numeric duration
    r"su[s5]p[e3]nd[e3]d\s+f[o0]r\s+\d{1,3}",
    re.IGNORECASE,
)
_COMBO_DEAR_SUBSCRIBER_RE = re.compile(
    # "Dear value subscriber" / "Dear valued subscriber"
    r"dear\s+val[ue]{1,4}\s+subscrib",
    re.IGNORECASE,
)

# ═══════════════════════════════════════════════════════════════
# 1a. CANONICAL TEMPLATE VALIDATOR
# ═══════════════════════════════════════════════════════════════
# Genuine MTN SMS are machine-generated and follow an exact template.
# Each violation is individually weighted via _VIOLATION_WEIGHTS so
# that minor format quirks don't cascade into false positives.

def _validate_canonical_template(
    raw_text: str, parsed: dict, input_method: str = "sms_paste"
) -> list[str]:
    """
    Check how closely the message matches the canonical MTN SMS template.

    Returns a list of violation strings.  Empty list = perfect match.
    """
    violations: list[str] = []
    text = raw_text.strip()
    text_lower = text.lower()

    # ── V1. Canonical opener — two-tier check (v6.4) ──
    # Tier 1: Does the opener match a GENUINE MTN template?
    #         No violation — full trust-bonus path available.
    # Tier 2: Does the opener claim incoming money in non-MTN wording?
    #         Light penalty (0.10) — Stage B decides genuine vs scam.
    # Tier 3: No recognisable incoming-money claim at all.
    #         Heavy penalty (0.32) — message is likely unrelated or faked.
    norm_text = _normalize_for_matching(text)
    # Phase 9.2: widen for screenshot OCR — phone status-bar junk may
    # precede the real opener in OCR-extracted text.
    _opener_limit = 160 if input_method == "screenshot_ocr" else 80
    opener_window = norm_text[:_opener_limit]

    _has_mtn_opener = any(op in opener_window for op in _CANONICAL_OPENERS)
    if not _has_mtn_opener:
        _has_incoming_claim_opener = any(
            op in opener_window for op in _INCOMING_CLAIM_OPENERS
        )
        if _has_incoming_claim_opener:
            # Non-MTN incoming-money claim: lighter penalty so that the
            # fraud signals in Stage B carry the full evidential weight.
            violations.append("non_mtn_incoming_claim")
        else:
            # No recognisable incoming-money claim at all.
            violations.append("no_canonical_opener")

    # ── V2. Transaction ID: present, labelled, 10-11 pure digits ──
    txn_match = _RAW_TXN_ID_RE.search(text)
    if txn_match:
        txn_val = txn_match.group(1).rstrip(".").rstrip(",")
        if not re.match(r"^\d{10,11}$", txn_val):
            violations.append("non_standard_txn_id")
    else:
        violations.append("missing_txn_id_label")

    # ── V3. Fee before E-levy ordering (when both are present) ──
    has_both = (
        _FEE_BEFORE_ELEVY_RE.search(text)
        or _ELEVY_BEFORE_FEE_RE.search(text)
    )
    if (has_both
            and _ELEVY_BEFORE_FEE_RE.search(text)
            and not _FEE_BEFORE_ELEVY_RE.search(text)):
        violations.append("wrong_field_order")

    # ── V4. Name in ALL CAPS (raw-text check; parser can't extract names) ──
    name_match = _NAME_PHONE_RE.search(text)
    if name_match:
        name_val = name_match.group(1).strip()
        if name_val != name_val.upper():
            violations.append("name_not_all_caps")

    # ── V5. Balance mentioned ──
    if "balance" not in text_lower:
        violations.append("no_balance_mention")

    # ── V6. Datetime present (DD/MM/YYYY HH:MM) ──
    # For pasted SMS, date/time is optional — carriers often strip
    # timestamps when the user copies the message body.
    # Phase 9.2: screenshots, like pasted SMS, often lack timestamps.
    if not _DATETIME_RE.search(text) and input_method not in ("sms_paste", "screenshot_ocr"):
        violations.append("no_datetime")

    # ── V7. E-levy math for transfers > GHS 100 ──
    amount = parsed.get("amount")
    tax = parsed.get("tax")
    is_transfer = parsed.get("transaction_type") in ("transfer", "payment")
    if is_transfer and amount is not None and amount > 100:
        if tax is not None and tax == 0.0:
            violations.append("elevy_math_wrong")

    # ── V8. Fee/E-levy/Tax text present for transfers ──
    # Genuine MTN transfer receipts always show at least one of:
    # "Fee charged:", "TRANSACTION FEE", "E-levy", or "TAX charged:" / "Tax:"
    # v6.2: added "tax" as a valid genuine field indicator so that messages
    # using "TAX charged: GHS X" format are not incorrectly penalised.
    if is_transfer:
        has_fee_text = (
            "fee charged" in text_lower
            or "transaction fee" in text_lower
            or "tax charged" in text_lower   # real MTN uses "TAX charged: GHS"
        )
        has_elevy_text = "e-levy" in text_lower or "e levy" in text_lower
        has_tax_text = "tax" in text_lower   # any explicit tax mention counts
        if not has_fee_text and not has_elevy_text and not has_tax_text:
            violations.append("missing_fee_elevy_text")

    # ── V9. Unexpected fields — "Ref:" is never in real MTN SMS ──
    # Note: "Reference:" (the full word) IS a valid MTN field and is
    # not matched by this pattern.
    if _REF_FIELD_RE.search(text):
        violations.append("unexpected_ref_field")

    # ── V10. Currency code — GHS not GHC ──
    if _WRONG_CURRENCY_RE.search(text):
        violations.append("wrong_currency")

    # ── V11. Misspellings (machine-generated text has zero typos) ──
    # Skipped for screenshot_ocr — Tesseract commonly garbles characters
    # into patterns that match known misspellings (e.g. "recived" from
    # "received").  These are OCR artefacts, not fraud signals.
    if input_method != "screenshot_ocr":
        for misspelling in _KNOWN_MISSPELLINGS:
            if misspelling in text_lower:
                violations.append(f"misspelling:{misspelling}")
                break

    # ── V12. Bare incoming claim (non-MTN opener + no balance proof) ──
    # A non-MTN phrased incoming claim that also lacks any balance
    # information provides no verifiable transaction data.  This compound
    # condition indicates high uncertainty: the message SAYS money arrived
    # but cannot be checked against any wallet state.
    # The extra 0.12 penalty ensures the composite exceeds the genuine
    # threshold (0.32) and lands in the suspicious band.
    if (
        "non_mtn_incoming_claim" in violations
        and "no_balance_mention" in violations
    ):
        violations.append("bare_incoming_claim")

    return violations


# ═══════════════════════════════════════════════════════════════
# 1b. TEXT AUTHENTICITY SCORER  (0.0 – 1.0 risk)
# ═══════════════════════════════════════════════════════════════
# Two-stage scoring:
#   Stage A — Template compliance (is the format correct?)
#   Stage B — Scam-content detection (does it contain red-flag language?)
#
# v6.1 calibration flow:
#   1. Score template violations (Stage A)
#   2. Apply trust bonus (-0.25) when core markers pass
#   3. Score scam content (Stage B)
#   4. Apply genuine lock (force 0.0) when trust bonus applied + no
#      Stage B flags fired

def _score_text_authenticity(
    raw_text: str, parsed: dict, input_method: str = "sms_paste"
) -> tuple[float, list[str]]:
    """
    Score how closely the raw SMS matches genuine MTN language.

    Returns (risk_score, list_of_flags_triggered).
    """
    if not raw_text:
        return 1.0, ["empty_message"]

    flags: list[str] = []
    risk = 0.0
    text_lower = raw_text.lower()
    text_stripped = raw_text.strip()

    # v6.5b: strip brackets/parens for matching — OCR captures UI emphasis
    # styling like "(BLOCKED)" or "[SUSPENDED]" that break substring matching.
    _text_match = re.sub(r'[()[\]{}]', '', text_lower)
    _raw_match = re.sub(r'[()[\]{}]', '', raw_text)

    # ══════════════════════════════════════════════
    # STAGE A — Canonical template validation
    # ══════════════════════════════════════════════
    # Each violation adds its own weight from _VIOLATION_WEIGHTS.
    violations = _validate_canonical_template(raw_text, parsed, input_method)
    if violations:
        for v in violations:
            # Misspellings use a "misspelling:word" key — extract base name
            base_key = v.split(":")[0] if v.startswith("misspelling") else v
            weight = _VIOLATION_WEIGHTS.get(base_key, 0.05)
            # Misspellings get a fixed 0.12 penalty (strong fraud signal)
            if v.startswith("misspelling"):
                weight = 0.12
            risk += weight
            flags.append(f"tmpl:{v}")

    # ── Structural trust bonus (v6.2: -0.25) ──
    # When all three core MTN markers are present (canonical opener,
    # balance mention, transaction ID label), the message is almost
    # certainly machine-generated by MTN.  The -0.25 bonus generously
    # absorbs all soft violations (each <= 0.003), ensuring genuine
    # messages with optional-field gaps score exactly 0.
    # v6.4: non_mtn_incoming_claim also blocks this path — messages with
    # a non-MTN opener must use the _strong_parsed_fields path instead.
    _core_markers_present = (
        "tmpl:no_canonical_opener" not in flags
        and "tmpl:non_mtn_incoming_claim" not in flags   # non-MTN opener disqualifies
        and "tmpl:no_balance_mention" not in flags
        and "tmpl:missing_txn_id_label" not in flags
    )

    # ── Strong genuine indicators (v6.2) ──
    # When the parser successfully extracted amount, transaction ID,
    # balance, AND fee/tax, the message carries the hallmarks of a
    # real MTN transaction even if the opening phrase didn't match
    # a known pattern exactly.  These strong fields outweigh small
    # phrase variations and entitle the message to the trust bonus.
    _strong_parsed_fields = (
        parsed.get("amount") is not None
        and parsed.get("mtn_transaction_id") is not None
        and parsed.get("balance_after") is not None
        and (parsed.get("fee") is not None or parsed.get("tax") is not None)
    )

    # ── Screenshot OCR genuine indicators (Phase 9.2) ──
    # When input is from screenshot OCR, OCR-tolerant pattern matching
    # provides a third trust path.  Even if exact keywords were garbled
    # enough to miss both _core_markers_present and _strong_parsed_fields,
    # the overall message shape may still be clearly genuine.
    _screenshot_ocr_genuine = False
    if input_method == "screenshot_ocr":
        _ocr_genuine, _ocr_count = _has_ocr_genuine_indicators(raw_text)
        if _ocr_genuine:
            _screenshot_ocr_genuine = True

    _trust_eligible = (
        _core_markers_present
        or _strong_parsed_fields
        or _screenshot_ocr_genuine
    )

    if _trust_eligible:
        # Screenshot OCR gets a larger bonus (-0.40) to absorb extra
        # template violations caused by OCR character substitution.
        if risk > 0:
            _bonus = 0.40 if _screenshot_ocr_genuine else 0.25
            risk = max(risk - _bonus, 0.0)
        if _screenshot_ocr_genuine:
            flags.append("screenshot_ocr_genuine")
        elif _strong_parsed_fields and not _core_markers_present:
            flags.append("strong_fields_bonus")
        # Always mark trust_bonus_applied when trust is established so
        # the genuine lock (below) can fire even when Stage A was
        # already risk=0 and no bonus was arithmetically needed.
        flags.append("trust_bonus_applied")

    # ══════════════════════════════════════════════
    # STAGE B — Scam-content detection
    # ══════════════════════════════════════════════

    # Track whether any Stage B fraud flag fires (used by genuine lock).
    _stage_b_fired = False

    # Track specifically whether any HARD (definitive) scam signal fired.
    # Hard signals remain decisive even in screenshot mode.
    # Soft signals (single words like "reversed", "suspended", "locked")
    # may be OCR captures from app UI on genuine screenshots — they must NOT
    # override confirmed genuine transaction structure.
    _hard_stage_b_fired = False

    # ── v6.2: Detect genuine MTN promotional/download footer ──
    # If the message contains a promotional app-download section, phrases
    # like "click here" / "click the link" are marketing text, not scam
    # instructions.  Exclude them from Stage B scoring in this context.
    _has_promo_footer = bool(_PROMO_FOOTER_RE.search(raw_text))

    # ── B1. Suspicious / scam phrases (Phase 9.1: multi-match + OCR regex) ──
    # Count ALL matching phrases — each additional hit adds +0.10 on top
    # of the base +0.28.  OCR-tolerant regexes run as a second pass so
    # imperfect OCR text still gets caught.
    _susp_hits: list[str] = []
    for phrase in _SUSPICIOUS_PHRASES:
        # v6.2: skip promo-safe phrases when a genuine download footer is present
        if phrase in _PROMO_SAFE_PHRASES and _has_promo_footer:
            continue
        if phrase in _text_match:
            _susp_hits.append(phrase)
    # OCR-regex fallback: only check regexes whose label wasn't already caught
    _susp_hit_set = set(_susp_hits)
    for pat, label in _SUSPICIOUS_PHRASE_REGEXES:
        if label not in _susp_hit_set and pat.search(_raw_match):
            _susp_hits.append(label)
            _susp_hit_set.add(label)

    if _susp_hits:
        # Base penalty for the first hit + 0.10 per extra hit
        risk += 0.28 + 0.10 * (len(_susp_hits) - 1)
        for ph in _susp_hits:
            flags.append(f"suspicious_phrase:{ph}")
        _stage_b_fired = True
        # Mark as hard if any matched phrase is in the hard set
        if any(ph in _HARD_SCAM_PHRASE_SET for ph in _susp_hits):
            _hard_stage_b_fired = True

    # ── B2. Urgency / manipulation language (Phase 9.1: multi-match + regex) ──
    _urg_hits: list[str] = []
    for word in _URGENCY_WORDS:
        if word in _text_match:
            _urg_hits.append(word)
    _urg_hit_set = set(_urg_hits)
    for pat, label in _URGENCY_REGEXES:
        if label not in _urg_hit_set and pat.search(_raw_match):
            _urg_hits.append(label)
            _urg_hit_set.add(label)

    if _urg_hits:
        risk += 0.35 + 0.08 * (len(_urg_hits) - 1)
        for uw in _urg_hits:
            flags.append(f"urgency:{uw}")
        _stage_b_fired = True
        # Mark as hard if any matched urgency phrase is a specific scam construct
        if any(uw in _HARD_URGENCY_WORD_SET for uw in _urg_hits):
            _hard_stage_b_fired = True

    # ── B3. PIN / credential request (Phase 9.1: multi-match + regex) ──
    _pin_hits: list[str] = []
    for kw in _PIN_REQUEST_WORDS:
        if kw in _text_match:
            _pin_hits.append(kw)
    _pin_hit_set = set(_pin_hits)
    for pat, label in _PIN_REGEXES:
        if label not in _pin_hit_set and pat.search(_raw_match):
            _pin_hits.append(label)
            _pin_hit_set.add(label)

    if _pin_hits:
        risk += 0.50 + 0.10 * (len(_pin_hits) - 1)
        for pk in _pin_hits:
            flags.append(f"pin_request:{pk}")
        _stage_b_fired = True
        _hard_stage_b_fired = True   # PIN requests are always hard scam signals

    # ── B4. Homoglyphs (Phase 9.2: skip for screenshot OCR) ──
    # Catches words like "MOBlLE" where a lowercase letter hides among
    # uppercase — character manipulation is a strong scam indicator.
    # Skipped for screenshot OCR — Tesseract frequently produces mixed-
    # case artefacts that are OCR errors, not character manipulation.
    if input_method != "screenshot_ocr":
        for word in re.findall(r"\b[A-Za-z]{4,}\b", raw_text):
            uppers = sum(1 for c in word if c.isupper())
            lowers = sum(1 for c in word if c.islower())
            if uppers >= 3 and 0 < lowers <= 2:
                risk += 0.28                         # v6.1: strong
                flags.append(f"homoglyph_suspect:{word}")
                _stage_b_fired = True
                _hard_stage_b_fired = True           # character manipulation = hard
                break

    # ── B5. Spacing anomalies ──
    # Tab characters never appear in genuine SMS.
    # Double-space penalty removed — real MTN messages have minor
    # carrier formatting quirks that are not fraud signals.
    if _TAB_RE.search(raw_text):
        risk += 0.05
        flags.append("tab_character")
        _stage_b_fired = True
        # Tabs can appear in some phone screenshot OCR outputs — only
        # treat as hard when not from a screenshot.
        if input_method != "screenshot_ocr":
            _hard_stage_b_fired = True

    # ── B6. No currency marker at all ──
    if "ghs" not in text_lower and "ghc" not in text_lower:
        risk += 0.06
        flags.append("no_currency_marker")
        _stage_b_fired = True

    # ── B7. Message too short to be a real notification ──
    if len(text_stripped) < 30:
        risk += 0.08
        flags.append("too_short")
        _stage_b_fired = True

    # ── B8. Compound scam escalation (Phase 9.1: scaled by hits) ──
    # When multiple scam-signal categories fire simultaneously,
    # the message is almost certainly a scam attempt.  The penalty
    # scales with the total number of individual hits across all
    # three categories (suspicious phrases + urgency + PIN).
    _scam_categories_fired = sum([
        len(_susp_hits) > 0,
        len(_urg_hits) > 0,
        len(_pin_hits) > 0,
    ])
    _total_scam_hits = len(_susp_hits) + len(_urg_hits) + len(_pin_hits)
    if _scam_categories_fired >= 2:
        # Base +0.15 for crossing 2+ categories, +0.03 per extra hit
        compound_penalty = 0.15 + 0.03 * max(_total_scam_hits - 2, 0)
        risk += min(compound_penalty, 0.35)          # cap at 0.35
        flags.append(f"compound_scam_signal:{_scam_categories_fired}cat_{_total_scam_hits}hits")
        _stage_b_fired = True

    # ── B9. Scam content with no MTN structure (Phase 9.1: scaled) ──
    # Scam phrases in text that lacks all core MTN markers (opener,
    # balance, transaction ID) is a strong combined signal — the
    # message tries to look official but has no real transaction data.
    # Penalty scales with how many scam hits were found.
    if _stage_b_fired and not _trust_eligible:
        no_structure_penalty = min(0.10 + 0.04 * max(_total_scam_hits - 1, 0), 0.25)
        risk += no_structure_penalty
        flags.append("scam_no_structure")

    # ── B10. Multi-message scam sequence (v6.5) ─────────────────────────────
    # Detects the cash-receive → reversal → suspension-threat pattern captured
    # in screenshots of multi-bubble SMS conversations.
    #
    # Why this rule is necessary:
    #   The screenshot_ocr genuine-lock (below) is designed to suppress SOFT
    #   ambient signals like "reversed" or "suspended" when they appear as app
    #   UI labels around a REAL MTN transaction.  But when a screenshot shows
    #   a SEQUENCE of scam messages, the OCR genuine indicators (a GHS amount,
    #   "received") come from the fake payment claim, and the scammer's threat
    #   words get incorrectly suppressed as "noise".
    #
    # Firing any two of these three combo ingredients together is a definitive
    # hard-fraud signal that bypasses the genuine lock.
    _combo_fake_receive  = bool(_COMBO_FAKE_RECEIVE_RE.search(_raw_match))
    _combo_reversal      = bool(_COMBO_REVERSAL_CLAIM_RE.search(_raw_match))
    _combo_suspension    = bool(_COMBO_SUSPENSION_DAYS_RE.search(_raw_match))
    _combo_dear_sub      = bool(_COMBO_DEAR_SUBSCRIBER_RE.search(_raw_match))

    _combo_threat_present = _combo_suspension or _combo_dear_sub

    if _combo_fake_receive and (_combo_reversal or _combo_threat_present):
        # Full cash-receive scam sequence confirmed
        parts = []
        if _combo_fake_receive:    parts.append("fake_receive")
        if _combo_reversal:        parts.append("reversal_claim")
        if _combo_suspension:      parts.append("suspension_threat")
        if _combo_dear_sub:        parts.append("dear_subscriber")
        risk += 0.65
        flags.append("multi_msg_scam_combo:" + "+".join(parts))
        _stage_b_fired = True
        _hard_stage_b_fired = True   # explicitly blocks the genuine lock
    elif _combo_reversal and _combo_threat_present:
        # Reversal claim + suspension/dear-subscriber threat without the
        # fake-receive opener — still a hard two-ingredient combo
        risk += 0.50
        flags.append("multi_msg_scam_combo:reversal+threat")
        _stage_b_fired = True
        _hard_stage_b_fired = True

    # ══════════════════════════════════════════════
    # GENUINE LOCK (v6.2 extended for screenshot_ocr)
    # ══════════════════════════════════════════════
    #
    # Standard path: trust_bonus applied + no Stage B → lock to genuine.
    #
    # Screenshot extension (new in v6.2):
    #   When input is from a screenshot, the OCR text captures far more
    #   than just the message — app inbox history, transaction status
    #   labels ("Transaction reversed"), navigation UI, promotional
    #   banners, and other context words that are NOT fraud signals.
    #
    #   If the trust bonus has been applied (core transaction markers
    #   confirmed) AND the ONLY Stage B matches are soft/ambient words
    #   (e.g. "reversed" from a prior transaction, "suspended" from a
    #   security notice, "locked" from a phone screen label) with NO hard
    #   scam phrases (PIN demands, reversal threats, dear-customer greetings,
    #   etc.), the soft hits are treated as OCR context noise and the
    #   genuine lock still fires.
    #
    # v6.5: _hard_stage_b_fired is now True whenever "cash receive",
    #   "due to report", a numeric suspension threat, or the full
    #   multi-message combo is detected — so those signals are NEVER
    #   suppressed by the screenshot noise path.
    _screen_ocr_noise_only = (
        _stage_b_fired
        and not _hard_stage_b_fired
        and input_method == "screenshot_ocr"
        and _trust_eligible
    )

    _pre_lock_risk = risk   # save before genuine lock potentially zeros it

    if "trust_bonus_applied" in flags and (not _stage_b_fired or _screen_ocr_noise_only):
        risk = 0.0
        if _screen_ocr_noise_only:
            # Record which soft signals were suppressed for the explanation builder
            flags.append("screenshot_noise_suppressed")
        flags.append("genuine_lock")

    # ── Screenshot red-flag override (v6.5b) ──────────────────────────────
    # Safety net: even when the genuine lock fires (the first SMS bubble
    # matches real MTN structure), if the FULL screenshot text contains
    # definitive coercive/threat language the message MUST NOT be verified.
    # This catches residual cases where brackets, novel phrasing, or OCR
    # artefacts let threat words slip past the normal Stage B patterns.
    if input_method == "screenshot_ocr" and "genuine_lock" in flags:
        _screenshot_redflag_re = re.compile(
            r"you\s+have\s+been\s+(?:blocked|suspended|reported|restricted)"
            r"|call\s+(?:the\s+)?office"
            r"|dear\s+(?:mobile\s*money\s*)?user"
            r"|dear\s+(?:valued?\s+)?subscriber"
            r"|account\s+(?:has\s+been\s+)?(?:blocked|closed|suspended|restricted)"
            r"|your\s+account\s+(?:is|will\s+be)\s+(?:blocked|closed|suspended)"
            r"|reported\s+to\s+(?:mtn|police|authorit)",
            re.IGNORECASE,
        )
        if _screenshot_redflag_re.search(_raw_match):
            flags.remove("genuine_lock")
            if "screenshot_noise_suppressed" in flags:
                flags.remove("screenshot_noise_suppressed")
            risk = max(_pre_lock_risk, 0.45) + 0.20
            risk = min(risk, 1.0)
            flags.append("screenshot_redflag_override")

    return round(min(risk, 1.0), 2), flags


# ═══════════════════════════════════════════════════════════════
# 2. STRUCTURAL CONSISTENCY SCORER  (0.0 – 1.0 risk)
# ═══════════════════════════════════════════════════════════════
# Evaluates the PARSED fields from sms_parser.py.
# v6.1: optional-field penalties at near-zero.  When text is clean
# (text_risk <= 0.20), the structural cap in analyze_message() limits
# structure contribution so parser quirks cannot influence the verdict.

def _score_structural_consistency(
    raw_text: str, parsed: dict
) -> tuple[float, list[str]]:
    """
    Score whether the parsed fields form a valid MTN transaction.

    Returns (risk_score, list_of_flags_triggered).
    """
    flags: list[str] = []
    risk = 0.0

    amount = parsed.get("amount")
    balance_after = parsed.get("balance_after")
    available_balance = parsed.get("available_balance")
    fee = parsed.get("fee")
    tax = parsed.get("tax")
    txn_id = parsed.get("mtn_transaction_id")
    phone = parsed.get("counterparty_number")
    dt = parsed.get("transaction_datetime")

    # ── 2a. Transaction ID present & purely numeric? ──
    if not txn_id:
        risk += 0.005                                # v6.1: near-zero
        flags.append("missing_txn_id")
    elif not _PURE_NUMERIC_RE.match(str(txn_id)):
        risk += 0.005                                # v6.1: near-zero
        flags.append("non_numeric_txn_id")
    else:
        # All-same-digit ID (e.g. 1111111111) is a real inconsistency
        if len(set(str(txn_id))) == 1:
            risk += 0.08
            flags.append("fabricated_txn_id")

    # ── 2b. Balance info present? ──
    # v6.1: near-zero — parser may miss balance on edge-case formatting.
    if balance_after is None:
        risk += 0.003                                # v6.1: near-zero
        flags.append("missing_balance")

    # ── 2c. Fee / e-levy parsed for transfers ──
    is_transfer = parsed.get("transaction_type") in ("transfer", "payment")
    if is_transfer and fee is None and tax is None:
        risk += 0.001                                # v6.1: near-zero
        flags.append("missing_fee_or_elevy")

    # ── 2d. Phone number present & valid Ghana prefix? ──
    if not phone:
        risk += 0.001                                # v6.1: near-zero
        flags.append("missing_phone")
    else:
        prefix = phone[:3]
        if prefix not in _GHANA_MOBILE_PREFIXES:
            risk += 0.03
            flags.append("non_ghana_prefix")

    # ── 2e. Datetime present? ──
    if not dt:
        risk += 0.001                                # v6.1: near-zero
        flags.append("missing_datetime")

    # ── 2f. Balance ≥ amount (for incoming transactions) ──
    # Genuine data inconsistency → kept at 0.10.
    direction = parsed.get("direction", "incoming")
    if direction == "incoming" and amount is not None and balance_after is not None:
        if balance_after < amount:
            risk += 0.10
            flags.append("balance_less_than_amount")

    # ── 2g. balance_after vs available_balance mismatch ──
    # v6.2: Current Balance and Available Balance legitimately differ in real
    # MTN messages — e.g., E-levy holds, reserved merchant funds, or wallet
    # states where available < current is normal.  Only flag when the gap is
    # extreme (> 50 % of the larger value), which indicates clearly broken data
    # rather than a normal real-world difference.
    if balance_after is not None and available_balance is not None:
        larger = max(balance_after, available_balance)
        if larger > 0 and abs(balance_after - available_balance) / larger > 0.50:
            risk += 0.08
            flags.append("balance_mismatch")
        # Normal small differences (e.g. GHS 5 E-levy hold) are not penalised.

    # ── 2h. Negative or zero amount ──
    # Clearly broken data → kept at 0.14.
    if amount is not None and amount <= 0:
        risk += 0.14
        flags.append("non_positive_amount")

    return round(min(risk, 1.0), 2), flags


# ═══════════════════════════════════════════════════════════════
# 3. BEHAVIOR SCORER  (0.0 – 1.0 risk)
# ═══════════════════════════════════════════════════════════════
# Behaviour is a third-tier signal (weight 0.05).
# A new sender alone, or a high-but-plausible amount alone, must
# NEVER push a genuine message to suspicious.

def _score_behavior(
    parsed: dict, profile: dict | None
) -> tuple[float, list[str]]:
    """
    Score how much this transaction deviates from the user's history.

    Returns (risk_score, list_of_flags_triggered).
    """
    flags: list[str] = []

    # No profile → no behavioural signal at all.
    if profile is None or profile.get("total_checks_count", 0) == 0:
        return 0.0, ["new_user"]

    risk = 0.0
    amount = parsed.get("amount")

    # ── 3a. Amount deviation from user's average / max ──
    if amount is not None:
        avg = profile.get("avg_incoming_amount", 0)
        max_amt = profile.get("max_incoming_amount", 0)

        if avg > 0 and amount > avg * 5:
            risk += 0.20
            flags.append("amount_5x_above_average")
        elif avg > 0 and amount > avg * 3:
            risk += 0.10
            flags.append("amount_3x_above_average")
        elif avg > 0 and amount > avg * 2:
            risk += 0.05
            flags.append("amount_2x_above_average")

        if max_amt > 0 and amount > max_amt * 1.5:
            risk += 0.06
            flags.append("exceeds_known_max")

    # ── 3b. Transaction type novelty ──
    txn_type = parsed.get("transaction_type")
    usual_types = profile.get("usual_transaction_types", [])
    if txn_type and usual_types and txn_type not in usual_types:
        risk += 0.04
        flags.append("new_txn_type")

    # ── 3c. Sender novelty ──
    # Receiving money from a new person is completely normal.
    counterparty_number = parsed.get("counterparty_number")
    usual_senders = profile.get("usual_senders", [])
    if counterparty_number and usual_senders:
        if counterparty_number not in usual_senders:
            risk += 0.02                             # v6.1: minimal
            flags.append("unknown_sender")

    return round(min(risk, 1.0), 2), flags


# ═══════════════════════════════════════════════════════════════
# Classification + Explanation
# ═══════════════════════════════════════════════════════════════

def _classify(composite_risk: float) -> str:
    """Map composite risk score to a label."""
    if composite_risk <= _THRESHOLD_GENUINE:
        return "genuine"
    elif composite_risk <= _THRESHOLD_SUSPICIOUS:
        return "suspicious"
    else:
        return "likely_fraudulent"


def _build_explanation(
    label: str,
    text_risk: float,
    structure_risk: float,
    behavior_risk: float,
    text_flags: list[str],
    structure_flags: list[str],
    behavior_flags: list[str],
    parsed: dict,
    confidence: float = 0.0,
) -> str:
    """
    Build a user-facing explanation tailored to the verdict.

    Phase 10.2 refinement — three distinct tones:
      genuine           → confident reassurance, no warning language
      suspicious        → precise about what triggered caution
      likely_fraudulent → specific fraud indicators named explicitly
    """
    # ── Collect observations, split by severity ──
    strong: list[str] = []   # decisive fraud signals
    mild:   list[str] = []   # minor format/structural notes

    # — Hard fraud indicators (strongest first) —
    if any("pin_request" in f for f in text_flags):
        strong.append(
            "Asks for your PIN or personal details "
            "\u2014 MTN never requests these by SMS."
        )
    if any(f.startswith("urgency") for f in text_flags):
        strong.append(
            "Contains urgent or threatening language "
            "not typical of genuine MTN messages."
        )
    # ── Phone-callback instruction (v6.4) ──
    # Detected via regex; replaced here with readable text so the technical
    # label ("call_phone_number") never appears in user-facing output.
    _PHONE_CALL_LABELS = frozenset({
        "call_phone_number", "contact_phone_number", "dial_phone_number"
    })
    if any(f"suspicious_phrase:{lbl}" in text_flags for lbl in _PHONE_CALL_LABELS):
        strong.append(
            "Contains an instruction to call or contact a specific phone number "
            "\u2014 genuine MTN transaction alerts never provide a callback number."
        )
    if any(f.startswith("suspicious_phrase") for f in text_flags):
        # Extract ALL matched phrases (show up to 3 for clarity).
        # Filter out phone-callback labels — already explained above.
        phrases = []
        for f in text_flags:
            if f.startswith("suspicious_phrase:"):
                lbl = f.split(":", 1)[1]
                if lbl not in _PHONE_CALL_LABELS:
                    phrases.append(lbl)
        if len(phrases) == 1:
            strong.append(
                f'Uses "{phrases[0]}" \u2014 not standard MTN wording.'
            )
        elif len(phrases) <= 3:
            quoted = ", ".join(f'"{p}"' for p in phrases)
            strong.append(
                f"Uses {quoted} \u2014 not standard MTN wording."
            )
        else:
            quoted = ", ".join(f'"{p}"' for p in phrases[:3])
            strong.append(
                f"Uses non-standard phrasing including {quoted}."
            )
    if any("homoglyph" in f for f in text_flags):
        # Extract the suspect word for specificity
        word = ""
        for f in text_flags:
            if f.startswith("homoglyph_suspect:"):
                word = f.split(":", 1)[1]
                break
        if word:
            strong.append(
                f'The word "{word}" contains unusual character '
                "substitutions."
            )
        else:
            strong.append(
                "Some characters appear altered to imitate "
                "genuine text."
            )
    if "tmpl:misspelling" in " ".join(text_flags):
        misspelled = ""
        for f in text_flags:
            if f.startswith("tmpl:misspelling:"):
                misspelled = f.split(":", 2)[2]
                break
        if misspelled:
            strong.append(
                f'Contains "{misspelled}" \u2014 official '
                "MTN messages do not contain typos."
            )
        else:
            strong.append(
                "Contains spelling errors \u2014 official MTN "
                "messages do not contain typos."
            )
    if "tmpl:no_balance_mention" in text_flags:
        strong.append(
            "No balance information \u2014 genuine MTN "
            "notifications always include a balance."
        )
    if any(f.startswith("compound_scam_signal") for f in text_flags):
        strong.append(
            "Combines multiple patterns commonly associated "
            "with MoMo fraud."
        )
    # v6.5: multi-message scam combo (cash-receive + reversal + suspension threat)
    if any(f.startswith("multi_msg_scam_combo") for f in text_flags):
        # Extract the combo description for the user
        combo_label = ""
        for f in text_flags:
            if f.startswith("multi_msg_scam_combo:"):
                combo_label = f.split(":", 1)[1].replace("+", ", ")
                break
        base_msg = (
            "Screenshot shows a multi-message scam sequence "
            "\u2014 a fake payment claim, reversal demand, or account "
            "suspension threat used together is a known MTN MoMo scam pattern."
        )
        if combo_label:
            base_msg += f" (Detected: {combo_label}.)"
        strong.append(base_msg)
    # v6.5b: screenshot red-flag override explanation
    if "screenshot_redflag_override" in text_flags:
        strong.append(
            "Screenshot contains threatening or coercive language "
            "(blocking, suspension, or pressure to call) alongside a "
            "transaction alert \u2014 this is inconsistent with a genuine "
            "MTN-only notification and matches known scam patterns."
        )
    if "scam_no_structure" in text_flags:
        strong.append(
            "Uses non-standard wording and lacks key MTN "
            "transaction details like a Transaction ID."
        )

    # Suppress soft template notes when genuine lock confirmed the msg
    _suppress_soft = (
        "genuine_lock" in text_flags
        or "strong_fields_bonus" in text_flags
        or "screenshot_ocr_genuine" in text_flags
    )
    if "tmpl:no_canonical_opener" in text_flags and not _suppress_soft:
        strong.append(
            "Opening line does not match known MTN "
            "message formats."
        )
    # v6.4: non-MTN incoming claim opener — mild note (not a hard signal)
    if "tmpl:non_mtn_incoming_claim" in text_flags and not _suppress_soft:
        mild.append(
            "opening phrase does not match standard MTN notification format"
        )

    # — Mild / format-level observations —
    if "tmpl:wrong_currency" in text_flags:
        mild.append(
            "uses the old currency code \u2018GHC\u2019 instead of \u2018GHS\u2019"
        )
    if "tmpl:wrong_field_order" in text_flags:
        mild.append(
            "Fee and E-levy lines appear in an unusual order"
        )
    if "tmpl:elevy_math_wrong" in text_flags:
        mild.append(
            "E-levy charge does not match expected rates for this amount"
        )
    if "tmpl:non_standard_txn_id" in text_flags:
        mild.append(
            "Transaction ID format looks unusual"
        )
    if "tmpl:unexpected_ref_field" in text_flags:
        mild.append(
            "includes an extra \u2018Ref:\u2019 field not used in standard MTN alerts"
        )
    if "tmpl:missing_fee_elevy_text" in text_flags:
        mild.append("fee and tax details are not shown")
    if "tmpl:missing_txn_id_label" in text_flags:
        mild.append("no Transaction ID label was found")
    if "tmpl:name_not_all_caps" in text_flags:
        mild.append(
            "sender name is not in the expected all-capitals format"
        )
    if "tmpl:no_datetime" in text_flags and not _suppress_soft:
        mild.append("no date or time is included")

    # — Structure observations —
    if "fabricated_txn_id" in structure_flags:
        strong.append(
            "Transaction ID uses repeated digits, "
            "which is not a valid MTN format."
        )
    if "non_positive_amount" in structure_flags:
        strong.append(
            "Transaction amount is zero or negative \u2014 "
            "not possible in a real transaction."
        )
    if "balance_less_than_amount" in structure_flags:
        mild.append(
            "balance shown is less than the transaction amount"
        )
    if "balance_mismatch" in structure_flags:
        mild.append(
            "the two balance figures in the message do not agree"
        )

    # — Behaviour observations (soft, contextual) —
    beh: list[str] = []
    if any("above_average" in f for f in behavior_flags):
        beh.append("amount is higher than your typical transactions")
    if "unknown_sender" in behavior_flags:
        beh.append("sender has not appeared in your history before")

    # ════════════════════════════════════════════════
    # Assemble per-verdict explanation
    # ════════════════════════════════════════════════

    if label == "genuine":
        # ── Confident, no warning language ──
        amount_str = ""
        if parsed.get("amount"):
            amount_str = f" of GHS {parsed['amount']:,.2f}"

        if "screenshot_ocr_genuine" in text_flags:
            base = (
                f"This appears to be a genuine MTN MoMo notification"
                f"{amount_str}. The content and structure are consistent "
                "with standard MTN alerts. Minor details may vary "
                "due to image quality."
            )
        else:
            base = (
                f"This message is consistent with standard MTN MoMo "
                f"format{amount_str}. Sender details, transaction data, "
                "and structure all match expected patterns."
            )

        notes = mild + beh
        if notes:
            joined = "; ".join(notes)
            base += (
                f" Note: {joined} \u2014 "
                "this does not affect the result."
            )

        # v6.3: note when OCR context noise was suppressed
        if "screenshot_noise_suppressed" in text_flags:
            base += (
                " Some words visible in the screenshot (e.g. transaction "
                "status labels from the app history) were recognised as "
                "app context, not fraud indicators."
            )

        return base

    elif label == "suspicious":
        # ── Precise: name exactly what triggered caution ──
        # Limit to the 4 most important items for scannability.
        items = (strong + mild + beh)[:4]
        if not items:
            items = ["some details could not be fully verified"]

        if len(items) == 1:
            detail = items[0]
            if detail and detail[0].islower():
                detail = detail[0].upper() + detail[1:]
            body = detail
        else:
            body = " ".join(
                f"({i}) {obs}" for i, obs in enumerate(items, 1)
            )

        if confidence >= 0.65:
            opener = "A few details differ from standard MTN alerts"
        else:
            opener = "This message could not be fully confirmed"

        return (
            f"{opener}. {body}. "
            "This may still be legitimate \u2014 check your "
            "MoMo app or dial *170# to confirm."
        )

    else:
        # ── likely_fraudulent: specific, protective, actionable ──
        # Cap at 4 bullet-worthy items for scannability.
        parts: list[str] = []

        if strong:
            parts.extend(strong[:4])

        if mild and len(parts) < 4:
            mild_joined = "; ".join(mild)
            parts.append(
                f"Also noted: {mild_joined}."
            )

        if not parts:
            parts.append(
                "Multiple details do not match what is expected "
                "from a genuine MTN notification."
            )

        body = " ".join(parts[:4])

        return (
            f"This message does not match standard MTN MoMo format. {body} "
            "Do not act on this message. To confirm a real "
            "transaction, check your MoMo app or call MTN at 100."
        )


# ═══════════════════════════════════════════════════════════════
# Public API — same signature so callers (message_check_service,
# smoke tests) don't need changes.
# ═══════════════════════════════════════════════════════════════

def analyze_message(
    raw_text: str,
    parsed_fields: dict,
    user_behavior_profile: dict | None = None,
    input_method: str = "sms_paste",
) -> dict:
    """
    Analyze an MTN MoMo SMS for authenticity.

    Parameters
    ----------
    raw_text : str
        The original SMS text submitted by the user.
    parsed_fields : dict
        Fields extracted by sms_parser.parse_sms().
    user_behavior_profile : dict | None
        The user's behavior profile from user_behavior_profiles table.
        None if the user is new (no history yet).
    input_method : str
        How the message was submitted.  'sms_paste' (default) for
        directly pasted SMS text, 'screenshot_ocr' for text extracted
        from a screenshot.  Controls tolerance for optional fields
        like date/time which are often absent in pasted messages.

    Returns
    -------
    dict with keys:
        predicted_label           — 'genuine' | 'suspicious' | 'likely_fraudulent'
        confidence_score          — 0.0–1.0
        explanation               — human-readable explanation
        format_risk_score         — text authenticity risk   (0.0–1.0)
        behavior_risk_score       — behaviour risk           (0.0–1.0)
        balance_consistency_score — structural risk           (0.0–1.0)
        sender_novelty_score      — derived from behaviour   (0.0–1.0)
        model_version             — 'v6.1-rule-based'
    """
    # ── 1. Score each component independently ──
    text_risk, text_flags = _score_text_authenticity(
        raw_text, parsed_fields, input_method
    )
    structure_risk, structure_flags = _score_structural_consistency(
        raw_text, parsed_fields
    )
    behavior_risk, behavior_flags = _score_behavior(
        parsed_fields, user_behavior_profile
    )

    # ── 1b. Structural cap when text is clean (v6.1: widened) ──
    # If the raw text closely matches MTN template (text_risk <= 0.20),
    # parser quirks in the structural scorer should NOT influence the
    # outcome.  Cap the effective structure risk so that minor field-
    # extraction failures stay harmless.
    effective_structure = structure_risk
    if text_risk <= 0.20:                            # v6.1: widened
        effective_structure = min(structure_risk, 0.02)  # v6.1: tighter

    # ── 2. Compute the weighted composite ──
    # v6.1: uses effective_structure (capped when text is clean).
    base_composite = text_risk * _W_TEXT + effective_structure * _W_STRUCTURE

    # Behavioural contribution.
    # Behaviour is capped so it can NEVER promote a text+structure-clean
    # message beyond the genuine threshold.
    behavior_add = behavior_risk * _W_BEHAVIOR
    if base_composite <= _THRESHOLD_GENUINE:
        max_allowed = max(0.0, _THRESHOLD_GENUINE - base_composite)
        behavior_add = min(behavior_add, max_allowed)

    composite_risk = round(base_composite + behavior_add, 3)

    # ── 3. Classify ──
    label = _classify(composite_risk)

    # ── 4. Confidence score ──
    # Farther from the nearest threshold boundary → more confident.
    if label == "genuine":
        confidence = round(1.0 - composite_risk, 2)
    elif label == "likely_fraudulent":
        confidence = round(min(composite_risk + 0.15, 1.0), 2)
    else:  # suspicious
        midpoint = (_THRESHOLD_GENUINE + _THRESHOLD_SUSPICIOUS) / 2
        distance = abs(composite_risk - midpoint)
        confidence = round(0.50 + distance, 2)

    confidence = max(0.10, min(confidence, 0.99))

    # ── 5. Build user-facing explanation (Phase 10.2: pass confidence) ──
    explanation = _build_explanation(
        label,
        text_risk, structure_risk, behavior_risk,
        text_flags, structure_flags, behavior_flags,
        parsed_fields,
        confidence,
    )

    # ── 6. Map to the keys that message_check_service.py expects ──
    sender_novelty = 0.0
    if "unknown_sender" in behavior_flags:
        sender_novelty = 0.10                        # v6.1: minimal
    elif "new_user" in behavior_flags:
        sender_novelty = 0.03                        # v6.1: minimal

    return {
        "predicted_label": label,
        "confidence_score": confidence,
        "explanation": explanation,
        "format_risk_score": text_risk,
        "behavior_risk_score": behavior_risk,
        "balance_consistency_score": structure_risk,
        "sender_novelty_score": round(sender_novelty, 2),
        "model_version": MODEL_VERSION,
    }
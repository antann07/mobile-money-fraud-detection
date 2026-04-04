"""
OCR Service — extract text from screenshot images.

Phase 8 Part 3: Improved preprocessing and text cleanup for MoMo screenshots.

Upgrades over Part 2:
  - Upscale-first strategy (Tesseract needs ~300 DPI)
  - Otsu's adaptive threshold via NumPy (replaces fixed threshold)
  - Median-filter denoising before binarization
  - Multi-strategy OCR: tries two preprocessing approaches, picks best
  - Expanded MoMo text normalization rules
  - Tesseract PSM tuning for phone-screenshot layouts

Uses pytesseract (Tesseract OCR) with Pillow for image loading.
Falls back gracefully if Tesseract is not installed.

Public functions:
    extract_text(image_path) → dict with extracted_text, success, confidence
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

# ── Try to import OCR dependencies ──
# If pytesseract or Pillow aren't installed, OCR will degrade gracefully.
_OCR_AVAILABLE = False
_NUMPY_AVAILABLE = False
try:
    import pytesseract
    from PIL import Image, ImageFilter, ImageEnhance
    _OCR_AVAILABLE = True

    # Allow overriding the Tesseract binary path via TESSERACT_CMD env var
    # (useful on Windows or Docker where it's not on PATH)
    _tesseract_cmd = os.environ.get("TESSERACT_CMD", "").strip()
    if _tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd

    logger.info("[OCR] pytesseract + Pillow loaded successfully")
except ImportError as e:
    logger.warning("[OCR] OCR dependencies not available: %s — screenshot OCR will be disabled", e)

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    pass  # Otsu's threshold falls back to fixed value


def is_available() -> bool:
    """Check whether OCR dependencies are installed and working."""
    if not _OCR_AVAILABLE:
        return False
    # Quick check that tesseract binary is reachable
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        logger.warning("[OCR] pytesseract imported but Tesseract binary not found on PATH")
        return False


# ── Preprocessing helpers ──


def _auto_rotate(img: "Image.Image") -> "Image.Image":
    """
    Auto-rotate based on EXIF orientation tag.

    Phone screenshots sometimes embed a rotation flag (e.g. 90°, 180°)
    that Pillow doesn't apply by default.  If we skip this, Tesseract
    sees sideways text and produces garbage.
    """
    try:
        from PIL import ExifTags
        exif = img.getexif()
        for tag_id, tag_name in ExifTags.TAGS.items():
            if tag_name == "Orientation":
                orientation = exif.get(tag_id)
                if orientation == 3:
                    img = img.rotate(180, expand=True)
                elif orientation == 6:
                    img = img.rotate(270, expand=True)
                elif orientation == 8:
                    img = img.rotate(90, expand=True)
                break
    except Exception:
        pass  # no EXIF or unreadable — not a problem
    return img


def _crop_phone_borders(img: "Image.Image") -> "Image.Image":
    """
    Crop the top and bottom ~8% of a phone screenshot.

    Phone screenshots typically include a status bar (clock, battery, signal)
    at the top and a navigation bar at the bottom.  These contain icons and
    numbers that Tesseract reads as garbage characters, polluting the output.

    We only crop if the image looks like a phone screenshot (portrait, tall).
    """
    width, height = img.size
    # Only crop portrait-oriented images that look like phone screens
    if height > width * 1.3 and height > 400:
        top_crop = int(height * 0.08)
        bottom_crop = int(height * 0.08)
        img = img.crop((0, top_crop, width, height - bottom_crop))
        logger.debug("[OCR] Cropped phone borders: top=%dpx bottom=%dpx", top_crop, bottom_crop)
    return img


def _normalize_brightness(img_gray: "Image.Image") -> "Image.Image":
    """
    Normalize brightness so very dark or very bright screenshots
    get a consistent mid-range before contrast/threshold steps.

    Uses Pillow's AutoContrast which stretches the histogram so the
    darkest pixels become 0 and the brightest become 255.
    """
    try:
        from PIL import ImageOps
        return ImageOps.autocontrast(img_gray, cutoff=1)
    except Exception:
        return img_gray  # graceful fallback


def _is_dark_background(img_gray: "Image.Image") -> bool:
    """
    Detect if the screenshot has a dark background (e.g. MoMo dark mode).

    Samples the median pixel value — if it's below 100 (out of 255)
    the background is likely dark and we should invert before OCR.
    """
    if not _NUMPY_AVAILABLE:
        return False
    pixels = np.array(img_gray, dtype=np.uint8)
    return float(np.median(pixels)) < 100


def _otsu_threshold(img_gray: "Image.Image") -> int:
    """
    Compute Otsu's optimal binarization threshold using NumPy.
    Falls back to a sensible fixed value (140) if NumPy is unavailable.

    Otsu's method picks the threshold that minimizes intra-class variance,
    so it adapts to each screenshot's brightness/contrast automatically.
    """
    if not _NUMPY_AVAILABLE:
        return 140  # safe fallback

    pixels = np.array(img_gray, dtype=np.uint8).ravel()
    hist, _ = np.histogram(pixels, bins=256, range=(0, 256))
    total = pixels.size
    sum_total = np.dot(np.arange(256), hist)

    sum_bg, weight_bg, best_thresh, best_var = 0.0, 0, 0, 0.0
    for t in range(256):
        weight_bg += hist[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * hist[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        var_between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if var_between > best_var:
            best_var = var_between
            best_thresh = t

    logger.debug("[OCR] Otsu threshold computed: %d", best_thresh)
    return best_thresh


def _preprocess_image(
    img: "Image.Image",
    aggressive: bool = False,
    invert: bool = False,
) -> "Image.Image":
    """
    Apply preprocessing to improve OCR accuracy on phone screenshots.

    Phase 8 Part 3 refined — pipeline order:
      0. Auto-rotate (EXIF)
      1. Crop phone status/nav bars
      2. Grayscale
      3. Invert if dark-mode screenshot
      4. Brightness normalization (AutoContrast)
      5. Upscale to give Tesseract enough pixels
      6. Contrast boost
      7. Median denoise
      8. Otsu adaptive threshold → binarize
      9. Sharpen (twice in aggressive mode)

    Args:
        aggressive: Heavier contrast + extra sharpening + higher upscale.
        invert:     Force pixel inversion (for dark-background screenshots).
    """
    # 0. Auto-rotate from EXIF so sideways screenshots are corrected
    img = _auto_rotate(img)

    # 1. Crop phone status/nav bars — they add garbage text
    img = _crop_phone_borders(img)

    # 2. Grayscale
    img = img.convert("L")

    # 3. Invert dark-background images so text becomes dark-on-light
    #    (Tesseract strongly prefers dark text on white background)
    if invert:
        from PIL import ImageOps
        img = ImageOps.invert(img)

    # 4. Brightness normalization — stretch histogram so dark/bright
    #    screenshots get a consistent range before later steps
    img = _normalize_brightness(img)

    # 5. Upscale FIRST — Tesseract performs best at ~300 DPI equivalent.
    #    Doing this before filtering gives filters more pixels to work with.
    width, height = img.size
    min_width = 1200 if aggressive else 900
    if width < min_width:
        scale = min_width / width
        img = img.resize(
            (int(width * scale), int(height * scale)),
            Image.LANCZOS,
        )
        logger.debug("[OCR] Upscaled by %.1fx → %dx%d", scale, img.width, img.height)

    # 6. Boost contrast — helps with faded or low-contrast screenshots
    contrast_factor = 2.0 if aggressive else 1.5
    img = ImageEnhance.Contrast(img).enhance(contrast_factor)

    # 7. Denoise — median filter removes salt-and-pepper noise
    #    without blurring text edges as much as a Gaussian would
    img = img.filter(ImageFilter.MedianFilter(size=3))

    # 8. Binarize — Otsu's adaptive threshold picks the optimal cutoff
    threshold = _otsu_threshold(img)
    img = img.point(lambda px: 255 if px > threshold else 0, mode="1")
    img = img.convert("L")  # back to grayscale for Tesseract

    # 9. Sharpen — makes character edges crisper after denoising
    img = img.filter(ImageFilter.SHARPEN)
    if aggressive:
        img = img.filter(ImageFilter.SHARPEN)  # second pass for aggressive mode

    return img


def _normalize_ocr_text(raw_text: str) -> str:
    """
    Clean up common OCR artifacts from MoMo screenshot text.

    Phase 8 Part 3 refined — normalization pipeline:
      1. Control-character & whitespace cleanup
      2. OCR punctuation repair ('|' → ':', stray brackets, etc.)
      3. Currency symbol fixes (GH$ → GHS, 6HS → GHS, …)
      4. Letter/digit substitution fixes (0↔O, 1↔l↔I↔!, 5↔S, 3↔e)
      5. Amount normalization (O → 0 inside numbers)
      6. MoMo phrase normalization (Cash In, Transaction ID, …)
      7. Date/time cleanup
      8. Mid-word line-break rejoining
    """
    if not raw_text:
        return ""

    text = raw_text

    # ========== 1. Whitespace / control chars ==========
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)   # strip control chars
    text = re.sub(r"\r\n", "\n", text)                            # CRLF → LF
    text = re.sub(r"\n{3,}", "\n\n", text)                        # collapse blank lines
    text = re.sub(r"[ \t]{2,}", " ", text)                        # collapse runs of spaces
    text = re.sub(r" *\n *", "\n", text)                          # trim spaces around newlines

    # ========== 2. OCR punctuation repair ==========
    # Tesseract frequently misreads ':' as '|', '}', '{', or ';'
    text = re.sub(r"(?<=\w)\s*[|}{;]\s*(?=\s*\S)", ": ", text)   # word| value → word: value
    text = re.sub(r"\bID[|}{;]\s*", "ID: ", text)                 # ID| → ID:
    text = re.sub(r"\bFee[|}{;]\s*", "Fee: ", text)               # Fee| → Fee:
    text = re.sub(r"\bTax[|}{;]\s*", "Tax: ", text)               # Tax| → Tax:
    text = re.sub(r"\bBalance[|}{;]\s*", "Balance: ", text)       # Balance| → Balance:
    # Stray pipe/bracket at line start (OCR artifact)
    text = re.sub(r"^[|}{]\s*", "", text, flags=re.MULTILINE)
    # '—' or '–' (em/en dash) that Tesseract inserts randomly
    text = re.sub(r"[\u2014\u2013]", "-", text)
    # Smart quotes → straight quotes
    text = re.sub(r"[\u2018\u2019\u201a]", "'", text)
    text = re.sub(r"[\u201c\u201d\u201e]", '"', text)

    # ========== 3. Currency OCR fixes ==========
    text = re.sub(r"\bGH[\$\u00a2]", "GHS", text)                 # GH$ / GH¢ → GHS
    text = re.sub(r"\b6HS\b", "GHS", text)                        # 6HS → GHS
    text = re.sub(r"\bGH5\b", "GHS", text)                        # GH5 → GHS
    text = re.sub(r"\bGl-IS\b", "GHS", text)                      # Gl-IS → GHS
    text = re.sub(r"\bGI-IS\b", "GHS", text)                      # GI-IS → GHS
    text = re.sub(r"\bGHS?\s*\.", "GHS ", text)                   # GHS. → GHS (space)
    text = re.sub(r"\bGH\s+S\b", "GHS", text)                     # GH S → GHS
    text = re.sub(r"\bG[^a-zA-Z0-9]S\b", "GHS", text)            # G.S, G-S → GHS
    text = re.sub(r"\bGI-I[S5]\b", "GHS", text)                   # GI-H5 → GHS
    text = re.sub(r"\bGH[\s]*[S5s]\b", "GHS", text)              # GH s → GHS

    # ========== 4. Letter/digit substitution fixes ==========
    text = re.sub(r"Transact[i1!][o0]n", "Transaction", text, flags=re.IGNORECASE)
    text = re.sub(r"Ba[l1!]ance", "Balance", text, flags=re.IGNORECASE)
    text = re.sub(r"Ava[i1!][l1!]ab[l1!]e", "Available", text, flags=re.IGNORECASE)
    text = re.sub(r"[Rr]ece[i1!]ved", "received", text)
    text = re.sub(r"Mobi[l1!]e", "Mobile", text, flags=re.IGNORECASE)
    text = re.sub(r"Paym[e3]n[t+]", "Payment", text, flags=re.IGNORECASE)
    text = re.sub(r"Curren[t+]", "Current", text, flags=re.IGNORECASE)
    text = re.sub(r"Ref[e3]rence", "Reference", text, flags=re.IGNORECASE)
    text = re.sub(r"F[e3][e3]\b", "Fee", text, flags=re.IGNORECASE)
    text = re.sub(r"D[e3]pos[i1!]t", "Deposit", text, flags=re.IGNORECASE)
    text = re.sub(r"W[i1!]thdraw", "Withdraw", text, flags=re.IGNORECASE)
    text = re.sub(r"Tran[s5]fer", "Transfer", text, flags=re.IGNORECASE)
    text = re.sub(r"[Nn]ot[i1!]f[i1!]cat[i1!]on", "Notification", text)
    text = re.sub(r"[Ss]ucc[e3][s5]{1,2}fu[l1!]", "Successful", text)
    text = re.sub(r"[Cc]omp[l1!][e3]t[e3]d", "Completed", text)
    text = re.sub(r"[Cc]harg[e3]d", "Charged", text)
    text = re.sub(r"P[e3]nd[i1!]ng", "Pending", text, flags=re.IGNORECASE)
    text = re.sub(r"[Ss]end[e3]r", "Sender", text)
    text = re.sub(r"[Rr]ec[i1!]p[i1!][e3]nt", "Recipient", text)
    text = re.sub(r"Acc[o0]unt", "Account", text, flags=re.IGNORECASE)

    # ========== 5. Amount normalization ==========
    # Fix O misread as 0 inside GHS amounts (e.g. "GHS 5O.OO" → "GHS 50.00")
    def _fix_amount_ohs(m: re.Match) -> str:
        return m.group(0).replace("O", "0").replace("o", "0")
    text = re.sub(r"GHS\s+[\dOo][\dOo,.]+", _fix_amount_ohs, text)

    # Fix commas misread as dots in large amounts ("1.000.00" → "1,000.00")
    # Only when the pattern is clearly thousands: digit.3digits.2digits
    text = re.sub(r"(\d)\.(\d{3})\.(\d{2})\b", r"\1,\2.\3", text)

    # Final space collapse after amount fixes (amount regex can leave double spaces)
    text = re.sub(r"GHS {2,}", "GHS ", text)

    # ========== 6. MoMo phrase normalization ==========
    text = re.sub(r"Ca[s5]h\s*[Il1!]n", "Cash In", text, flags=re.IGNORECASE)
    text = re.sub(r"Ca[s5]h\s*[O0]ut", "Cash Out", text, flags=re.IGNORECASE)
    text = re.sub(r"MoMo|MOMO|M0M0|momo|MOMo", "MoMo", text)
    text = re.sub(r"MTN\s+Mobi[l1!]e\s+Money", "MTN Mobile Money", text, flags=re.IGNORECASE)
    # "Transaction ID" with OCR junk between words
    text = re.sub(r"Transaction\s*(?:ID|[Il1!]D|[Il1!]d)", "Transaction ID", text, flags=re.IGNORECASE)
    # "Current Balance" / "Available Balance" / "New Balance"
    text = re.sub(r"Current\s+Balance", "Current Balance", text, flags=re.IGNORECASE)
    text = re.sub(r"Available\s+Balance", "Available Balance", text, flags=re.IGNORECASE)
    text = re.sub(r"[Nn]ew\s+[Bb]alance", "New Balance", text)
    # "Fee charged" / "TAX charged" normalization
    text = re.sub(r"Fee\s+[Cc]harg[e3]d", "Fee charged", text)
    text = re.sub(r"TAX\s+[Cc]harg[e3]d", "TAX charged", text)
    # "Payment made for" / "Payment received from" phrase normalization
    text = re.sub(r"Paym[e3]nt\s+[Mm]ad[e3](?=\s+for)", "Payment made", text, flags=re.IGNORECASE)
    text = re.sub(r"Paym[e3]nt\s+[Rr][e3]c[e3][il1!]v[e3]d(?=\s+from)", "Payment received", text, flags=re.IGNORECASE)
    # Amount-colon spacing: "GHS:50" → "GHS 50"
    text = re.sub(r"GHS\s*:\s*", "GHS ", text)
    # "You have received" / "You've received" normalization
    text = re.sub(r"You\s+have\s+rece[i1!]ved", "You have received", text, flags=re.IGNORECASE)
    text = re.sub(r"You'?\s*ve\s+rece[i1!]ved", "You have received", text, flags=re.IGNORECASE)
    # "from" with zero for O
    text = re.sub(r"\bfr[o0]m\b", "from", text, flags=re.IGNORECASE)
    # E-levy / E-Levy / elevy / E-1evy
    text = re.sub(r"[Ee]-?\s*[Ll1][e3]vy", "E-Levy", text)

    # ========== 7. Date/time cleanup ==========
    # Fix O misread as 0 in dates (e.g. "25/O3/2O26" → "25/03/2026")
    def _fix_date_ohs(m: re.Match) -> str:
        return m.group(0).replace("O", "0").replace("o", "0")
    text = re.sub(r"\d{1,2}[/\-][\dOo]{1,2}[/\-][\dOo]{2,4}", _fix_date_ohs, text)

    # ========== 8. Rejoin mid-word line breaks ==========
    text = re.sub(r"(?<=[a-z]),?\n(?=[a-z])", " ", text)
    text = re.sub(r"(?<=[a-z])-\n(?=[a-z])", "", text)  # hyphenated line break

    return text.strip()


def _text_is_usable(text: str) -> bool:
    """
    Check whether OCR-extracted text is usable enough to run through
    the parser + authenticity engine.

    A message is considered usable if it has:
      - At least 20 characters, AND
      - At least one MoMo-related keyword

    This prevents garbage OCR output from producing misleading predictions.
    """
    if not text or len(text.strip()) < 20:
        return False
    lower = text.lower()
    momo_signals = [
        "ghs", "transaction", "balance", "received", "payment",
        "cash in", "cash out", "fee", "mtn", "mobile money", "momo",
        "current balance", "available balance", "transaction id",
        "deposit", "withdrawal", "transfer", "e-levy",
    ]
    return any(kw in lower for kw in momo_signals)


def _detect_screenshot_context_flags(text: str) -> list[str]:
    """
    Scan OCR-extracted text for multi-message scam context patterns.

    A screenshot can capture MULTIPLE SMS bubbles in one image.  When a
    scammer sends a sequence like:
      1. "Cash receive for GHS X from NAME"   (fake payment claim)
      2. "Reversal of GHS X have been made"   (reversal demand)
      3. "You have been suspended for 91 DAYS due to REPORT"  (threat)

    … all three appear in the OCR output as one block of text.  The
    authenticity engine may misidentify the GHS amount + "received" from
    the first bubble as genuine MTN indicators and suppress the threat
    signals as "app UI noise".

    This function detects those dangerous combinations BEFORE the engine
    runs, so the route can add an explicit warning to the response.

    Returns a list of flag strings.  An empty list means no suspicious
    combinations were detected at the OCR level.
    """
    if not text or len(text.strip()) < 20:
        return []

    flags: list[str] = []

    # Detect multiple SMS bubbles: two or more blank-line gaps between
    # message blocks suggest a multi-message screenshot.
    if len(re.findall(r"\n{2,}", text)) >= 2:
        flags.append("multi_message_detected")

    # Ingredient checks (OCR-tolerant patterns)
    _has_fake_receive = bool(re.search(
        r"cash\s+rec[e3][il1!]ve(?:\s+for|\s+of)?|rec[e3][il1!]ve\s+for",
        text, re.IGNORECASE,
    ))
    _has_reversal_claim = bool(re.search(
        r"r[e3]v[e3]rsa[il1!]\s+of\s+|r[e3]v[e3]rsa[il1!]\s+(?:have|has)\s+been",
        text, re.IGNORECASE,
    ))
    _has_suspension_days = bool(re.search(
        r"su[s5]p[e3]nd[e3]d\s+f[o0]r\s+\d{1,3}",
        text, re.IGNORECASE,
    ))
    _has_dear_subscriber = bool(re.search(
        r"dear\s+val[ue]{1,4}\s+subscrib",
        text, re.IGNORECASE,
    ))
    _has_due_to_report = bool(re.search(
        r"due\s+to\s+report",
        text, re.IGNORECASE,
    ))
    # v6.5b: account-blocking threats and call-the-office coercion
    _has_blocked_threat = bool(re.search(
        r"(?:have|has)\s+been\s+[(\ \[]*(?:block|suspend|restrict)",
        text, re.IGNORECASE,
    ))
    _has_call_office = bool(re.search(
        r"call\s+(?:the\s+)?office",
        text, re.IGNORECASE,
    ))
    _has_dear_momouser = bool(re.search(
        r"dear\s+(?:mobile\s*money\s*)?user",
        text, re.IGNORECASE,
    ))

    if _has_fake_receive and _has_reversal_claim:
        flags.append("cash_receive_plus_reversal")
    if _has_reversal_claim and (_has_suspension_days or _has_dear_subscriber):
        flags.append("reversal_plus_suspension_threat")
    if _has_suspension_days or (_has_dear_subscriber and _has_due_to_report):
        flags.append("suspension_threat_detected")
    # v6.5b: blocked/call-office coercion
    if _has_blocked_threat or _has_call_office or _has_dear_momouser:
        flags.append("coercive_threat_detected")

    # contradictory_context: the screenshot mixes what looks like a payment
    # notification with a reversal demand or suspension threat.  These NEVER
    # appear together in a legitimate single MTN transaction notification.
    if (
        (_has_fake_receive or _has_reversal_claim)
        and (_has_suspension_days or _has_dear_subscriber or _has_due_to_report)
    ):
        flags.append("contradictory_context")

    # v6.5b: also contradictory when any MoMo transaction-like content
    # co-exists with account-blocking threats or call-the-office coercion.
    if "contradictory_context" not in flags and (
        _has_blocked_threat or _has_call_office or _has_dear_momouser
    ):
        _has_momo_signal = bool(re.search(
            r"(?:received|cash\s*in|payment|you\s+have\s+received)\s+(?:for\s+)?GHS",
            text, re.IGNORECASE,
        ))
        if _has_momo_signal:
            flags.append("contradictory_context")

    return flags


# ── Scam-signal detection (Phase 9.1: OCR-tolerant scam heuristic) ──
# Regex patterns that tolerate common OCR character substitutions
# (0↔o, 1↔l↔i, 5↔s, 3↔e, etc.) so scam phrases are still caught
# when Tesseract produces imperfect output.
#
# Each pattern is a compiled regex.  We use character classes like
# [o0] and [il1!] to absorb the most frequent OCR mis-reads.

_SCAM_SIGNAL_PATTERNS: list[re.Pattern] = [
    # ─── Account block / suspend threats ───
    re.compile(r"acc[o0]unt\s+(?:has\s+been\s+)?b[il1!]?[o0]ck", re.I),
    re.compile(r"acc[o0]unt\s+(?:has\s+been\s+)?su[s5]p[e3]nd", re.I),
    re.compile(r"acc[o0]unt\s+(?:has\s+been\s+)?(?:t[e3]mp[o0]rar[il1!]ly\s+)?(?:d[il1!]sabl|r[e3]str[il1!]ct)", re.I),
    re.compile(r"(?:has|have)\s+been\s+b[il1!]?[o0]ck", re.I),
    re.compile(r"(?:has|have)\s+been\s+su[s5]p[e3]nd", re.I),
    re.compile(r"t[e3]mp[o0]rar[il1!]ly\s+b[il1!]?[o0]ck", re.I),
    re.compile(r"t[e3]mp[o0]rary\s+h[o0][il1!]d", re.I),
    # ─── Head office / customer care impersonation ───
    re.compile(r"h[e3]ad\s+[o0]ff[il1!]c[e3]", re.I),
    re.compile(r"ca[il1!]{2}\s+cust[o0]m[e3]r\s+car[e3]", re.I),
    re.compile(r"ca[il1!]{2}\s+cust[o0]m[e3]r\s+s[e3]rv[il1!]c[e3]", re.I),
    re.compile(r"c[o0]ntact\s+cust[o0]m[e3]r\s+car[e3]", re.I),
    re.compile(r"ca[il1!]{2}\s+(?:our\s+)?(?:ca[il1!]{2}\s+)?c[e3]ntr[e3]", re.I),
    re.compile(r"ca[il1!]{2}\s+(?:our\s+)?(?:ca[il1!]{2}\s+)?c[e3]nt[e3]r", re.I),
    # ─── Verify / confirm identity ───
    re.compile(r"v[e3]r[il1!]fy\s+y[o0]ur\s+acc[o0]unt", re.I),
    re.compile(r"c[o0]nf[il1!]rm\s+y[o0]ur\s+[il1!]d[e3]nt[il1!]ty", re.I),
    re.compile(r"updat[e3]\s+y[o0]ur\s+d[e3]ta[il1!][il1!]", re.I),
    re.compile(r"updat[e3]\s+y[o0]ur\s+acc[o0]unt", re.I),
    # ─── PIN / credential harvesting ───
    re.compile(r"(?:y[o0]ur|m[o0]m[o0])\s+p[il1!]n", re.I),
    re.compile(r"c[o0]nf[il1!]rm\s+y[o0]ur\s+p[il1!]n", re.I),
    re.compile(r"[e3]nt[e3]r\s+y[o0]ur\s+p[il1!]n", re.I),
    re.compile(r"y[o0]ur\s+pa[s5]{2}w[o0]rd", re.I),
    re.compile(r"y[o0]ur\s+[o0]tp", re.I),
    re.compile(r"s[e3]cr[e3]t\s+c[o0]d[e3]", re.I),
    # ─── Wrong transaction / reversal threats ───
    re.compile(r"wr[o0]ng\s+transact[il1!][o0]n", re.I),
    re.compile(r"r[e3]v[e3]rsa[il1!]\s+transact[il1!][o0]n", re.I),
    re.compile(r"w[il1!][il1!]{2}\s+be\s+r[e3]v[e3]rs[e3]d", re.I),
    re.compile(r"s[e3]nt\s+[il1!]n\s+[e3]rr[o0]r", re.I),
    re.compile(r"s[e3]nt\s+by\s+m[il1!]stak[e3]", re.I),
    re.compile(r"k[il1!]nd[il1!]y\s+r[e3]turn", re.I),
    re.compile(r"s[e3]nd\s+back", re.I),
    # ─── Dear customer / greeting (MTN never greets) ───
    re.compile(r"d[e3]ar\s+(?:va[il1!]u[e3]d\s+)?cust[o0]m[e3]r", re.I),
    # ─── Prize / lottery / phishing ───
    re.compile(r"y[o0]u\s+(?:have\s+)?w[o0]n", re.I),
    re.compile(r"c[o0]ngratulat[il1!][o0]n", re.I),
    re.compile(r"c[il1!][il1!]ck\s+(?:h[e3]r[e3]|th[e3]\s+[il1!][il1!]nk)", re.I),
    re.compile(r"r[e3][il1!][e3]as[e3]\s+y[o0]ur\s+fund", re.I),
    # ─── Urgency / threat ───
    re.compile(r"fa[il1!][il1!]ur[e3]\s+t[o0]\s+c[o0]mp[il1!]y", re.I),
    re.compile(r"c[o0]ntact\s+us\s+[il1!]mm[e3]d[il1!]at[e3][il1!]y", re.I),
    re.compile(r"d[o0]n.?t\s+att[e3]mpt", re.I),
    re.compile(r"d[o0]\s+n[o0]t\s+att[e3]mpt", re.I),
    re.compile(r"syst[e3]m\s+upgrad[e3]", re.I),
    re.compile(r"ma[il1!]nt[e3]nanc[e3]\s+f[e3]{2}", re.I),
    re.compile(r"s[e3]cur[il1!]ty\s+a[il1!][e3]rt", re.I),
]


def _text_has_scam_signals(text: str) -> bool:
    """
    Check whether OCR text contains scam-like phrases.

    Uses OCR-tolerant regex patterns so that character-substitution
    errors (e.g. "bl0cked", "ver1fy", "acc0unt") don't hide scams.

    Returns True when at least 1 pattern matches.  The patterns are
    multi-word phrases (not single keywords), so a single accidental
    match on random OCR garbage is extremely unlikely.
    """
    if not text or len(text.strip()) < 15:
        return False
    # v6.5b: strip brackets/parens so "(BLOCKED)" matches block patterns
    clean = re.sub(r'[()[\]{}]', '', text)
    return any(pat.search(clean) for pat in _SCAM_SIGNAL_PATTERNS)


def _estimate_confidence(raw_text: str, cleaned_text: str) -> float:
    """
    Estimate a confidence score for the OCR extraction.

    Scoring (max 1.0):
      - Text length:      up to 0.25  (real MoMo = 80–400 chars)
      - MoMo keywords:    up to 0.35  (more keywords = more likely real)
      - Character quality: up to 0.20  (ratio of clean vs. garbage chars)
      - Structural cues:   up to 0.20  (field: value patterns, GHS amounts)

    Returns a float between 0.0 and 1.0.
    """
    if not cleaned_text:
        return 0.0

    score = 0.0
    lower_text = cleaned_text.lower()

    # ── Length ── (max 0.25)
    length = len(cleaned_text)
    if length >= 120:
        score += 0.25
    elif length >= 80:
        score += 0.20
    elif length >= 40:
        score += 0.12
    else:
        score += 0.05

    # ── MoMo keyword presence ── (max 0.35)
    # Weighted: strong indicators are worth more
    strong_keywords = ["transaction id", "ghs", "current balance",
                       "available balance", "mtn mobile money"]
    normal_keywords = ["received", "payment", "cash in", "cash out",
                       "fee", "mtn", "momo", "balance", "transfer",
                       "deposit", "withdrawal", "e-levy"]
    strong_hits = sum(1 for kw in strong_keywords if kw in lower_text)
    normal_hits = sum(1 for kw in normal_keywords if kw in lower_text)
    keyword_score = (strong_hits * 0.08) + (normal_hits * 0.04)
    score += min(keyword_score, 0.35)

    # ── Character quality ── (max 0.20)
    clean_chars = sum(1 for c in cleaned_text if c.isalnum() or c in " .,:-/()\n")
    total_chars = len(cleaned_text)
    if total_chars > 0:
        quality_ratio = clean_chars / total_chars
        score += quality_ratio * 0.20

    # ── Structural cues ── (max 0.20)
    # Real MoMo messages have "Field: Value" patterns and GHS amounts
    field_value_count = len(re.findall(r"\w+\s*:\s*\S", cleaned_text))
    ghs_amount_count = len(re.findall(r"GHS\s?[\d,]+\.?\d*", cleaned_text))
    struct_score = min(field_value_count * 0.03, 0.10) + min(ghs_amount_count * 0.05, 0.10)
    score += min(struct_score, 0.20)

    return round(min(score, 1.0), 2)


def _run_ocr_pass(
    img: "Image.Image",
    aggressive: bool = False,
    invert: bool = False,
) -> tuple[str, str, float, bool]:
    """
    Run one preprocessing + Tesseract pass and return results.

    Args:
        aggressive: Use heavier contrast + extra sharpening + PSM 6.
        invert:     Invert image pixels (for dark-background screenshots).

    Returns (raw_text, cleaned_text, confidence, usable).
    """
    processed = _preprocess_image(img.copy(), aggressive=aggressive, invert=invert)

    # PSM 6 = "assume a single uniform block of text" — good for MoMo screenshots
    # PSM 3 = "fully automatic page segmentation" — Tesseract default
    custom_config = "--psm 6" if aggressive else "--psm 3"
    raw_text = pytesseract.image_to_string(processed, lang="eng", config=custom_config)
    cleaned_text = _normalize_ocr_text(raw_text)
    confidence = _estimate_confidence(raw_text, cleaned_text)
    usable = _text_is_usable(cleaned_text)
    return raw_text, cleaned_text, confidence, usable


def extract_text(image_path: str) -> dict:
    """
    Extract text from a screenshot image.

    Phase 8 Part 3: Multi-strategy OCR — tries normal and aggressive
    preprocessing, then picks whichever produced higher confidence.
    This significantly improves results for low-contrast or noisy screenshots.

    Args:
        image_path: Absolute path to the saved screenshot file.

    Returns:
        {
            "success": bool,
            "extracted_text": str or None,
            "raw_ocr_text": str or None,
            "confidence": float,
            "low_confidence": bool,
            "usable": bool,
            "error": str or None
        }
    """
    logger.info("[OCR] Starting extraction: path=%s", os.path.basename(image_path))

    # Guard: check OCR availability
    if not _OCR_AVAILABLE:
        logger.warning("[OCR] Dependencies not installed — returning pending")
        return {
            "success": False,
            "extracted_text": None,
            "raw_ocr_text": None,
            "confidence": 0.0,
            "usable": False,
            "scam_detected": False,
            "context_flags": [],
            "contradictory_context": False,
            "error": "OCR dependencies (pytesseract, Pillow) not installed.",
        }

    # Guard: check file exists
    if not os.path.isfile(image_path):
        logger.error("[OCR] File not found: %s", image_path)
        return {
            "success": False,
            "extracted_text": None,
            "raw_ocr_text": None,
            "confidence": 0.0,
            "usable": False,
            "scam_detected": False,
            "context_flags": [],
            "contradictory_context": False,
            "error": "Image file not found.",
        }

    try:
        # 1. Load image once
        logger.debug("[OCR] Loading image…")
        img = Image.open(image_path)

        # 2. Detect dark background (MoMo dark mode)
        gray_check = img.convert("L")
        dark_bg = _is_dark_background(gray_check)
        if dark_bg:
            logger.info("[OCR] Dark background detected — will add inverted pass")

        # 3. Normal preprocessing pass
        logger.debug("[OCR] Pass 1 — normal preprocessing…")
        raw1, cleaned1, conf1, usable1 = _run_ocr_pass(img, aggressive=False)
        logger.info("[OCR] Pass 1 result: %d chars, conf=%.2f, usable=%s",
                    len(cleaned1), conf1, usable1)

        # 4. If first pass is already strong (conf >= 0.6 and usable), skip extra passes
        if conf1 >= 0.6 and usable1:
            raw_text, cleaned_text, confidence, usable = raw1, cleaned1, conf1, usable1
            logger.info("[OCR] Pass 1 sufficient — skipping extra passes")
        else:
            # Collect all candidate results for comparison
            candidates = [("pass1", raw1, cleaned1, conf1, usable1)]

            # 5. Aggressive preprocessing pass (heavier contrast, double sharpen, psm 6)
            logger.debug("[OCR] Pass 2 — aggressive preprocessing…")
            raw2, cleaned2, conf2, usable2 = _run_ocr_pass(img, aggressive=True)
            logger.info("[OCR] Pass 2 result: %d chars, conf=%.2f, usable=%s",
                        len(cleaned2), conf2, usable2)
            candidates.append(("pass2-aggressive", raw2, cleaned2, conf2, usable2))

            # 6. Inverted pass for dark backgrounds (only when detected or both passes poor)
            if dark_bg or (not usable1 and not usable2):
                logger.debug("[OCR] Pass 3 — inverted (dark-mode) preprocessing…")
                raw3, cleaned3, conf3, usable3 = _run_ocr_pass(img, aggressive=True, invert=True)
                logger.info("[OCR] Pass 3 result: %d chars, conf=%.2f, usable=%s",
                            len(cleaned3), conf3, usable3)
                candidates.append(("pass3-inverted", raw3, cleaned3, conf3, usable3))

            # Pick the best candidate: prefer usable first, then highest confidence
            best = max(candidates, key=lambda c: (c[4], c[3]))  # (usable, confidence)
            label, raw_text, cleaned_text, confidence, usable = best
            logger.info("[OCR] Selected %s (conf=%.2f, usable=%s)", label, confidence, usable)

        # 5. Compute low-confidence flag
        low_confidence = confidence < 0.35

        # 6. Check if we got meaningful text
        if len(cleaned_text) < 5:
            logger.warning("[OCR] Extracted text too short (%d chars) — likely failed", len(cleaned_text))
            return {
                "success": False,
                "extracted_text": cleaned_text if cleaned_text else None,
                "raw_ocr_text": raw_text.strip() if raw_text else None,
                "confidence": confidence,
                "low_confidence": True,
                "usable": False,
                "scam_detected": False,
                "context_flags": [],
                "contradictory_context": False,
                "error": "OCR extracted very little text. The image may not contain readable text.",
            }

        if not usable:
            logger.info("[OCR] Text extracted (%d chars) but no MoMo keywords found — marked not usable",
                        len(cleaned_text))

        # Phase 9: detect scam-like language even when text isn't a MoMo message
        scam_detected = _text_has_scam_signals(cleaned_text)
        if scam_detected:
            logger.info("[OCR] Scam-signal phrases detected in OCR text")

        # v6.5: detect multi-message scam context combinations
        # Returns flags like "contradictory_context", "cash_receive_plus_reversal", etc.
        context_flags = _detect_screenshot_context_flags(cleaned_text)
        if context_flags:
            logger.info("[OCR] Screenshot context flags detected: %s", context_flags)

        logger.info("[OCR] Extraction complete: %d chars, conf=%.2f, low_conf=%s, usable=%s, scam=%s",
                    len(cleaned_text), confidence, low_confidence, usable, scam_detected)
        return {
            "success": True,
            "extracted_text": cleaned_text,
            "raw_ocr_text": raw_text.strip() if raw_text else None,
            "confidence": confidence,
            "low_confidence": low_confidence,
            "usable": usable,
            "scam_detected": scam_detected,
            "context_flags": context_flags,
            "contradictory_context": "contradictory_context" in context_flags,
            "error": None,
        }

    except Exception as e:
        logger.exception("[OCR] Extraction failed: %s", e)
        return {
            "success": False,
            "extracted_text": None,
            "raw_ocr_text": None,
            "confidence": 0.0,
            "low_confidence": True,
            "usable": False,
            "scam_detected": False,
            "context_flags": [],
            "contradictory_context": False,
            "error": f"OCR processing error: {type(e).__name__}",
        }

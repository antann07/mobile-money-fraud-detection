# Mobile Money Fraud Detection — Pilot Acceptance Checklist

**System:** Flask backend (v6.4-rule-based) + React/Vite frontend  
**Target:** Manual pre-deployment sign-off for pilot release  
**Format:** Each item is a manual step. Mark ✅ PASS / ❌ FAIL / ⚠️ SKIP.  
**Go/No-Go rule:** All HIGH items must be PASS. No more than 3 MEDIUM items may be FAIL.

---

## Section 1 — Authentication Flow

> **Prerequisite:** Backend running, DB seeded with at least one regular user and one admin user.

| #    | Step                                                                                                           | Expected Result                                                                                                                                                                | Sev  | Result |
| ---- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---- | ------ |
| 1.1  | Register a new account with valid unique email + password ≥8 chars                                             | 201 response, `success: true`. Frontend redirects to `/login`.                                                                                                                 | MED  |        |
| 1.2  | Attempt to register with an already-used email                                                                 | 409 or 400 response, error message shown on form, no redirect.                                                                                                                 | MED  |        |
| 1.3  | Log in with valid credentials                                                                                  | 200 response, JWT stored in browser (localStorage/cookie), redirects to `/dashboard`.                                                                                          | HIGH |        |
| 1.4  | Log in with wrong password — repeat exactly **5 times**                                                        | After the 5th failure, next login attempt (correct password) returns a lockout error. Account must remain locked for 15 minutes. (`MAX_FAILED_LOGINS=5`, `LOCKOUT_MINUTES=15`) | HIGH |        |
| 1.5  | After the 15-minute lockout window elapses, log in with correct password                                       | Login succeeds; JWT issued.                                                                                                                                                    | HIGH |        |
| 1.6  | Access a protected route (`/api/message-checks/history`) without a `Authorization: Bearer` header              | Response: `401` with `"Missing or malformed Authorization header."`                                                                                                            | HIGH |        |
| 1.7  | Tamper with a valid JWT (change one character in the payload)                                                  | Response: `401` with `"Token is invalid."`                                                                                                                                     | HIGH |        |
| 1.8  | Simulate an expired token (advance system clock >24h, or set `TOKEN_EXPIRY_HOURS=0` briefly)                   | Response: `401` with `"Token has expired. Please login again."` — Frontend shows logged-out state.                                                                             | HIGH |        |
| 1.9  | Click "Forgot Password" and submit a valid email                                                               | `POST /api/auth/forgot-password` returns `200`, **no token in response body**. Reset token appears only in server console log.                                                 | HIGH |        |
| 1.10 | Copy token from server console, navigate to `/reset-password?token=<TOKEN>&email=<EMAIL>`, submit new password | `POST /api/auth/reset-password` returns `200`, user can now log in with new password. Old password rejected.                                                                   | HIGH |        |
| 1.11 | Attempt reset with an expired or wrong token                                                                   | Returns `400`/`401` error, password is unchanged.                                                                                                                              | HIGH |        |
| 1.12 | Log out (clear token from browser) then press browser Back button                                              | Redirected to `/login`, protected pages not accessible.                                                                                                                        | MED  |        |

---

## Section 2 — Fraud Verdict / Result States

> Test via the `CheckMessage` page (SMS paste tab). Paste each message and confirm full result card.

### 2A — Core label rendering

| #   | Input Message                                                                                                              | Expected Label                          | Expected UI                                                                      | Sev  | Result |
| --- | -------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- | -------------------------------------------------------------------------------- | ---- | ------ |
| 2.1 | `You have received GHS 50.00 from 0241234567 John Doe. Your new balance is GHS 150.00. Transaction ID: A123456789. - MoMo` | **Verified** (genuine)                  | Green pill, ✅ icon, guidance says "safe to proceed"                             | HIGH |        |
| 2.2 | A real-looking MTN message but with "kindly return" + reversal language added                                              | **Potential Fraud** (likely_fraudulent) | Red pill, 🚨 icon, guidance says "don't send money, don't share PIN"             | HIGH |        |
| 2.3 | A message that triggers no strong genuine or fraud signals (ambiguous)                                                     | **Needs Review** (suspicious)           | Amber pill, ⚠️ icon, guidance says "check \*170#, don't call numbers in message" | HIGH |        |
| 2.4 | An outgoing/debit SMS: `GHS 20.00 has been deducted from your MoMo...`                                                     | **Not Analysed** (out_of_scope)         | Grey pill, ℹ️ icon, `scope_reason` explanation shown                             | MED  |        |

### 2B — API contract checks (DevTools → Network tab)

| #   | Check                                                               | Expected                                                                                                | Sev  | Result |
| --- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ---- | ------ |
| 2.5 | Response JSON for any verdict contains all required keys            | `success`, `predicted_label`, `confidence_score`, `explanation`, `risk_score`, `input_method`, `is_mtn` | HIGH |        |
| 2.6 | `out_of_scope` response additionally contains                       | `scope_reason` key present                                                                              | MED  |        |
| 2.7 | `confidence_score` is between 0.0 and 1.0                           | No values above 1.0 or below 0.0                                                                        | MED  |        |
| 2.8 | `is_mtn` field is `true` for MTN-branded message, `false` otherwise | Matches message content                                                                                 | LOW  |        |

### 2C — Known defects (disclose in pilot notes, do not block on)

| DEF     | Description                                                                                                                                                                                       | Sev  | Workaround                                                                        |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- | --------------------------------------------------------------------------------- |
| DEF-002 | Hard scam language (`do not spend`, `call_phone_number`) on a partial/no-balance message lands at `suspicious` instead of `likely_fraudulent` — composite score sits on threshold boundary (0.45) | HIGH | Pilot users should treat `suspicious` as a warning                                |
| DEF-004 | OCR path can give `genuine` to a reversal scam if message has ≥2 genuine structural markers — OCR trust bonus (-0.40) absorbs the scam penalties                                                  | HIGH | Disclose in pilot UX: "OCR results should be confirmed with SMS text if possible" |
| DEF-005 | OCR path gives `suspicious` for PIN-harvesting message instead of `likely_fraudulent`                                                                                                             | HIGH | Same disclosure as DEF-004                                                        |
| DEF-007 | Wrong currency code (`GHC` instead of `GHS`) still scores `genuine` — `wrong_currency` is not a Stage B hard signal                                                                               | MED  | Do not use DEF-007 scenario in pilot demo                                         |

---

## Section 3 — OCR vs Pasted-Text Consistency

> Use the same message content for both tabs to confirm parity. Use a clean PNG screenshot of an MTN MoMo notification.

| #   | Step                                                                    | Expected                                                                                               | Sev  | Result |
| --- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ---- | ------ |
| 3.1 | Paste a genuine MTN message (text tab) → note verdict + confidence      | `genuine`, confidence ≥ 0.80                                                                           | HIGH |        |
| 3.2 | Upload a clear screenshot of the same message (screenshot tab)          | Same `genuine` verdict. OCR confidence pill shown. `input_method: screenshot_ocr`.                     | HIGH |        |
| 3.3 | Verify the OCR confidence pill label is visible on the result card      | Either "High Confidence OCR", "Medium Confidence OCR", or "Low Confidence OCR"                         | MED  |        |
| 3.4 | Upload an image with status-bar noise (signal/battery icons visible)    | Verdict not degraded to suspicious purely because of status-bar characters — noise suppression working | MED  |        |
| 3.5 | Upload an unsupported file type (e.g. `.pdf` or `.gif`)                 | `400` error, clear rejection message on UI, no server crash                                            | HIGH |        |
| 3.6 | Upload a file larger than 5 MB                                          | `413` or `400` error, rejected before processing, error shown to user                                  | HIGH |        |
| 3.7 | Upload an image with homoglyph substitutions (e.g. `0` → `O` in amount) | Verdict should not degrade; homoglyph normalisation absorbs soft noise                                 | MED  |        |
| 3.8 | If pytesseract is NOT installed on server — submit screenshot           | Graceful degradation: `503` or meaningful error, no unhandled exception, no 500 crash                  | HIGH |        |

---

## Section 4 — Responsiveness

> Test at each breakpoint below: desktop (1280px), tablet (768px), mobile (375px). Use browser DevTools device emulation if needed.

| #    | Page                           | Element to verify                                             | Sev  | Result |
| ---- | ------------------------------ | ------------------------------------------------------------- | ---- | ------ |
| 4.1  | `/check`                       | SMS/OCR tab switcher renders horizontally, full width         | MED  |        |
| 4.2  | `/check`                       | Result card is not clipped or overflowed at 375px             | HIGH |        |
| 4.3  | `/check`                       | Screenshot drag-drop zone is usable at 375px (tap uploads)    | MED  |        |
| 4.4  | `/history`                     | Message list rows are readable at 375px, no horizontal scroll | MED  |        |
| 4.5  | `/history/<id>`                | Detail page explanation text wraps properly                   | MED  |        |
| 4.6  | `/login` & `/register`         | Form fields full-width, submit button accessible on mobile    | HIGH |        |
| 4.7  | `/forgot-password`             | Single-field form centred, full-width at 375px                | MED  |        |
| 4.8  | Sidebar (authenticated layout) | Collapses to hamburger/drawer on mobile                       | MED  |        |
| 4.9  | All verdict pills              | Text doesn't truncate mid-word on narrow screens              | LOW  |        |
| 4.10 | Admin `/review-queue`          | Queue rows readable at 768px (tablet)                         | MED  |        |

---

## Section 5 — UI / HCI Consistency

> Visual and interaction quality — no DevTools required.

| #    | Check                                                                       | Expected                                                                                                        | Sev  | Result |
| ---- | --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ---- | ------ |
| 5.1  | Every page that makes an API call shows a loading state                     | Spinner or skeleton while awaiting response; no blank flash                                                     | MED  |        |
| 5.2  | Submitting SMS/OCR check with empty input                                   | Inline validation error before API call; button disabled or error message shown                                 | HIGH |        |
| 5.3  | All 4 verdict pill colours are visually distinct                            | Green (genuine), Amber (suspicious), Red (likely_fraudulent), Grey (out_of_scope)                               | HIGH |        |
| 5.4  | Verdict guidance text is actionable (not generic)                           | `suspicious` guidance says "check \*170#…"; `likely_fraudulent` says "do not send money, do not share your PIN" | HIGH |        |
| 5.5  | After submitting a check on `/check`, page auto-scrolls to result card      | Result card visible without manual scroll, especially on mobile                                                 | MED  |        |
| 5.6  | Copy button on result card copies explanation text                          | Clipboard populated; button shows brief "Copied!" confirmation                                                  | LOW  |        |
| 5.7  | MoMo chip rendered when `is_mtn: true`                                      | Branded chip visible on result card                                                                             | LOW  |        |
| 5.8  | `out_of_scope` result card shows `scope_reason`                             | User sees explanation of why message wasn't analysed                                                            | MED  |        |
| 5.9  | Clicking a row in `/history` navigates to `/history/<id>` with correct data | Detail matches list row, no blank page                                                                          | HIGH |        |
| 5.10 | Auth error messages are human-readable                                      | No raw stack traces, `[object Object]`, or 500 error codes shown to user                                        | HIGH |        |
| 5.11 | `ForgotPassword` page: after submit, user sees confirmation message         | "Check your email for a reset link" shown regardless of whether email exists (no user enumeration)              | HIGH |        |
| 5.12 | `ResetPassword` page: after expired/invalid token, user sees helpful error  | "This reset link has expired or is invalid" + link back to forgot-password                                      | MED  |        |

---

## Section 6 — Admin Workflow

> Requires a user with `role = admin` in the database.

| #   | Step                                                                    | Expected                                                                                       | Sev  | Result |
| --- | ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ---- | ------ |
| 6.1 | Log in as admin. Navigate to `/review-queue`.                           | Flagged queue loads. Only `suspicious` and `likely_fraudulent` messages appear.                | HIGH |        |
| 6.2 | Attempt to access `/review-queue` while logged in as a **regular user** | Blocked — `403 Admin access required.` on API, frontend redirects or shows access-denied state | HIGH |        |
| 6.3 | Click a flagged item → navigate to `/review-queue/<id>`                 | Detail shows full message text, current verdict, confidence score, all explanation flags       | HIGH |        |
| 6.4 | Submit a review label of `genuine`                                      | `POST /api/reviews/<id>` returns `200`. Status updated to `confirmed_genuine`.                 | HIGH |        |
| 6.5 | Submit a review label of `likely_fraudulent`                            | Status updated to `confirmed_fraud`.                                                           | HIGH |        |
| 6.6 | Submit a review label of `escalated`                                    | Status updated to `escalated`.                                                                 | MED  |        |
| 6.7 | Attempt to submit an invalid reviewer label (e.g. `"approved"`)         | `400` error returned; status not changed.                                                      | MED  |        |
| 6.8 | Confirm reviewed item no longer appears in the pending queue            | After review, item removed from `GET /api/reviews/flagged` response                            | HIGH |        |
| 6.9 | Non-admin bearer token on `GET /api/reviews/flagged`                    | `403` with `"Admin access required."`                                                          | HIGH |        |

---

## Section 7 — Deployment Readiness Basics

> Run `ProductionConfig.validate()` output — it auto-checks most of these on startup.

### 7A — Environment blockers (all MUST pass before go-live)

| #   | Check                                                              | Command / Method               | Pass Condition                                    | Sev  |
| --- | ------------------------------------------------------------------ | ------------------------------ | ------------------------------------------------- | ---- |
| 7.1 | `SECRET_KEY` is not the default                                    | `echo $SECRET_KEY`             | Not `"dev-secret-key-change-in-production"`       | HIGH |
| 7.2 | `SECRET_KEY` is at least 32 characters                             | `echo -n $SECRET_KEY \| wc -c` | ≥ 32                                              | HIGH |
| 7.3 | `CORS_ORIGINS` is not `"*"`                                        | `echo $CORS_ORIGINS`           | Explicit list of allowed frontend origins         | HIGH |
| 7.4 | `DATABASE_URL` points to PostgreSQL                                | `echo $DATABASE_URL`           | Starts with `postgresql://` — **not** `sqlite://` | HIGH |
| 7.5 | `FLASK_DEBUG=0` / not set to `True`                                | `echo $FLASK_DEBUG`            | `0` or absent                                     | HIGH |
| 7.6 | `FLASK_ENV=production`                                             | `echo $FLASK_ENV`              | `production`                                      | HIGH |
| 7.7 | `TOKEN_EXPIRY_HOURS` ≤ 72                                          | `echo $TOKEN_EXPIRY_HOURS`     | ≤ 72 (default 24 is fine)                         | MED  |
| 7.8 | `ProductionConfig.validate()` prints no CRITICAL errors on startup | Server log on startup          | No `[CONFIG-CRITICAL]` lines                      | HIGH |

### 7B — Container / Service checks

| #    | Check                                                                                              | Expected                                                                          | Sev  | Result |
| ---- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ---- | ------ |
| 7.9  | All services start cleanly with `docker-compose up`                                                | No crash loops; all containers reach healthy state                                | HIGH |        |
| 7.10 | `GET /api/health` (or equivalent) returns `200`                                                    | Health endpoint responsive                                                        | MED  |        |
| 7.11 | `uploads/screenshots/` directory is writable by the backend process                                | Screenshot upload succeeds end-to-end                                             | HIGH |        |
| 7.12 | DB migrations applied — all tables exist (`users`, `message_checks`, `fraud_reviews`, `audit_log`) | `\dt` in psql shows all tables                                                    | HIGH |        |
| 7.13 | pytesseract and tesseract-ocr are installed in the backend container                               | `tesseract --version` exits 0 inside container (or graceful-degradation accepted) | MED  |        |
| 7.14 | ML model file(s) present and loadable at startup                                                   | No `FileNotFoundError` in logs; advisory scorer initialises                       | MED  |        |
| 7.15 | Frontend build artefacts served by nginx — `index.html` loads on root URL                          | No 404 on `/`                                                                     | HIGH |        |
| 7.16 | nginx proxy correctly forwards `/api/*` to Flask backend                                           | `/api/auth/login` reachable from browser without CORS error                       | HIGH |        |

### 7C — Security posture checks

| #    | Check                                                                      | Expected                                                                   | Sev  | Result |
| ---- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ---- | ------ |
| 7.17 | No DEBUG stacktraces leaking to HTTP responses in production               | Trigger a 500 (temporarily) — response must not contain Python traceback   | HIGH |        |
| 7.18 | Password reset tokens never appear in API response bodies                  | `POST /api/auth/forgot-password` response JSON — no `token` field          | HIGH |        |
| 7.19 | `Authorization: Bearer` tokens not logged to persistent log files          | Grep server logs for `Bearer` — should not appear as literal header values | MED  |        |
| 7.20 | File upload allows only `.png/.jpg/.jpeg/.webp` with magic-byte validation | Submit a `.php` file renamed to `.jpg` — must be rejected                  | HIGH |        |

---

## Go / No-Go Decision Matrix

| Category                           | Condition                                     | Decision                                      |
| ---------------------------------- | --------------------------------------------- | --------------------------------------------- |
| Any Section 7A item FAIL           | Env var or config blocker unresolved          | **BLOCK** — do not deploy                     |
| Any HIGH item FAIL in Sections 1-6 | Core auth, verdict, admin, or security broken | **BLOCK** — fix before pilot                  |
| DEF-004 or DEF-005 unresolved      | OCR scam bypass active                        | **CONDITIONAL** — deploy with user disclosure |
| DEF-002 / DEF-003 unresolved       | Threshold boundary gap active                 | **CONDITIONAL** — deploy with pilot note      |
| 3 or fewer MEDIUM items FAIL       | Minor UX/consistency issues                   | **PROCEED** — log as post-pilot backlog       |
| All HIGHs pass, DEFs disclosed     | Acceptable pilot baseline                     | **GO** ✅                                     |

---

## Pilot Disclosure Notes (include in pilot briefing)

1. **OCR reliability:** Screenshot analysis is best-effort. If the OCR result is `suspicious` or `genuine` but the user suspects fraud, they should paste the SMS text directly for a more reliable verdict.
2. **Threshold boundary:** Certain sophisticated scam messages that mimic genuine structure may land at `suspicious` rather than `likely_fraudulent`. Treat `suspicious` results with the same caution as `likely_fraudulent` during the pilot.
3. **Currency code:** Messages using `GHC` instead of `GHS` will not be penalised; advise pilot users to check the currency symbol manually.
4. **Scope:** This system analyses **incoming** MoMo credit notifications only. Outgoing/debit SMS messages will show "Not Analysed" — this is expected behaviour.

---

_Generated against: `MODEL_VERSION = "v6.4-rule-based"` | QA suite: 72/82 pass | 10 known defects documented in defect register._

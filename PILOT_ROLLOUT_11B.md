# Phase 11B — Pilot Rollout Package

**System:** TONYKAY MTN Mobile Money Fraud Detection  
**Status:** GO (Phase 11A passed 19/19)  
**Pilot scope:** 3–10 invited users, controlled environment  
**Date prepared:** 2026-04-04

---

## 1. Controlled Pilot Rollout Checklist

Complete each item before inviting the first pilot user.

| #   | Task                                                                                                           | Owner | Done |
| --- | -------------------------------------------------------------------------------------------------------------- | ----- | ---- |
| 1   | Confirm all 3 Docker containers are running and healthy                                                        | Admin | ☐    |
| 2   | Verify `.env` has production secrets (not defaults)                                                            | Admin | ☐    |
| 3   | Create 1 admin account and 1 test customer account                                                             | Admin | ☐    |
| 4   | Walk through the full user flow once yourself (register → login → SMS check → screenshot check → view history) | Admin | ☐    |
| 5   | Confirm database backups are possible (`docker exec ... pg_dump`)                                              | Admin | ☐    |
| 6   | Share the access URL with pilot users only (do not post publicly)                                              | Admin | ☐    |
| 7   | Send each pilot user the Pilot User Testing Plan (Section 2 below)                                             | Admin | ☐    |
| 8   | Set a pilot window (recommended: 3–5 days) with a clear end date                                               | Admin | ☐    |
| 9   | Bookmark the admin monitoring checklist (Section 4) for daily use                                              | Admin | ☐    |
| 10  | Create a shared channel for pilot feedback (WhatsApp group, Google Form, or shared doc)                        | Admin | ☐    |

**Go-live command (already done, but for reference):**

```
docker compose up -d
```

**Quick health check:**

```
curl http://localhost:3000/api/health
```

---

## 2. Pilot User Testing Plan

Give this to each pilot tester. Keep it simple.

---

### Welcome, Pilot Tester!

You are testing the **MTN Mobile Money Fraud Detection System**. Your job is to try the app like a normal user and report anything confusing, broken, or wrong.

**Access URL:** `http://<provided-by-admin>:3000`

#### Step-by-step tasks

| #   | What to do                                                                                                                                                                                                                  | What to look for                                               | Notes                                    |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------- |
| 1   | **Register** a new account using your email, a strong password (8+ chars, upper+lower+digit+special), a Ghana phone number, and your name.                                                                                  | Registration succeeds. You see a success message.              | If it fails, write down the exact error. |
| 2   | **Log in** with the account you just created.                                                                                                                                                                               | You reach the dashboard.                                       |                                          |
| 3   | **Check a genuine SMS.** Paste this into the SMS check box: `You have received GHS 50.00 from Kwame Asante 0241234567. Your new balance is GHS 120.00. Transaction ID: TXN123456789. Thank you for using MTN Mobile Money.` | The system should mark it as genuine or verified.              | Write down what label you see.           |
| 4   | **Check a suspicious SMS.** Paste this: `URGENT: Your MTN MoMo account has been compromised! Click http://bit.ly/mtn-verify to verify your account immediately or your funds will be frozen. Enter your PIN to confirm.`    | The system should flag it as suspicious or fraudulent.         | Write down what label you see.           |
| 5   | **Check a random/unrelated SMS.** Paste this: `Hey, are you coming for the party tonight?`                                                                                                                                  | The system should mark it out-of-scope or show a clear result. |                                          |
| 6   | **Upload a screenshot** of a real or sample MoMo notification (take a photo of your phone or use a test image).                                                                                                             | The system extracts text and shows a result.                   | Note if OCR text is accurate.            |
| 7   | **View your history.** Go to history/dashboard after the checks above.                                                                                                                                                      | You should see all your previous checks saved.                 | Count them — should be at least 4.       |
| 8   | **Log out and log back in.**                                                                                                                                                                                                | History still shows your previous results.                     |                                          |
| 9   | **Try something wrong on purpose** (empty SMS, very long text, wrong file type for screenshot).                                                                                                                             | The system should show a clear error, not crash.               |                                          |

#### After testing, report:

- What worked well
- What was confusing
- Any errors you saw (screenshot or exact text)
- How long each step took (roughly)
- Would you trust this system with your real MoMo messages? Why or why not?

**Send your feedback to:** `<admin provides channel>`

---

## 3. Pilot Issue Log Template

Use this table to track every issue reported during the pilot. One row per issue.

| ID    | Date | Reporter | Step# | Summary | Severity | Status | Fix Notes |
| ----- | ---- | -------- | ----- | ------- | -------- | ------ | --------- |
| P-001 |      |          |       |         |          |        |           |
| P-002 |      |          |       |         |          |        |           |
| P-003 |      |          |       |         |          |        |           |

**Severity levels:**

- **Critical** — System crashes, data lost, security issue, complete blocker
- **High** — Feature doesn't work, wrong fraud label on obvious case
- **Medium** — Confusing UI, slow response, minor mislabel
- **Low** — Cosmetic, typo, nice-to-have improvement

**Status values:**

- `New` → `Triaged` → `Fixing` → `Fixed` → `Verified`
- Or: `Won't Fix` / `Deferred`

---

## 4. Admin Monitoring Checklist

Run these checks **once daily** during the pilot (takes ~5 minutes).

| #   | Check                             | Command / Action                                                                                                          | Healthy If                             |
| --- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| 1   | All containers running            | `docker compose ps`                                                                                                       | All 3 show "Up" + "healthy"            |
| 2   | No restart loops                  | `docker compose ps` → check STATUS                                                                                        | No "(restarting)" states               |
| 3   | Backend responds                  | `curl http://localhost:3000/api/health`                                                                                   | Returns `{"status":"ok"}`              |
| 4   | Database accessible               | `docker exec mobile-money-fraud-detection-db-1 psql -U momo -d fraud_detection -c "SELECT count(*) FROM users;"`          | Returns a number, no error             |
| 5   | Check count growing               | `docker exec mobile-money-fraud-detection-db-1 psql -U momo -d fraud_detection -c "SELECT count(*) FROM message_checks;"` | Number increases as testers use system |
| 6   | No disk space issues              | `docker system df`                                                                                                        | Volumes not filling up                 |
| 7   | Backend error logs                | `docker compose logs --tail=50 backend \| findstr /i "error exception traceback"`                                         | No recurring errors                    |
| 8   | Review flagged items              | Log in as admin → `/reviews/flagged` or call `GET /api/reviews/flagged`                                                   | Review any suspicious-flagged checks   |
| 9   | Spot-check a recent result        | Pick a recent message_check from DB and verify the label makes sense                                                      | Labels match expectations              |
| 10  | Take a DB backup (every 2–3 days) | `docker exec mobile-money-fraud-detection-db-1 pg_dump -U momo fraud_detection > backup_YYYYMMDD.sql`                     | File is non-empty                      |

**If something is wrong:**

1. Check `docker compose logs backend --tail=100` for details
2. Try `docker compose restart backend` for transient errors
3. Log the issue in the Issue Log (Section 3)
4. If critical: `docker compose down` → fix → `docker compose up -d`

---

## 5. Known Pilot Cautions & Limitations

Share these with pilot testers so expectations are set correctly.

| #   | Limitation                                                                                                                              | Impact                                                                     | Workaround                                                                             |
| --- | --------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| 1   | **No trained ML model yet for SMS classification** — the system uses rule-based heuristics (v6.5-rule-based) not a production ML model. | Some edge-case labels may be wrong. Obvious fraud/genuine cases work well. | Review labels manually; don't rely on the system as sole fraud authority during pilot. |
| 2   | **OCR depends on image quality** — blurry, dark, or partial screenshots may extract garbled text.                                       | Incorrect or incomplete text extraction → wrong label.                     | Use clear, well-lit screenshots. Crop to just the notification area.                   |
| 3   | **Rate limiting is active** — API: 30 req/min, screenshot upload: 5 req/min per IP.                                                     | Rapid-fire testing may hit 429 errors.                                     | Wait a few seconds between requests. Normal use will never hit this.                   |
| 4   | **Single-server deployment** — no load balancing or failover.                                                                           | If the server goes down, everything is down.                               | Admin monitors daily; restart if needed.                                               |
| 5   | **No email verification** — accounts are created without email confirmation.                                                            | Anyone with the URL can register.                                          | Share URL only with invited pilot testers.                                             |
| 6   | **No password recovery email** — forgot-password endpoint exists but does not send real emails.                                         | Users who forget passwords need admin help.                                | Admin can reset via DB if needed.                                                      |
| 7   | **Screenshot uploads stored on server volume** — not cloud-backed.                                                                      | If Docker volumes are deleted, uploads are lost.                           | Admin keeps DB backups.                                                                |
| 8   | **JWT tokens expire after 24 hours** — configurable via `TOKEN_EXPIRY_HOURS`.                                                           | Users must re-login daily.                                                 | This is intentional for security.                                                      |

---

## 6. Feedback Triage Workflow

How to collect feedback, decide what matters, and act on it.

```
┌─────────────────────────────────┐
│  1. COLLECT                     │
│  Pilot users submit feedback    │
│  via shared channel daily       │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│  2. LOG                         │
│  Admin adds each item to the    │
│  Issue Log (Section 3) with     │
│  severity + step number         │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│  3. TRIAGE (daily, end of day)  │
│                                 │
│  Critical → Fix immediately     │
│  High     → Fix within 24 hrs  │
│  Medium   → Batch for end of   │
│             pilot window        │
│  Low      → Log, defer to      │
│             post-pilot backlog  │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│  4. FIX & VERIFY                │
│  - Fix in code                  │
│  - Rebuild: docker compose      │
│    up --build -d                │
│  - Re-run the failing test      │
│  - Mark issue as "Fixed"        │
│  - Ask reporter to verify       │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│  5. PILOT CLOSE-OUT             │
│  At end of pilot window:        │
│  - Count: total issues, fixed,  │
│    deferred                     │
│  - Survey: "Would you use this  │
│    for real MoMo messages?"     │
│  - Decision:                    │
│    ✓ Expand pilot               │
│    ✓ Fix blockers then expand   │
│    ✗ Major rework needed        │
└─────────────────────────────────┘
```

### Fix priority decision matrix

|                                                   | Users affected: 1    | Users affected: Many                          |
| ------------------------------------------------- | -------------------- | --------------------------------------------- |
| **Blocks core flow** (can't check SMS/screenshot) | High — fix in 24h    | Critical — fix now                            |
| **Wrong result** (mislabel)                       | Medium — log pattern | High — check if rule-based logic needs update |
| **Confusing UX** (unclear message, layout issue)  | Low — defer          | Medium — batch fix                            |
| **Cosmetic** (typo, color, spacing)               | Low — defer          | Low — defer                                   |

### Recommended feedback collection methods (pick one)

| Method                  | Best for                                                 | Setup time |
| ----------------------- | -------------------------------------------------------- | ---------- |
| **WhatsApp group**      | Small pilot (3–5 people), informal                       | 2 min      |
| **Google Form**         | Structured responses, easy to analyze                    | 15 min     |
| **Shared Google Sheet** | Collaborative, pilot testers can see each other's issues | 10 min     |
| **GitHub Issues**       | Technical team, integrates with code workflow            | 5 min      |

---

_End of Phase 11B Pilot Rollout Package_

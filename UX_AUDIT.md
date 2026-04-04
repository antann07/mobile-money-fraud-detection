# MTN MoMo Fraud Detection — Fintech UX/HCI Audit & Improvement Plan

> Audience: Student project team preparing for polished demo / controlled deployment
> Scope: 5 key pages — no full redesign, incremental refinements within existing theme

---

## 1. Overall UX Assessment

### What's Working Well

- **Design system is consistent**: The CSS tokens (colors, radii, shadows, spacing) create a cohesive, modern look across all pages. The navy/blue/slate palette is appropriate for fintech—serious without being cold.
- **Verdict theming is strong**: Green/amber/red visual lanes for genuine/suspicious/fraudulent are clear and well-implemented (accent bars, tinted backgrounds, pill colors).
- **Component architecture is clean**: `PageLayout`, shared `pillClass()`/`verdictIcon()` functions, and the consistent card/table/message-box patterns make the app feel unified.
- **Drag-and-drop upload**: The screenshot upload with preview, file-size validation, and OCR confidence display is genuinely above demo-quality.
- **Stats strips**: Summary cards at the top of History and Review Queue give quick context before the user dives into the table. Good pattern.

### Core HCI Problems (Across All Pages)

| Problem                                 | Impact                 | Details                                                                                                                                                                                                           |
| --------------------------------------- | ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Technical language exposed to users** | Trust erosion          | Labels like `likely_fraudulent`, `format_risk_score`, `behavior_risk_score`, `parser_confidence` belong in an API response, not a user interface. Real fintech apps never show raw model internals.               |
| **No "what should I do?" guidance**     | Decision paralysis     | Verdicts tell users _what_ the system found but never _what to do about it_. A suspicious result should include clear recommended actions.                                                                        |
| **Numeric scores without context**      | Cognitive overload     | Risk scores like `0.23` or `0.71` are meaningless to a non-technical user. They need plain-English calibration ("Low risk", "High risk") alongside or instead of the number.                                      |
| **Emoji as icons**                      | Semi-professional feel | Emoji render differently across OS/browsers and feel casual. For a fintech demo this is acceptable, but replacing key emojis with SVG icons (or at minimum a consistent emoji set) would raise perceived quality. |
| **No progressive disclosure**           | Information overload   | Every page shows all fields at once. The verdict card, risk breakdown, extracted fields, ML badge, and model version all compete for attention simultaneously.                                                    |
| **Duplicate helper functions**          | Maintenance risk       | `pillClass()`, `verdictIcon()`, `verdictClass()`, `riskColor()` are copy-pasted across 4 files. One change means 4 edits.                                                                                         |

---

## 2. Page-by-Page Audit & Improvements

---

### 2A. Check Message Page (`CheckMessage.jsx`)

**Current state**: Functional SMS/screenshot dual-tab form with inline result display. This is the core page — its UX determines whether a user trusts the system.

#### Problems Found

| #   | Issue                                                                                                                                                                                   | Category          | Severity |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | -------- |
| 1   | **Placeholder text is too long** — the SMS box shows a 3-line example that makes the textarea look pre-filled                                                                           | Clarity           | Medium   |
| 2   | **"Select Wallet" is confusing** — users don't understand why checking an SMS requires choosing a wallet                                                                                | Mental model      | High     |
| 3   | **No guidance on what makes a good screenshot** — users will submit blurry, cropped, or wrong images                                                                                    | Task guidance     | High     |
| 4   | **Result card appears below the form with no transition** — after clicking "Verify", the user may not realize the result loaded (especially on small screens where it's below the fold) | Visibility        | High     |
| 5   | **Verdict headings are passive** — "Some details need attention" doesn't say _which_ details or _what_ to do                                                                            | Action guidance   | High     |
| 6   | **Risk score labels are cryptic** — "Balance Check: 0.23" means nothing to the user                                                                                                     | Cognitive load    | High     |
| 7   | **ML badge is distracting** — "Agrees with rules" / "Differs from rules" is internal model debugging, not useful to end users                                                           | Trust             | Medium   |
| 8   | **"Model: v6.1-hybrid-calibrated" in footer** — model version is developer info, not user info                                                                                          | Audience mismatch | Low      |
| 9   | **Button says "🔍 Verify Message"** — the magnifying glass emoji implies search, not verification                                                                                       | Microinteraction  | Low      |
| 10  | **Confidence percentage shown without interpretation** — "72%" could be high or low depending on context                                                                                | Clarity           | Medium   |

#### Recommended Improvements

**A. Add wallet context helper text**

```
Current:  "Select Wallet" (label only)
Improved: "Select Wallet" + helper text:
          "Choose the wallet this message was sent to.
           This helps us check the transaction against your history."
```

**B. Improve placeholder text**

```
Current:  Multi-line example SMS pasted into placeholder
Improved: Single-line prompt:
          "Paste the full MTN MoMo SMS you received here…"
```

**C. Add screenshot guidance callout**
Before the upload area, add a small info box:

```
📸 For best results:
  • Screenshot the full SMS notification or MoMo inbox message
  • Make sure all text is visible and not cropped
  • Avoid screenshots of screenshots or photos of screens
```

**D. Scroll to result after submission**

```javascript
// After setResult(data.data):
setTimeout(() => {
  document.querySelector(".result-card")?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}, 100);
```

**E. Rewrite verdict headlines for action orientation**

| Verdict           | Current                              | Improved                                               |
| ----------------- | ------------------------------------ | ------------------------------------------------------ |
| Genuine           | "Message verified — looks genuine"   | "This message appears authentic"                       |
| Suspicious        | "Some details need attention"        | "Proceed with caution — some details are unusual"      |
| Likely Fraudulent | "Warning — this may not be from MTN" | "Do not act on this message — it shows signs of fraud" |

**F. Add what-to-do guidance below each verdict**

| Verdict           | Guidance                                                                                                                                                                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Genuine           | "This message matches expected MTN MoMo patterns. You can proceed with confidence, but always verify large transactions independently."                                                                                                                |
| Suspicious        | "Some elements of this message don't match typical MTN formats. Before acting on it: (1) Do not call any phone numbers in the message, (2) Check your MoMo balance directly through the \*170# USSD menu, (3) If unsure, visit an MTN service center." |
| Likely Fraudulent | "This message has strong indicators of fraud. Do not: send money, share your PIN, or call numbers in this message. If you already acted on it, contact MTN immediately at 100 or visit a service center."                                              |

**G. Humanize risk scores**

| Current                           | Improved                              |
| --------------------------------- | ------------------------------------- |
| `format_risk_score: 0.12`         | Message Format: Low risk ●            |
| `behavior_risk_score: 0.71`       | Transaction Pattern: High risk ●●●    |
| `balance_consistency_score: 0.45` | Balance Consistency: Moderate risk ●● |
| `sender_novelty_score: 0.08`      | Sender Recognition: Low risk ●        |

Show the numeric value on hover or in a details toggle for power users.

**H. Remove or collapse ML badge for regular users**
The ML agreement/disagreement signal is useful for admins reviewing cases, not for end users checking their SMS. Either:

- Remove it from CheckMessage entirely, OR
- Move it into a "Technical Details" collapsible section

**I. Remove model version from user-facing footer**
Replace with:

```
Checked on Apr 2, 2026 at 3:45 PM · Check ID: #42
```

---

### 2B. Message History Page (`MessageHistory.jsx`)

**Current state**: Stats strip + table showing all past checks. Clean and functional.

#### Problems Found

| #   | Issue                                                                                                             | Category         | Severity |
| --- | ----------------------------------------------------------------------------------------------------------------- | ---------------- | -------- |
| 1   | **Table columns show raw DB field names** — `likely_fraudulent` with underscores displayed as-is                  | Polish           | Medium   |
| 2   | **No filtering or search** — a user with 50+ checks has no way to find a specific one                             | Usability        | Medium   |
| 3   | **"Sender" column shows `counterparty_name`** — sometimes blank, sometimes `null`                                 | Data quality     | Low      |
| 4   | **Confidence bar has no label** — the thin green/amber bar means nothing without context                          | Clarity          | Medium   |
| 5   | **"View →" button text is generic** — doesn't tell the user what they'll see                                      | Microinteraction | Low      |
| 6   | **Empty state CTA says "Check Your First Message"** — good, but could add brief explanation of what checking does | Onboarding       | Low      |

#### Recommended Improvements

**A. Clean up label display**
The `replace("_", " ")` only replaces the first underscore. Use:

```javascript
(label || "").replaceAll("_", " ");
```

And capitalize: `"likely fraudulent"` → `"Likely Fraudulent"`

Better approach — create a display label map:

```javascript
const VERDICT_DISPLAY = {
  genuine: "Genuine",
  suspicious: "Suspicious",
  likely_fraudulent: "Likely Fraud",
};
```

**B. Add a simple filter row above the table**
Three toggle pills: `All` | `Genuine` | `Suspicious` | `Fraud` — filter the table client-side. This is cheap to implement and hugely improves usability.

**C. Improve "View" button**

```
Current:  "View →"
Improved: "Details →"
```

**D. Add relative time**

```
Current:  "4/2/2026"
Improved: "Today, 3:45 PM"  or  "2 days ago"
```

---

### 2C. Message Check Detail Page (`MessageCheckDetail.jsx`)

**Current state**: Full breakdown of a single message check — verdict card, extracted fields grid, raw SMS text. This is the "evidence page" users see after clicking from history.

#### Problems Found

| #   | Issue                                                                                                           | Category         | Severity |
| --- | --------------------------------------------------------------------------------------------------------------- | ---------------- | -------- |
| 1   | **Page title says "Message Check #42"** — DB ID is not meaningful to users                                      | Clarity          | Medium   |
| 2   | **Extracted Fields grid shows every field even when empty ("—")** — creates visual clutter                      | Visual hierarchy | Medium   |
| 3   | **"Raw SMS Text" section has no framing** — no explanation of why it's there or what the user should look for   | Context          | Low      |
| 4   | **No action buttons** — after viewing a suspicious result, the user has no next step (report? re-check? share?) | Action guidance  | High     |
| 5   | **Risk breakdown uses same cryptic scores as CheckMessage**                                                     | Cognitive load   | High     |

#### Recommended Improvements

**A. Improve page title**

```
Current:  "Message Check #42"
Improved: "Message Verification — Apr 2, 2026"
Subtitle: "SMS check from wallet 024XXXXXXX"
```

**B. Only show fields that have values**
Already partially done in the `extracted-grid`, but the table in the detail view shows 14 rows including many "—" entries. Filter out null/empty rows:

```javascript
.filter(([label, value]) => value != null && value !== "" && value !== "—")
```

**C. Add context to Raw SMS section**

```
Current:  heading "📩 Raw Message" + pre block
Improved: heading "Original Message" + helper text:
          "This is the exact text analyzed by our system.
           Highlighted fields were extracted automatically."
```

**D. Add action buttons at the bottom**

```
[← Back to History]    [🔍 Check Another Message]    [📋 Copy Report]
```

---

### 2D. Review Queue Page (`ReviewQueue.jsx`)

**Current state**: Admin-only table of flagged message checks with stats strip showing counts by status. Clean but has workflow gaps.

#### Problems Found

| #   | Issue                                                                                                                                   | Category        | Severity |
| --- | --------------------------------------------------------------------------------------------------------------------------------------- | --------------- | -------- |
| 1   | **5 stat cards squeeze on one row** — on 1200px screens they're tiny and hard to read                                                   | Layout          | Medium   |
| 2   | **No sorting** — admin can't sort by date, confidence, or status                                                                        | Workflow        | High     |
| 3   | **No visual priority indicator** — a 95% confidence fraud and a 55% suspicious look the same in the table except for the confidence bar | Triage          | High     |
| 4   | **"Review →" doesn't indicate urgency** — pending items look the same as reviewed items                                                 | Action guidance | Medium   |
| 5   | **Column header says "Predicted Label"** — admin-facing UX still uses model terminology                                                 | Language        | Medium   |
| 6   | **No batch actions** — admin must review one at a time. Even a simple "Mark all as reviewed" would help                                 | Workflow        | Low      |

#### Recommended Improvements

**A. Reduce stats to 3–4 cards**
Merge "Total Flagged" and "Pending Review" into one card with a sub-line:

```
Pending Review
    12
 of 27 total flagged
```

**B. Rename column headers**

```
Current:   "Predicted Label" | "Review Status"
Improved:  "System Verdict"  | "Review Decision"
```

**C. Add priority styling for high-confidence fraud**

```javascript
// If confidence > 0.8 and label is likely_fraudulent, add:
<span className="priority-flag">⚡ High Priority</span>
```

**D. Differentiate the "Review →" button for pending vs. reviewed**

```
Pending:   "Review →"  (primary blue button)
Reviewed:  "View ✓"    (outline/secondary button)
```

**E. Add sorting by column**
Start with client-side sort on the `items` array — clicking a column header toggles ascending/descending. Priority columns: Date, Confidence, Review Status.

---

### 2E. Review Detail Page (`ReviewDetail.jsx`)

**Current state**: Combined view — shows the verdict card, full message details table, and a review form. This is where the admin makes the final call.

#### Problems Found

| #   | Issue                                                                                                                                        | Category         | Severity |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- | -------- |
| 1   | **Two separate dropdowns ("Your Verdict" + "Review Status") are confusing** — the relationship between verdict and status is unclear         | Mental model     | High     |
| 2   | **Dropdown options use raw DB values** — `"likely_fraudulent"` and `"confirmed_fraud"` shown as-is                                           | Language         | Medium   |
| 3   | **No side-by-side layout** — the evidence (message + verdict) and the review form are stacked vertically, requiring scrolling back and forth | Layout           | High     |
| 4   | **"Previously reviewed" banner uses same style as success messages** — easy to miss or confuse with the current verdict                      | Visual hierarchy | Medium   |
| 5   | **No keyboard shortcuts** — admin reviewing 20+ items can't quickly approve/flag and move to next                                            | Efficiency       | Low      |
| 6   | **After saving, no "go to next" action** — admin must manually click back to queue and pick the next item                                    | Workflow         | High     |

#### Recommended Improvements

**A. Clarify the two-dropdown relationship**
Add helper text:

```
"Your Verdict" → "What do you believe this message actually is?"
"Review Status" → "What should happen with this case?"
```

Or better: combine into a single decision with smart defaults:

```
Your Decision:
  ○ Confirm as Genuine    → auto-sets status to "confirmed_genuine"
  ○ Confirm as Fraud      → auto-sets status to "confirmed_fraud"
  ○ Needs Escalation      → auto-sets status to "escalated"
  ○ Keep Pending          → status stays "pending"
```

**B. Improve dropdown option labels**

```
Current:  "likely_fraudulent", "confirmed_fraud", "confirmed_genuine"
Improved: "Likely Fraudulent", "Confirmed Fraud", "Confirmed Genuine"
```

**C. Add "Review Next" button after saving**

```javascript
// After successful save:
<button onClick={goToNextPending} className="btn btn-primary">
  Review Next Case →
</button>
```

This requires fetching the pending queue to know the next ID, or passing it via route state.

**D. Improve "Previously reviewed" banner**
Use a distinct style — not green `success`, but a neutral `info` (blue) box with an edit icon:

```
📝 Last reviewed by admin@example.com on Apr 1, 2026
   Verdict: Confirmed Genuine · Status: confirmed_genuine
   Notes: "Transaction verified with sender."
   [Edit Review]
```

---

## 3. Product Language Improvements

### Verdict Labels (User-Facing)

| Internal Label      | Current UI          | Recommended                               | Tone                |
| ------------------- | ------------------- | ----------------------------------------- | ------------------- |
| `genuine`           | "genuine"           | "Verified" or "Authentic"                 | Calm, reassuring    |
| `suspicious`        | "suspicious"        | "Needs Attention" or "Review Recommended" | Alert, non-alarming |
| `likely_fraudulent` | "likely fraudulent" | "Warning: Potential Fraud"                | Urgent, directive   |

### Risk Score Labels

| Internal Key                | Current UI            | Recommended             |
| --------------------------- | --------------------- | ----------------------- |
| `format_risk_score`         | "Message Format"      | "Message Format" (keep) |
| `behavior_risk_score`       | "Transaction History" | "Transaction Pattern"   |
| `balance_consistency_score` | "Balance Check"       | "Balance Consistency"   |
| `sender_novelty_score`      | "Sender Recognition"  | "Sender Familiarity"    |

### Risk Score Interpretation

| Score Range | Label           | Visual    |
| ----------- | --------------- | --------- |
| 0.00 – 0.25 | "Low risk"      | Green dot |
| 0.26 – 0.55 | "Moderate risk" | Amber dot |
| 0.56 – 1.00 | "High risk"     | Red dot   |

### Section Headings

| Current               | Recommended              | Rationale                               |
| --------------------- | ------------------------ | --------------------------------------- |
| "📊 Risk Breakdown"   | "How We Assessed This"   | Less technical, more explanatory        |
| "📋 Extracted Fields" | "Transaction Details"    | Users don't know what "extracted" means |
| "📩 Raw Message"      | "Original Message"       | "Raw" is developer language             |
| "🔍 Submit Review"    | "Your Assessment"        | Cleaner framing for admin               |
| "🤖 ML Model"         | Remove, or "AI Analysis" | "ML Model" is internal                  |

---

## 4. UI/UX Implementation Priorities

### Tier 1: Quick Wins (< 2 hours total, biggest impact)

| #   | Change                                                                                | File(s)                     | Effort |
| --- | ------------------------------------------------------------------------------------- | --------------------------- | ------ |
| 1   | Create shared `verdictUtils.js` — deduplicate all helper functions                    | New `utils/verdictUtils.js` | 30 min |
| 2   | Add verdict display label map (remove underscores, proper case)                       | `verdictUtils.js`           | 10 min |
| 3   | Add action guidance text below each verdict on CheckMessage                           | `CheckMessage.jsx`          | 20 min |
| 4   | Scroll to result card after SMS/screenshot analysis                                   | `CheckMessage.jsx`          | 5 min  |
| 5   | Add helper text under "Select Wallet" dropdown                                        | `CheckMessage.jsx`          | 5 min  |
| 6   | Add screenshot guidance callout                                                       | `CheckMessage.jsx`          | 10 min |
| 7   | Shorten SMS textarea placeholder to one line                                          | `CheckMessage.jsx`          | 2 min  |
| 8   | Hide empty extracted fields (filter null/blank values)                                | `MessageCheckDetail.jsx`    | 10 min |
| 9   | Rename "Raw Message" → "Original Message", "Extracted Fields" → "Transaction Details" | All pages                   | 10 min |
| 10  | Rename "Predicted Label" → "System Verdict" in Review Queue table                     | `ReviewQueue.jsx`           | 2 min  |

### Tier 2: Medium Effort (2–4 hours total, strong polish)

| #   | Change                                                                               | File(s)                                                          | Effort |
| --- | ------------------------------------------------------------------------------------ | ---------------------------------------------------------------- | ------ |
| 11  | Add human-readable risk labels ("Low risk" / "Moderate" / "High") next to scores     | `CheckMessage.jsx`, `MessageCheckDetail.jsx`, `ReviewDetail.jsx` | 30 min |
| 12  | Add verdict filter pills on Message History page                                     | `MessageHistory.jsx`                                             | 45 min |
| 13  | Improve Review Detail — add helper text to dropdowns, show capitalized option labels | `ReviewDetail.jsx`                                               | 20 min |
| 14  | Add "Review Next →" button after saving review                                       | `ReviewDetail.jsx`                                               | 30 min |
| 15  | Add relative timestamps ("Today, 3:45 PM" / "2 days ago")                            | `MessageHistory.jsx`, `ReviewQueue.jsx`                          | 30 min |
| 16  | Move ML badge into collapsible "Technical Details" section                           | `CheckMessage.jsx`                                               | 20 min |
| 17  | Replace model version footer with check timestamp + ID                               | `CheckMessage.jsx`                                               | 10 min |

### Tier 3: Longer Term (4–8 hours, professional polish)

| #   | Change                                                         | File(s)                            | Effort    |
| --- | -------------------------------------------------------------- | ---------------------------------- | --------- |
| 18  | Add column sorting to Review Queue table                       | `ReviewQueue.jsx`                  | 1–2 hours |
| 19  | Add priority badge for high-confidence fraud in Review Queue   | `ReviewQueue.jsx`                  | 30 min    |
| 20  | Add "Copy Report" button on Message Check Detail               | `MessageCheckDetail.jsx`           | 45 min    |
| 21  | Differentiate "Review →" vs "View ✓" buttons in queue          | `ReviewQueue.jsx`                  | 20 min    |
| 22  | Add smooth result-card entrance animation                      | `App.css`                          | 20 min    |
| 23  | Add Error Boundary component for uncaught React errors         | New `components/ErrorBoundary.jsx` | 30 min    |
| 24  | Side-by-side layout for evidence + review form on wide screens | `ReviewDetail.jsx`, `App.css`      | 1–2 hours |

---

## 5. Phased Roadmap

### Phase 1: Language & Guidance (1 session)

Focus: Make the app speak human instead of model-ese.

- [ ] Create `utils/verdictUtils.js` with shared helpers
- [ ] Apply display label map across all pages
- [ ] Add action guidance text to all three verdict states
- [ ] Rename technical section headings
- [ ] Add wallet selection helper text
- [ ] Add screenshot guidance callout
- [ ] Scroll to result card on CheckMessage
- [ ] Shorten placeholder
- [ ] Remove model version from user-facing footer

**Result**: The app feels like it was designed for users, not developers.

### Phase 2: Information Hierarchy (1 session)

Focus: Show the right information at the right time.

- [ ] Humanize risk scores with labels
- [ ] Hide empty extracted fields
- [ ] Move ML badge to collapsible section
- [ ] Add relative timestamps
- [ ] Add verdict filter pills on Message History
- [ ] Improve detail page title/subtitle

**Result**: Users can scan quickly and drill down when needed.

### Phase 3: Admin Workflow (1 session)

Focus: Make the review process efficient.

- [ ] Add helper text to review dropdowns
- [ ] Capitalize and clean review option labels
- [ ] Add "Review Next →" post-save
- [ ] Add priority badges for high-confidence fraud
- [ ] Differentiate pending vs. reviewed action buttons
- [ ] Rename column headers in Review Queue

**Result**: Admin can process the review queue 2–3x faster.

### Phase 4: Professional Polish (1 session)

Focus: Details that make it feel like a real product.

- [ ] Column sorting in Review Queue
- [ ] Copy Report button on detail page
- [ ] Result card entrance animation
- [ ] Error boundary component
- [ ] Side-by-side review layout (wide screens)

**Result**: Demo-ready for a fintech stakeholder audience.

---

## Quick-Reference: Files to Change

| File                               | Changes                                                                                                                              |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| New: `src/utils/verdictUtils.js`   | Shared `pillClass`, `verdictIcon`, `verdictClass`, `verdictHeadline`, `riskColor`, `VERDICT_DISPLAY`, `riskLabel()`                  |
| `src/pages/CheckMessage.jsx`       | Action guidance, scroll-to-result, screenshot guidance, wallet helper text, shorter placeholder, collapsible ML badge, better footer |
| `src/pages/MessageHistory.jsx`     | Display label map, filter pills, relative time, "Details →" button text                                                              |
| `src/pages/MessageCheckDetail.jsx` | Better title/subtitle, hide empty fields, rename sections, action buttons                                                            |
| `src/pages/ReviewQueue.jsx`        | Rename columns, priority badge, differentiate button states, stats card consolidation                                                |
| `src/pages/ReviewDetail.jsx`       | Dropdown helper text, capitalized options, "Review Next →", improved "previously reviewed" banner                                    |
| `src/App.css`                      | Result card animation, priority flag styling, collapsible section styling                                                            |

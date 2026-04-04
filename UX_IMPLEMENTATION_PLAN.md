# Fintech UX Implementation Plan — Top 10 Changes

> Scope: Incremental polish within existing React app and CSS theme
> Tone: Calm, trustworthy, clear — never alarming, never vague

---

## Priority 1: Create Shared Verdict Utilities

**File**: `frontend/src/utils/verdictUtils.js` (new)

All 4 pages duplicate `pillClass()`, `verdictIcon()`, `verdictClass()`, `verdictHeadline()`, `riskColor()`. Centralise once, import everywhere.

```javascript
// ── Display labels (never show raw DB values to users) ─────────
export const VERDICT_LABEL = {
  genuine: "Authentic",
  suspicious: "Needs Review",
  likely_fraudulent: "Potential Fraud",
};

export const VERDICT_HEADLINE = {
  genuine: "This message appears to be authentic",
  suspicious: "Some details in this message are unusual",
  likely_fraudulent: "This message shows signs of fraud",
};

// ── Action guidance shown below the verdict headline ───────────
export const VERDICT_GUIDANCE = {
  genuine:
    "This message follows expected MTN MoMo patterns. You can proceed normally. " +
    "For large transactions, we still recommend verifying your balance via *170#.",
  suspicious:
    "Some elements of this message don't match typical MTN patterns. " +
    "Before taking action:\n" +
    "• Do not call any phone number in the message\n" +
    "• Check your MoMo balance directly via *170#\n" +
    "• If in doubt, visit your nearest MTN service centre",
  likely_fraudulent:
    "This message has strong indicators of fraud. " +
    "Do not send money, share your PIN, or call numbers in this message.\n" +
    "If you have already acted on it, contact MTN immediately by dialling 100.",
};

// ── Status pill CSS class ──────────────────────────────────────
export function pillClass(label) {
  if (label === "genuine") return "trusted";
  if (label === "suspicious") return "review";
  if (label === "likely_fraudulent") return "blocked";
  return "info";
}

// ── Verdict icon ───────────────────────────────────────────────
export function verdictIcon(label) {
  if (label === "genuine") return "✅";
  if (label === "suspicious") return "⚠️";
  if (label === "likely_fraudulent") return "🚨";
  return "❓";
}

// ── Result card CSS class ──────────────────────────────────────
export function verdictClass(label) {
  if (label === "genuine") return "verdict-genuine";
  if (label === "suspicious") return "verdict-suspicious";
  if (label === "likely_fraudulent") return "verdict-fraudulent";
  return "verdict-unknown";
}

// ── Risk score → CSS class ─────────────────────────────────────
export function riskColor(value) {
  if (value == null) return "";
  if (value <= 0.25) return "risk-low";
  if (value <= 0.55) return "risk-med";
  return "risk-high";
}

// ── Risk score → human label ───────────────────────────────────
export function riskLabel(value) {
  if (value == null) return "—";
  if (value <= 0.25) return "Low";
  if (value <= 0.55) return "Moderate";
  return "High";
}

// ── Review status display ──────────────────────────────────────
export const REVIEW_STATUS_LABEL = {
  pending: "Pending",
  confirmed_genuine: "Confirmed Genuine",
  confirmed_fraud: "Confirmed Fraud",
  escalated: "Escalated",
};

export const REVIEWER_LABEL_DISPLAY = {
  genuine: "Genuine",
  suspicious: "Suspicious",
  likely_fraudulent: "Likely Fraudulent",
};
```

**Then update imports** in `CheckMessage.jsx`, `MessageHistory.jsx`, `MessageCheckDetail.jsx`, `ReviewQueue.jsx`, `ReviewDetail.jsx` — delete the local duplicate functions and import from `../utils/verdictUtils`.

---

## Priority 2: Rewrite Verdict Wording Across All Pages

Replace every raw label display. Currently the pill text uses:

```javascript
{
  (pred.predicted_label || "").replace("_", " ");
}
```

Change to:

```javascript
{
  VERDICT_LABEL[pred.predicted_label] || pred.predicted_label;
}
```

### Complete Verdict Copy

#### Genuine Verdict

| Element          | Current                            | New                                                                                                                                                            |
| ---------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pill text        | `genuine`                          | **Authentic**                                                                                                                                                  |
| Headline         | "Message verified — looks genuine" | **"This message appears to be authentic"**                                                                                                                     |
| Guidance         | _(none)_                           | **"This message follows expected MTN MoMo patterns. You can proceed normally. For large transactions, we still recommend verifying your balance via \*170#."** |
| Confidence label | `87% confidence`                   | **87% match**                                                                                                                                                  |

#### Suspicious Verdict

| Element          | Current                       | New                                                                                                                                                                                                                                          |
| ---------------- | ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pill text        | `suspicious`                  | **Needs Review**                                                                                                                                                                                                                             |
| Headline         | "Some details need attention" | **"Some details in this message are unusual"**                                                                                                                                                                                               |
| Guidance         | _(none)_                      | **"Some elements of this message don't match typical MTN patterns. Before taking action: • Do not call any phone number in the message • Check your MoMo balance directly via \*170# • If in doubt, visit your nearest MTN service centre"** |
| Confidence label | `54% confidence`              | **54% match**                                                                                                                                                                                                                                |

#### Likely Fraudulent Verdict

| Element          | Current                              | New                                                                                                                                                                                              |
| ---------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Pill text        | `likely fraudulent`                  | **Potential Fraud**                                                                                                                                                                              |
| Headline         | "Warning — this may not be from MTN" | **"This message shows signs of fraud"**                                                                                                                                                          |
| Guidance         | _(none)_                             | **"This message has strong indicators of fraud. Do not send money, share your PIN, or call numbers in this message. If you have already acted on it, contact MTN immediately by dialling 100."** |
| Confidence label | `92% confidence`                     | **92% match**                                                                                                                                                                                    |

#### Implementation in CheckMessage.jsx, MessageCheckDetail.jsx, ReviewDetail.jsx

After the verdict headline `<p>` element, add the guidance block:

```jsx
<p className="verdict-guidance">{VERDICT_GUIDANCE[pred.predicted_label]}</p>
```

New CSS class:

```css
.verdict-guidance {
  margin: 0.75rem 0 0;
  font-size: 0.88rem;
  line-height: 1.65;
  color: var(--color-slate-600);
  white-space: pre-line;
}
```

Change confidence label from "confidence" → "match":

```jsx
<span className="verdict-sub">match</span>
```

---

## Priority 3: Humanize Risk Scores

Currently shows raw floats (`0.23`, `0.71`). Change to labelled interpretation.

**In the risk grid, replace:**

```jsx
<span className="risk-value">
  {pred[key] != null ? pred[key].toFixed(2) : "—"}
</span>
```

**With:**

```jsx
<span className="risk-value">{riskLabel(pred[key])}</span>
<span className="risk-detail">
  {pred[key] != null ? pred[key].toFixed(2) : ""}
</span>
```

**Rename section heading:**

```
Current:  "📊 Risk Breakdown"
New:      "How We Assessed This"
```

**New CSS:**

```css
.risk-detail {
  display: block;
  font-size: 0.7rem;
  color: var(--color-slate-400);
  font-weight: 500;
  margin-top: 0.15rem;
  font-variant-numeric: tabular-nums;
}
```

**Risk item labels — rename:**
| Current | New |
|---------|-----|
| Message Format | Message Format |
| Transaction History | Transaction Pattern |
| Balance Check | Balance Consistency |
| Sender Recognition | Sender Familiarity |

---

## Priority 4: Add Wallet Helper Text and Screenshot Guidance

### Wallet Dropdown

After the `<label>Select Wallet</label>`, add:

```jsx
<span
  className="form-hint"
  style={{ display: "block", marginBottom: "0.35rem", textAlign: "left" }}
>
  Choose the wallet this message was sent to — this helps verify the
  transaction.
</span>
```

### SMS Placeholder

```
Current:  'Paste the full MoMo SMS here, e.g.:\n\nYou have received GHS 100.00 from...'
New:      'Paste the full MTN MoMo SMS you received…'
```

### Screenshot Guidance

Before the drag-drop upload area, add:

```jsx
<div
  className="message-box info"
  style={{ marginBottom: "0.75rem", fontSize: "0.85rem" }}
>
  <span className="message-icon">💡</span>
  <div>
    For best results, upload a clear screenshot showing the complete message.
    Avoid cropped images or photos of a screen.
  </div>
</div>
```

---

## Priority 5: Scroll to Result and Improve Loading Text

### Auto-scroll after submission

In both `handleSmsSubmit` and `handleScreenshotSubmit`, after `setResult(data.data)`:

```javascript
setTimeout(() => {
  document.querySelector(".result-card")?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}, 150);
```

### Loading text

```
Current:  "Analyzing SMS…" / "Processing screenshot…"
New:      "Checking message authenticity…" / "Reading and analysing your screenshot…"
```

---

## Priority 6: Rewrite OCR and Error Messages

### OCR Low-Confidence Warning

```
Current:  "OCR confidence is low. The extracted text may contain errors — verify the result carefully."
New:      "We had difficulty reading parts of this image. The extracted text below may be incomplete — please review it before continuing."
```

### OCR Pending (screenshot uploaded, text not usable)

```
Current:  "Screenshot uploaded. Some text was extracted but it doesn't look like a MoMo message."
New:      "Your screenshot was saved. We extracted some text, but it doesn't appear to contain a MoMo transaction message. You can review the text below or try pasting the message directly in the SMS tab."
```

### OCR Pending (no text extracted)

```
Current:  "Text could not be extracted. Try a clearer screenshot, or paste the message in the SMS tab."
New:      "We couldn't read text from this image. Try a screenshot with clear, readable text — or paste the message directly in the SMS tab for faster results."
```

### OCR Error (complete failure)

```
Current:  "OCR could not extract text from this image. Try uploading a clearer, well-lit screenshot."
New:      "This image couldn't be processed. Please try again with a clear, well-lit screenshot. If the issue persists, use the SMS tab to paste the message text directly."
```

### OCR Section Title

```
Current:  "🔍 OCR Extracted Text"
New:      "Text Read From Screenshot"
```

### General Error Messages

```
Current:  "Analysis failed."
New:      "Something went wrong while checking this message. Please try again."

Current:  "Could not reach the server. Is the backend running?"
New:      "Unable to connect to the server. Please check your connection and try again."

Current:  "Please paste the SMS message text."
New:      "Please paste the SMS message you'd like to check."

Current:  "Please select a wallet first."
New:      "Please select a wallet before submitting."

Current:  "File is too large (3.2 MB). Maximum size is 5 MB."
New:      "This file is too large (3.2 MB). Please use an image under 5 MB."

Current:  "Only PNG, JPG, and WEBP images are accepted."
New:      "Please upload a PNG, JPG, or WEBP image."
```

### Success Messages

```
Current:  "Review saved successfully."
New:      "Your review has been saved."

Current:  "Session expired. Please log in again."
New:      "Your session has expired. Please sign in again."
```

---

## Priority 7: Clean Up History and Detail Pages

### MessageHistory.jsx

- Rename "View →" button to **"Details"**
- Add verdict filter pills above the table:

```jsx
<div className="filter-pills">
  {["all", "genuine", "suspicious", "likely_fraudulent"].map((f) => (
    <button
      key={f}
      className={`filter-pill ${filter === f ? "active" : ""}`}
      onClick={() => setFilter(f)}
    >
      {f === "all" ? "All" : VERDICT_LABEL[f]}
    </button>
  ))}
</div>
```

- Filter the `checks` array based on selected filter
- Use `VERDICT_LABEL` for pill text instead of `replace("_", " ")`

### MessageCheckDetail.jsx

- **Page title**: Change from `"Message Check #${id}"` to **`"Message Verification"`** with subtitle: `"Check #${id} · ${check.created_at ? new Date(check.created_at).toLocaleDateString() : ''}"``
- **Section heading**: Change `"Message Details"` → **"Transaction Details"**
- **Section heading**: Change `"Raw SMS Text"` → **"Original Message"**
- **Filter out empty fields**: Only render extracted-grid items when value is truthy
- **Add action link at bottom**:

```jsx
<div style={{ marginTop: "1.5rem", display: "flex", gap: "1rem" }}>
  <Link to="/check-message" className="btn btn-primary">
    Check Another Message
  </Link>
  <Link
    to="/message-history"
    className="btn"
    style={{ border: "1px solid var(--color-slate-300)" }}
  >
    Back to History
  </Link>
</div>
```

---

## Priority 8: Improve Review Queue Table Headers and Priority

### ReviewQueue.jsx Column Renames

| Current Header    | New Header              |
| ----------------- | ----------------------- |
| `Predicted Label` | **System Verdict**      |
| `Confidence`      | **Confidence** _(keep)_ |
| `Review Status`   | **Review Decision**     |
| `Counterparty`    | **Sender / Recipient**  |

### Add Priority Indicator

For items where `confidence_score > 0.8` and label is `likely_fraudulent`:

```jsx
{
  item.predicted_label === "likely_fraudulent" &&
    item.confidence_score > 0.8 && (
      <span className="priority-flag">Priority</span>
    );
}
```

```css
.priority-flag {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: var(--radius-full);
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  background: var(--color-danger-bg);
  color: var(--color-danger);
  border: 1px solid var(--color-danger-border);
  margin-left: 0.5rem;
}
```

### Differentiate Action Buttons

```jsx
{
  !item.review_status || item.review_status === "pending" ? (
    <Link
      to={`/review-queue/${item.message_check_id}`}
      className="btn btn-primary btn-view"
    >
      Review
    </Link>
  ) : (
    <Link
      to={`/review-queue/${item.message_check_id}`}
      className="btn btn-outline btn-view"
    >
      View
    </Link>
  );
}
```

New CSS:

```css
.btn-outline {
  background: transparent;
  color: var(--color-slate-600);
  border: 1px solid var(--color-slate-300);
}
.btn-outline:hover {
  background: var(--color-slate-50);
  border-color: var(--color-slate-400);
}
```

---

## Priority 9: Improve Review Detail Form UX

### ReviewDetail.jsx

**A. Add helper text to dropdowns:**

```jsx
<div className="form-group">
  <label htmlFor="reviewerLabel">Your Assessment</label>
  <span className="form-hint" style={{ textAlign: "left", marginBottom: "0.35rem" }}>
    Based on the evidence above, what do you believe this message is?
  </span>
  <select ...>
    <option value="">— select your assessment —</option>
    <option value="genuine">Genuine — message is authentic</option>
    <option value="suspicious">Suspicious — cannot confirm either way</option>
    <option value="likely_fraudulent">Likely Fraudulent — appears to be fraud</option>
  </select>
</div>
```

```jsx
<div className="form-group">
  <label htmlFor="reviewStatus">Case Resolution</label>
  <span className="form-hint" style={{ textAlign: "left", marginBottom: "0.35rem" }}>
    What action should be taken on this case?
  </span>
  <select ...>
    <option value="">— select resolution —</option>
    <option value="confirmed_genuine">Close — Confirmed Genuine</option>
    <option value="confirmed_fraud">Close — Confirmed Fraud</option>
    <option value="escalated">Escalate for further investigation</option>
    <option value="pending">Keep open — Pending further info</option>
  </select>
</div>
```

**B. Rename section heading:**

```
Current:  "🔍 Submit Review"
New:      "Your Assessment"
```

**C. Rename section headings in evidence area:**

```
"📊 Risk Breakdown"   →  "Assessment Breakdown"
"📋 Extracted Fields"  →  "Transaction Details"
"📩 Raw Message"       →  "Original Message"
```

**D. Add "Review Next" after save:**

```jsx
{
  saveMsg && (
    <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.5rem" }}>
      <Link
        to="/review-queue"
        className="btn"
        style={{ border: "1px solid var(--color-slate-300)" }}
      >
        Back to Queue
      </Link>
      <button
        onClick={() => {
          /* navigate to next pending */
        }}
        className="btn btn-primary"
      >
        Review Next Case →
      </button>
    </div>
  );
}
```

---

## Priority 10: Remove/Collapse Technical Details for End Users

### ML Badge — Collapse on CheckMessage

The `ml_available` block with "Agrees with rules" / "Differs from rules" is developer debugging. On the user-facing CheckMessage page, wrap it in a collapsible:

```jsx
{
  pred.ml_available && (
    <details className="tech-details">
      <summary>Technical details</summary>
      <div
        className={`ml-badge ${pred.ml_agrees ? "ml-agrees" : "ml-differs"}`}
      >
        ...existing content...
      </div>
    </details>
  );
}
```

```css
.tech-details {
  margin-top: 1rem;
}
.tech-details summary {
  font-size: 0.8rem;
  color: var(--color-slate-400);
  cursor: pointer;
  font-weight: 600;
  letter-spacing: 0.3px;
}
.tech-details summary:hover {
  color: var(--color-slate-600);
}
```

### Model Version Footer — Replace

```
Current:  "Model: v6.1-hybrid-calibrated"
New:      "Verified on Apr 2, 2026 at 3:45 PM"
```

```jsx
<div className="result-footer">
  Verified on{" "}
  {new Date().toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })}{" "}
  at{" "}
  {new Date().toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  })}
  {mc?.id && <> · Ref #{mc.id}</>}
</div>
```

On the ReviewDetail page, keep the model version visible since admins benefit from it.

---

## Implementation Sequence

```
Step 1  →  Create verdictUtils.js, update all 5 page imports
Step 2  →  Apply VERDICT_LABEL / VERDICT_HEADLINE / VERDICT_GUIDANCE
Step 3  →  Humanize risk scores (riskLabel + riskDetail)
Step 4  →  Wallet helper text + screenshot guidance + shorter placeholder
Step 5  →  Auto-scroll + loading text improvements
Step 6  →  Rewrite all OCR / error / success copy
Step 7  →  History filters + Detail page cleanup
Step 8  →  Review Queue headers + priority + button differentiation
Step 9  →  Review Detail form UX improvements
Step 10 →  Collapse ML badge + replace model footer
```

Each step is independent and can be committed separately. Steps 1–6 can be done in a single session. Steps 7–10 are follow-up polish.

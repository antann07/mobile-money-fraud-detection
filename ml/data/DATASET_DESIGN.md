# MTN MoMo Fraud Detection – Training Dataset Design

## 1. Dataset Column Structure

| #   | Column                    | Type      | Description                                      | Example                                                           |
| --- | ------------------------- | --------- | ------------------------------------------------ | ----------------------------------------------------------------- |
| 1   | `sample_id`               | int       | Unique row identifier                            | 1                                                                 |
| 2   | `raw_sms`                 | string    | Full SMS text (pasted or OCR-extracted)          | "You have received GHS 500.00 from..."                            |
| 3   | `source_channel`          | enum      | How the message entered the system               | `sms` \| `screenshot`                                             |
| 4   | `transaction_type`        | enum      | Parsed transaction type                          | `deposit` \| `transfer_in` \| `payment` \| `airtime` \| `cash_in` |
| 5   | `direction`               | enum      | Money flow direction                             | `incoming` \| `outgoing`                                          |
| 6   | `amount`                  | float     | Transaction amount in GHS                        | 500.00                                                            |
| 7   | `fee`                     | float     | Fee charged (0 if not present)                   | 0.50                                                              |
| 8   | `balance_after`           | float     | Balance shown after transaction                  | 1250.00                                                           |
| 9   | `counterparty_name`       | string    | Sender/receiver name shown in SMS                | "KWAME MENSAH"                                                    |
| 10  | `counterparty_number`     | string    | Sender/receiver phone number                     | 0241234567                                                        |
| 11  | `mtn_transaction_id`      | string    | Transaction ID shown in SMS (blank if missing)   | 9384710236                                                        |
| 12  | `transaction_datetime`    | datetime  | Timestamp shown in SMS body                      | 2026-03-15 09:30:00                                               |
| 13  | `has_valid_txn_id`        | bool(0/1) | Whether SMS contains a valid MTN transaction ID  | 1                                                                 |
| 14  | `has_balance`             | bool(0/1) | Whether SMS shows a balance                      | 1                                                                 |
| 15  | `has_fee`                 | bool(0/1) | Whether SMS mentions a fee or e-levy             | 1                                                                 |
| 16  | `has_counterparty_name`   | bool(0/1) | Whether a sender/receiver name is present        | 1                                                                 |
| 17  | `has_counterparty_number` | bool(0/1) | Whether a phone number is present                | 1                                                                 |
| 18  | `has_valid_datetime`      | bool(0/1) | Whether a parseable datetime exists              | 1                                                                 |
| 19  | `amount_unusually_round`  | bool(0/1) | Amount is suspiciously round (e.g. 1000, 5000)   | 0                                                                 |
| 20  | `contains_url`            | bool(0/1) | SMS contains a URL/link                          | 0                                                                 |
| 21  | `contains_urgency_words`  | bool(0/1) | "immediately", "urgent", "expire", "act now"     | 0                                                                 |
| 22  | `contains_pin_request`    | bool(0/1) | Asks for PIN, password, OTP                      | 0                                                                 |
| 23  | `spelling_error_count`    | int       | Number of spelling/grammar errors detected       | 0                                                                 |
| 24  | `message_length`          | int       | Character count of raw_sms                       | 187                                                               |
| 25  | `parser_confidence`       | float     | Weighted confidence from sms_parser.py (0.0–1.0) | 0.92                                                              |
| 26  | `label`                   | enum      | Ground-truth classification                      | `genuine` \| `suspicious` \| `likely_fraudulent`                  |
| 27  | `label_source`            | enum      | Who assigned the label                           | `expert` \| `user_report` \| `rule_engine` \| `synthetic`         |
| 28  | `notes`                   | string    | Optional annotation explaining label choice      | "Missing transaction ID"                                          |

---

## 2. Label Definitions

### `genuine` — Confirmed real MTN MoMo notification

The message is a **real, system-generated** SMS from MTN Mobile Money. It:

- Contains a valid MTN transaction ID (10-digit pure numeric, e.g. `9384710236`)
- Shows correct GHS amount formatting with accurate e-levy (1% on transfers above GHS 100)
- Includes a balance-after figure that is mathematically consistent
- Uses the exact MTN MoMo SMS template (see format notes below)
- Has a realistic Ghanaian counterparty name and valid MTN-prefix phone number
- Does NOT contain links, PIN requests, or urgency language
- Date appears at end as bare `DD/MM/YYYY HH:MM` (no "Date:" prefix)

**MTN template (incoming transfer):**

```
You have received GHS {amount} from {NAME} {phone}. Transaction ID: {10-digit}.
Fee charged: GHS 0.00. E-levy: GHS {1% of amount}. Your new balance is GHS {balance}.
{DD/MM/YYYY HH:MM}.
```

**MTN template (cash-in):**

```
Cash In of GHS {amount} at agent {NAME} {phone}. Transaction ID: {10-digit}.
Your new balance is GHS {balance}. {DD/MM/YYYY HH:MM}.
```

**Decision rule:** If the SMS matches the MTN template exactly, all math checks out, and all fields parse cleanly, label it `genuine`.

### `suspicious` — Structurally deviant but not overtly fake

The message has **one or more detectable text/structure anomalies** compared to genuine MTN templates. A text classifier should be able to flag these without needing user behavior history. Red flags are embedded in the **wording, field labels, field order, formatting, or numeric consistency** of the SMS itself.

**Text/structure indicators (at least one per sample):**

| Indicator                | Example                                                                        | Why it's detectable          |
| ------------------------ | ------------------------------------------------------------------------------ | ---------------------------- |
| Wrong wording            | "You received" instead of "You have received"                                  | Regex/template mismatch      |
| Wrong field labels       | "Trans.ID:" or "Balance:" instead of "Transaction ID:" / "Your new balance is" | Label differs from canonical |
| Swapped field order      | E-levy line before Fee line                                                    | Sequence deviation           |
| Name casing              | Title Case "Ama Serwaa" instead of ALL CAPS                                    | Parser or NLP can detect     |
| Phone format             | "(024...)" with parentheses or "+233..." international                         | Regex pattern difference     |
| Extra non-standard field | "Ref: MP260327.1955" appended                                                  | Real MTN never adds Ref line |
| Non-numeric txn ID       | "48293OI762" (letters mixed in)                                                | Regex `\d{10}` fails         |
| Missing preposition      | "Cash In GHS" instead of "Cash In of GHS"                                      | Exact wording mismatch       |
| Date label prefix        | "Date: 28/03/2026" instead of bare "28/03/2026"                                | Extra label text             |
| E-levy math error        | GHS 0.00 on a GHS 1,000 transfer (should be 10.00)                             | Arithmetic check             |

**Key design principle:** Every suspicious sample must be distinguishable from genuine through **text analysis alone** — without user history, device info, or transaction timing. The anomaly lives in the message text, not the context around it.

**Decision rule:** The message structurally resembles an MTN notification but deviates from the canonical template in at least one detectable way (wording, field label, field order, formatting, or numeric consistency).

### `likely_fraudulent` — Strong fraud indicators

The message is **almost certainly fake** or part of a scam. It:

- Contains a URL or link (MTN MoMo SMS never includes links)
- Asks for PIN, OTP, password, or secret code
- Uses urgency language: "act now", "expires in", "immediately confirm"
- Has major spelling or grammar errors (unlike automated MTN messages)
- Missing critical fields (no transaction ID, no balance, no fee)
- Claims to be from MTN but uses non-standard sender format
- Amount/balance math is impossible (balance_after = balance_before, or negative)
- Impersonates MTN with wrong formatting (e.g. "GHC" instead of "GHS")

**Decision rule:** A reasonable MoMo user or fraud analyst would immediately flag this as fake. The message contains deliberate deception markers.

---

## 3. Feature Groups

### Group A: Text Features (extracted from raw_sms)

| Feature                  | Source           | Why it matters                                                |
| ------------------------ | ---------------- | ------------------------------------------------------------- |
| `contains_url`           | Regex scan       | Real MTN SMS never has links                                  |
| `contains_urgency_words` | Keyword list     | Pressure tactics = scam signal                                |
| `contains_pin_request`   | Keyword list     | MTN never asks for PIN via SMS                                |
| `spelling_error_count`   | NLP / dictionary | Auto-generated SMS has zero errors                            |
| `message_length`         | len(raw_sms)     | Fake messages are often shorter or longer than real templates |
| `parser_confidence`      | sms_parser.py    | Low confidence = doesn't match MTN format                     |
| `has_valid_txn_id`       | Regex            | Missing = likely fake                                         |
| `has_balance`            | Regex            | Missing = likely fake                                         |
| `has_fee`                | Regex            | Real transactions show fee/e-levy                             |
| `has_valid_datetime`     | Regex            | Missing or malformed = suspicious                             |

### Group B: Structured Transaction Features (parsed values)

| Feature                   | Source                                  | Why it matters                                                     |
| ------------------------- | --------------------------------------- | ------------------------------------------------------------------ |
| `amount`                  | Parsed from SMS                         | Unusually high amounts for new senders                             |
| `fee`                     | Parsed from SMS                         | Fee = 0 on deposits is real; fee absent on transfers is suspicious |
| `balance_after`           | Parsed from SMS                         | Enables balance consistency check                                  |
| `amount_unusually_round`  | Computed                                | Exact round amounts more common in scams                           |
| `balance_consistency`     | balance_before + amount ≈ balance_after | Math doesn't add up = fabricated                                   |
| `has_counterparty_name`   | Parsed                                  | Real MTN SMS always includes sender name                           |
| `has_counterparty_number` | Parsed                                  | Real MTN SMS always includes phone number                          |

### Group C: User Behavior Features (from user history)

| Feature                | Source                          | Why it matters                        |
| ---------------------- | ------------------------------- | ------------------------------------- |
| `amount_zscore`        | (amount - user_mean) / user_std | Unusual amount for this user          |
| `txn_time_deviation`   | abs(hour - user_avg_hour)       | Transaction at unusual time           |
| `velocity_1day`        | Count of txns in last 24h       | Burst of messages = likely fake batch |
| `is_new_device`        | device_id history               | New device + high amount = risk       |
| `is_new_location`      | region history                  | New location + high amount = risk     |
| `sender_novelty_score` | counterparty history            | First-time sender with large amount   |
| `balance_drain_ratio`  | amount / balance_before         | Draining entire balance = risk        |
| `sim_swap_flag`        | Carrier data                    | Recent SIM swap = highest risk        |

---

## 4. Auto-Parseable vs Manual Fields

This table clarifies which columns your `sms_parser.py` can extract automatically and which require manual annotation or computation.

| Column                    | Source         | Method                                                                 |
| ------------------------- | -------------- | ---------------------------------------------------------------------- |
| `raw_sms`                 | User input     | Direct paste or OCR extraction from screenshot                         |
| `source_channel`          | System         | Set by input method (sms paste vs screenshot upload)                   |
| `transaction_type`        | **Auto-parse** | `sms_parser.py` keyword detection ("received", "Cash In", "Payment")   |
| `direction`               | **Auto-parse** | `sms_parser.py` keyword detection (incoming vs outgoing)               |
| `amount`                  | **Auto-parse** | Regex: `GHS\s?[\d,]+\.?\d*` — first amount in message                  |
| `fee`                     | **Auto-parse** | Regex: `Fee charged:` or `E-levy:` followed by GHS amount              |
| `balance_after`           | **Auto-parse** | Regex: `new balance is GHS` or `Balance: GHS`                          |
| `counterparty_name`       | **Auto-parse** | Regex: `from {NAME} {phone}` pattern extraction                        |
| `counterparty_number`     | **Auto-parse** | Regex: `(\+233\|0)[2-5]\d{8}` — Ghana phone format                     |
| `mtn_transaction_id`      | **Auto-parse** | Regex: `Transaction ID:` followed by 6+ digits                         |
| `transaction_datetime`    | **Auto-parse** | Regex: `DD/MM/YYYY HH:MM` pattern at end of message                    |
| `has_valid_txn_id`        | **Computed**   | `1` if `mtn_transaction_id` is 10-digit numeric, else `0`              |
| `has_balance`             | **Computed**   | `1` if `balance_after` was successfully parsed                         |
| `has_fee`                 | **Computed**   | `1` if fee or e-levy line found in text                                |
| `has_counterparty_name`   | **Computed**   | `1` if name extracted, else `0`                                        |
| `has_counterparty_number` | **Computed**   | `1` if phone number extracted, else `0`                                |
| `has_valid_datetime`      | **Computed**   | `1` if datetime parsed, else `0`                                       |
| `amount_unusually_round`  | **Computed**   | `1` if amount % 500 == 0 or amount % 1000 == 0                         |
| `contains_url`            | **Computed**   | Regex: `https?://` or `www\.` or `.xyz` / `.com/` patterns             |
| `contains_urgency_words`  | **Computed**   | Keyword list: "urgent", "immediately", "act now", "expire", "reversed" |
| `contains_pin_request`    | **Computed**   | Keyword list: "PIN", "password", "OTP", "secret"                       |
| `spelling_error_count`    | **Computed**   | Dictionary/NLP check against known correct words                       |
| `message_length`          | **Computed**   | `len(raw_sms)`                                                         |
| `parser_confidence`       | **Computed**   | Weighted score from `sms_parser.py` (0.0–1.0)                          |
| `label`                   | **Manual**     | Expert annotation — ground truth                                       |
| `label_source`            | **Manual**     | Who assigned the label (expert, user_report, rule_engine)              |
| `notes`                   | **Manual**     | Free-text explanation of labeling decision                             |

**Summary:** 11 fields are auto-parsed from SMS text, 12 are computed from parsed values, 3 are manual annotations, and 2 come from system context.

---

## 5. How to Grow This Dataset

1. **Start with these 35 seed samples** to validate your pipeline end-to-end
2. **Collect real messages** from trusted users (with consent) — label as `genuine`
3. **Collect scam reports** from users and online forums — label as `likely_fraudulent`
4. **Use admin reviews** from `fraud_reviews` table to create expert-labeled samples
5. **Augment with variations** — swap names, amounts, dates in templates
6. **Target 500+ samples** before serious ML training (150 genuine, 150 suspicious, 200 fraudulent)
7. **Use the `label_source` column** to track data provenance for quality control

---

## 10. Using the Phase 7 Dataset to Improve the Rule-Based Engine

The 23-column schema in `phase7_labeled_sms.csv` maps directly to rules that
can be implemented in `flask_backend/services/sms_parser.py` and a new
`fraud_engine.py` scoring layer. Below is a practical guide.

### 10.1 Feature → Rule Mapping

| Boolean Column          | Rule Idea                                                            | Threshold / Logic                    |
| ----------------------- | -------------------------------------------------------------------- | ------------------------------------ |
| `has_valid_mtn_format`  | If 0, immediately flag as non-genuine                                | Binary gate — genuine always = 1     |
| `has_balance_info`      | Missing balance in a transfer SMS is a strong fraud signal           | 0 → +40 risk points                  |
| `has_fee_info`          | Missing Fee/E-levy on a transfer over GHS 100 is suspicious          | 0 AND amount > 100 → +25 risk points |
| `has_transaction_id`    | Missing or non-numeric txn ID                                        | 0 → +30 risk points                  |
| `has_sender_name`       | Missing sender name in a transfer SMS                                | 0 → +20 risk points                  |
| `has_character_anomaly` | Spelling errors, wrong casing, wrong currency code, informal abbrevs | 1 → +15 risk points                  |
| `has_spacing_anomaly`   | Double spaces, tab characters, unusual whitespace                    | 1 → +10 risk points                  |
| `has_urgency_language`  | "avoid", "blocked", "reversal", "within 24hrs", "immediately"        | 1 → +35 risk points                  |

### 10.2 Composite Risk Score

```
risk_score = 0
if not has_valid_mtn_format:   risk_score += 50
if not has_balance_info:       risk_score += 40
if has_urgency_language:       risk_score += 35
if not has_transaction_id:     risk_score += 30
if not has_fee_info and amount > 100: risk_score += 25
if not has_sender_name:        risk_score += 20
if has_character_anomaly:      risk_score += 15
if has_spacing_anomaly:        risk_score += 10
```

**Decision thresholds (tunable):**

- `risk_score == 0` → **genuine** (all checks pass)
- `1 ≤ risk_score ≤ 65` → **suspicious** (one or two soft failures)
- `risk_score > 65` → **likely_fraudulent** (multiple failures or urgency + missing fields)

### 10.3 Validating Against the Dataset

Run the scoring formula over all 20 rows and verify:

| Class             | Expected Score Range | Dataset Rows |
| ----------------- | -------------------- | ------------ |
| genuine           | 0                    | 1–10         |
| suspicious        | 50–65                | 11–15        |
| likely_fraudulent | 70–160               | 16–20        |

If any row falls outside its expected band, adjust the point values above.
The 20-sample dataset is small enough to inspect row-by-row but diverse enough
to cover the main deviation patterns seen in real Ghana MoMo scams.

### 10.4 Integration Steps

1. **Compute the 8 boolean flags** inside `sms_parser.py`'s `parse_sms()` — most already return data that maps to these flags (e.g., `amount`, `txn_id`, `balance`).
2. **Add `has_valid_mtn_format`** as a template-matching function that checks the canonical MTN message structure (field order, wording, presence of all expected sections).
3. **Add `has_character_anomaly`** by checking: name is ALL CAPS, currency is "GHS" not "GHC", no misspellings in keywords ("received" not "recieved"), txn ID is purely numeric.
4. **Add `has_urgency_language`** by scanning for a keyword list: `["avoid", "blocked", "reversal", "immediately", "urgent", "expire", "act now", "within"]`.
5. **Pipe the 8 flags into the composite score** in `fraud_engine.py` and return the risk label alongside the parser output.
6. **Log every scored SMS** to the `predictions` table so the admin review queue has context.

## 6. Integration With Your Existing System

This dataset feeds into your existing pipeline:

- `sms_parser.py` → extracts Group B features from `raw_sms`
- `behavioral_features.py` → computes Group C features from user history
- `train_model.py` → trains Random Forest on Groups A+B+C
- `predict_api.py` → Isolation Forest for anomaly detection
- `fraud_reviews` table → human labels feed back into training data

## 7. E-levy Reference (Ghana 2024–2026)

| Rule          | Detail                                                       |
| ------------- | ------------------------------------------------------------ |
| Rate          | 1% of transfer amount                                        |
| Threshold     | Applies to electronic transfers above GHS 100/day cumulative |
| Exempt        | Cash-in, cash-out at agents; airtime top-ups; bank-to-wallet |
| Applies to    | Person-to-person MoMo transfers, merchant payments           |
| Deducted from | Receiver's incoming amount (shown as E-levy line in SMS)     |

Use this table to validate whether e-levy values in sample messages are realistic.

## 8. Recommended Feature Weighting

For v1 of the model, prioritise features in this order:

| Priority    | Feature Group                        | Weight guidance | Rationale                                                                                                                   |
| ----------- | ------------------------------------ | --------------- | --------------------------------------------------------------------------------------------------------------------------- |
| 1 (highest) | **Text authenticity** (Group A)      | ~50%            | Wording, field labels, parser confidence, URLs, PIN requests, spelling — these separate all 3 classes without external data |
| 2           | **Structured consistency** (Group B) | ~30%            | E-levy math, balance arithmetic, field presence/absence, txn ID format — verifiable from the message alone                  |
| 3 (lowest)  | **User behavior** (Group C)          | ~20%            | Transaction timing, velocity, device/location novelty — useful refinement but should NOT be the primary discriminator       |

> **Design goal:** A model trained on Groups A+B alone (no user history) should achieve >80% accuracy across all three classes. Group C features improve precision but are not required for baseline separation.

---

## 9. Dataset Files

### v4 — Primary (20 samples)

`ml/data/momo_sms_training_seed_v4.csv`

- 20 rows: 10 genuine + 5 suspicious + 5 likely_fraudulent
- 28 columns (see Section 1)
- All genuine samples follow the exact canonical MTN MoMo template with correct e-levy math
- **All suspicious samples have at least one TEXT/STRUCTURE anomaly** (wrong wording, wrong field labels, swapped field order, format deviation, or e-levy math error) — detectable without user behavior
- All fraudulent samples have 2+ strong deception markers (URLs, PIN requests, spelling errors, wrong currency, missing most standard fields)
- Each sample's `notes` column documents the specific text/structure indicator(s) that justify its label

### v3 — Extended (35 samples)

`ml/data/momo_sms_training_seed_v3.csv`

- 35 rows: 15 genuine + 10 suspicious + 10 likely_fraudulent
- Same column structure and design principles as v4
- Superset with additional variety in transaction types and anomaly patterns

"""Generate the refined Phase 7 labeled SMS dataset (20 rows).

Run:  python ml/data/gen_phase7.py
Writes: ml/data/phase7_labeled_sms.csv
"""

import csv, os

HEADER = [
    "id","raw_text","source_type","transaction_type","direction",
    "amount","fee","balance_after","available_balance",
    "counterparty_name","counterparty_number","transaction_id","reference",
    "has_valid_mtn_format","has_balance_info","has_fee_info",
    "has_transaction_id","has_sender_name",
    "has_character_anomaly","has_spacing_anomaly","has_urgency_language",
    "label","notes",
]

ROWS = [
    # ──────────────────── GENUINE (1-10) ────────────────────
    [1,
     "You have received GHS 150.00 from KWAME MENSAH 0241234567. Transaction ID: 9384710236. Fee charged: GHS 0.00. E-levy: GHS 1.50. Your new balance is GHS 1,248.50. 15/03/2026 09:32.",
     "sms","transfer","incoming",150.00,1.50,1248.50,"",
     "KWAME MENSAH","0241234567","9384710236","",
     1,1,1,1,1, 0,0,0,
     "genuine",
     "Canonical MTN transfer. E-levy = 1% of 150. All fields present in standard order."],

    [2,
     "You have received GHS 75.50 from AMA BOATENG 0551987432. Transaction ID: 8472910348. Fee charged: GHS 0.00. E-levy: GHS 0.00. Your new balance is GHS 830.50. 16/03/2026 14:17.",
     "sms","transfer","incoming",75.50,0.00,830.50,"",
     "AMA BOATENG","0551987432","8472910348","",
     1,1,1,1,1, 0,0,0,
     "genuine",
     "Under GHS 100 so e-levy exempt. Standard template."],

    [3,
     "Cash In of GHS 200.00 at agent ISAAC DARKO 0201567893. Transaction ID: 1029384756. Your new balance is GHS 450.00. 17/03/2026 11:03.",
     "sms","deposit","incoming",200.00,0.00,450.00,"",
     "ISAAC DARKO","0201567893","1029384756","",
     1,1,0,1,1, 0,0,0,
     "genuine",
     "Cash-in template. No Fee/E-levy line (cash-in exempt by e-levy rules)."],

    [4,
     "You have received GHS 500.00 from ABENA OWUSU 0271098762. Transaction ID: 5647382917. Fee charged: GHS 0.00. E-levy: GHS 5.00. Your new balance is GHS 2,335.00. 18/03/2026 08:44.",
     "sms","transfer","incoming",500.00,5.00,2335.00,"",
     "ABENA OWUSU","0271098762","5647382917","",
     1,1,1,1,1, 0,0,0,
     "genuine",
     "E-levy = 5.00 (1% of 500). Round amount but common for peer transfers."],

    [5,
     "Payment of GHS 45.00 received from KOFI ASANTE 0541236789. Transaction ID: 2910485738. Fee charged: GHS 0.00. E-levy: GHS 0.00. Your new balance is GHS 1,095.00. 19/03/2026 16:22.",
     "sms","payment","incoming",45.00,0.00,1095.00,"",
     "KOFI ASANTE","0541236789","2910485738","",
     1,1,1,1,1, 0,0,0,
     "genuine",
     "Payment template. Under 100 so no e-levy."],

    [6,
     "You have received GHS 1,200.00 from EMMANUEL TETTEH 0261234589. Transaction ID: 8392017483. Fee charged: GHS 0.00. E-levy: GHS 12.00. Your new balance is GHS 3,488.00. 20/03/2026 10:05.",
     "sms","transfer","incoming",1200.00,12.00,3488.00,"",
     "EMMANUEL TETTEH","0261234589","8392017483","",
     1,1,1,1,1, 0,0,0,
     "genuine",
     "Large transfer. E-levy = 12.00 (1% of 1200)."],

    [7,
     "You have received GHS 22.00 from GIFTY LAMPTEY 0501234578. Transaction ID: 4728193054. Fee charged: GHS 0.00. E-levy: GHS 0.00. Your new balance is GHS 122.00. 20/03/2026 13:28.",
     "sms","transfer","incoming",22.00,0.00,122.00,"",
     "GIFTY LAMPTEY","0501234578","4728193054","",
     1,1,1,1,1, 0,0,0,
     "genuine",
     "Small odd amount. Under 100 so no e-levy."],

    [8,
     "You have received GHS 350.00 from YAW ADJEI 0241098763. Transaction ID: 9182736453. Fee charged: GHS 0.00. E-levy: GHS 3.50. Your new balance is GHS 696.50. 21/03/2026 07:14.",
     "sms","transfer","incoming",350.00,3.50,696.50,"",
     "YAW ADJEI","0241098763","9182736453","",
     1,1,1,1,1, 0,0,0,
     "genuine",
     "E-levy = 3.50 (1% of 350). Early morning transfer."],

    [9,
     "Cash In of GHS 100.00 at agent MERCY AGYEMANG 0551098762. Transaction ID: 5648291734. Your new balance is GHS 100.00. 21/03/2026 17:48.",
     "sms","deposit","incoming",100.00,0.00,100.00,"",
     "MERCY AGYEMANG","0551098762","5648291734","",
     1,1,0,1,1, 0,0,0,
     "genuine",
     "Cash-in template. Balance = amount (wallet was empty). No fee line."],

    [10,
     "You have received GHS 85.00 from SAMUEL OFORI 0271234569. Transaction ID: 7382910462. Fee charged: GHS 0.00. E-levy: GHS 0.00. Your new balance is GHS 535.00. 22/03/2026 12:01.",
     "sms","transfer","incoming",85.00,0.00,535.00,"",
     "SAMUEL OFORI","0271234569","7382910462","",
     1,1,1,1,1, 0,0,0,
     "genuine",
     "Under 100 so no e-levy. Standard midday transfer."],

    # ──────────────────── SUSPICIOUS (11-15) ────────────────────
    # Design: each has EXACTLY ONE subtle text/structure deviation.
    # Everything else matches the canonical MTN template perfectly.

    [11,
     "You have received GHS 800.00 from FRANCIS APPIAH 0249876543. Transaction ID: 7391048265. Fee charged: GHS 0.00. E-levy: GHS 0.00. Your new balance is GHS 2,150.00. 25/03/2026 14:10.",
     "sms","transfer","incoming",800.00,0.00,2150.00,"",
     "FRANCIS APPIAH","0249876543","7391048265","",
     0,1,1,1,1, 0,0,0,
     "suspicious",
     "SINGLE DEVIATION — e-levy math: GHS 0.00 on GHS 800 transfer (should be 8.00). Template wording, field order, formatting all canonical."],

    [12,
     "You have received GHS 3,000.00 from PRINCE OWUSU 0241111234. Transaction ID: 8473920165. E-levy: GHS 30.00. Fee charged: GHS 0.00. Your new balance is GHS 3,070.00. 26/03/2026 15:14.",
     "sms","transfer","incoming",3000.00,30.00,3070.00,"",
     "PRINCE OWUSU","0241111234","8473920165","",
     0,1,1,1,1, 0,0,0,
     "suspicious",
     "SINGLE DEVIATION — field order: E-levy line before Fee line. Real MTN always prints Fee first then E-levy. Values and wording are correct."],

    [13,
     "You have received GHS 250.00 from Ama Serwaa 0551234567. Transaction ID: 6482910374. Fee charged: GHS 0.00. E-levy: GHS 2.50. Your new balance is GHS 752.50. 27/03/2026 09:45.",
     "sms","transfer","incoming",250.00,2.50,752.50,"",
     "Ama Serwaa","0551234567","6482910374","",
     0,1,1,1,1, 1,0,0,
     "suspicious",
     "SINGLE DEVIATION — name casing: Title Case 'Ama Serwaa' instead of ALL CAPS 'AMA SERWAA'. Real MTN always renders names uppercase. Template otherwise canonical."],

    [14,
     "You have received GHS 5,000.00 from RICHARD BOATENG 0249871234. Transaction ID: 48293OI762. Fee charged: GHS 0.00. E-levy: GHS 50.00. Your new balance is GHS 5,150.00. 27/03/2026 11:30.",
     "sms","transfer","incoming",5000.00,50.00,5150.00,"",
     "RICHARD BOATENG","0249871234","48293OI762","",
     0,1,1,0,1, 1,0,0,
     "suspicious",
     "SINGLE DEVIATION — txn ID format: '48293OI762' mixes letters O and I with digits. Visually similar to 0 and 1 but fails pure-numeric check. Template otherwise canonical."],

    [15,
     "You have received GHS 400.00 from BENJAMIN OFORI 0261111222. Transaction ID: 3948201756. Fee charged: GHS 0.00. E-levy: GHS 4.00. Your new balance is GHS 1,504.00. Ref: MP260328.1320. 28/03/2026 13:20.",
     "sms","transfer","incoming",400.00,4.00,1504.00,"",
     "BENJAMIN OFORI","0261111222","3948201756","MP260328.1320",
     0,1,1,1,1, 0,0,0,
     "suspicious",
     "SINGLE DEVIATION — extra field: 'Ref: MP260328.1320' inserted between balance and datetime. Real MTN SMS never includes a Ref line. Template otherwise canonical."],

    # ──────────────────── LIKELY FRAUDULENT (16-20) ────────────────────
    # Design: realistic Ghana MoMo scam patterns. Missing multiple standard
    # fields and/or social engineering content. Less exaggerated than v1.

    [16,
     "You have received GHS 2,000.00 from JAMES MENSAH 0241234567. Transaction ID: 1111111111. Your new balance is GHS 2,050.00. This was sent in error. Kindly return GHS 2,000.00 to 0241234567 to avoid your account being blocked.",
     "sms","transfer","incoming",2000.00,0.00,2050.00,"",
     "JAMES MENSAH","0241234567","1111111111","",
     0,1,0,1,1, 0,0,1,
     "likely_fraudulent",
     "Reversal scam. Semi-structured: has name, phone, txn ID, balance. But: missing Fee/E-levy lines, missing datetime, fabricated txn ID (all 1s), and appends social engineering asking victim to 'return' money. 'avoid your account being blocked' = urgency."],

    [17,
     "MTN MoMo: Your wallet has been credited with GHS 5,000.00. To complete this transaction call our verification line at 0209999999. Failure to verify within 24hrs will result in reversal.",
     "sms","transfer","incoming",5000.00,0.00,"","",
     "","0209999999","","",
     0,0,0,0,0, 0,0,1,
     "likely_fraudulent",
     "Vishing scam. 'MTN MoMo:' prefix is not real MTN format. 'credited' not 'received'. No txn ID, no balance, no fee, no sender name, no datetime. Directs victim to call fake verification number. 'within 24hrs' + 'reversal' = urgency."],

    [18,
     "You have recieved GHS 3,500.00 into your MTN MoMo acount. Your funds are temporarily on hold due to system maintanance. Please call 0207777321 to release your funds.",
     "sms","transfer","incoming",3500.00,0.00,"","",
     "","0207777321","","",
     0,0,0,0,0, 1,0,0,
     "likely_fraudulent",
     "Spelling-error scam. Three misspellings: 'recieved', 'acount', 'maintanance'. Real MTN SMS is machine-generated with zero typos. Wrong template structure. Missing all standard fields (txn ID, balance, fee, name, datetime). Directs victim to call."],

    [19,
     "Dear customer you have received GHC 6,000 in ur MoMo wallet from CHIEF NANA OSEI. Pls kindly send back GHC 3,000 to 0249999888 as it was sent by mistake. God bless you.",
     "sms","transfer","incoming",6000.00,0.00,"","",
     "CHIEF NANA OSEI","0249999888","","",
     0,0,0,0,1, 1,0,0,
     "likely_fraudulent",
     "Send-back scam with wrong currency. 'GHC' is pre-2007 code (real MTN uses 'GHS'). Informal language: 'ur', 'Pls kindly', 'God bless you' = human-written not system-generated. Missing txn ID, balance, fee, datetime. Social engineering asks victim to return money."],

    [20,
     "MTN Mobile Money: A deposit of GHS 8,500.00 has been made to your account. For security purposes confirm your identity by replying with your MoMo PIN and date of birth.",
     "sms","transfer","incoming",8500.00,0.00,"","",
     "","","","",
     0,0,0,0,0, 0,0,0,
     "likely_fraudulent",
     "Identity theft scam. 'MTN Mobile Money:' prefix is not real MTN format. 'deposit...has been made' is wrong template. Asks for MoMo PIN + date of birth via SMS reply. No txn ID, no balance, no fee, no counterparty, no datetime. No explicit urgency words but intent is data harvesting."],
]

# ── Write CSV ──
out_path = os.path.join(os.path.dirname(__file__), "phase7_labeled_sms.csv")
with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(HEADER)
    for row in ROWS:
        assert len(row) == len(HEADER), f"Row {row[0]}: {len(row)} cols (expected {len(HEADER)})"
        writer.writerow(row)

print(f"Wrote {len(ROWS)} rows to {out_path}")

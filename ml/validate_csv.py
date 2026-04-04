"""
validate_csv.py — Check fraud_training_data.csv for column-count errors
========================================================================
Reads every line and reports any row whose field count doesn't match
the header.  Uses Python's built-in csv module so quoted commas
(e.g. "GHS 1,248.50") are handled correctly.

Usage:
    python validate_csv.py
"""

import csv
import os

CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "fraud_training_data.csv")

with open(CSV_PATH, "r", encoding="utf-8") as f:
    reader = csv.reader(f)
    header = next(reader)
    expected = len(header)
    print(f"Header has {expected} columns")

    bad_rows = []
    for line_num, row in enumerate(reader, start=2):
        if len(row) != expected:
            bad_rows.append((line_num, len(row), row))

if bad_rows:
    print(f"\n*** {len(bad_rows)} bad row(s) found ***\n")
    for line_num, count, row in bad_rows:
        print(f"  Line {line_num}: {count} fields (expected {expected})")
        # Show just the first 3 and last 3 fields so it's readable
        preview = row[:3] + ["..."] + row[-3:]
        print(f"    Preview: {preview}\n")
else:
    print("All rows OK — every row has exactly {expected} columns.".format(expected=expected))

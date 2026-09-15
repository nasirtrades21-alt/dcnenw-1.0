"""
scraper/export.py

WHAT THIS FILE DOES (plain English):
Reads the qualified properties out of the SQLite database and writes them
to data/leads.csv — the file you'll actually open/download from GitHub.

Per the spec: this file does NOT decide who qualifies. It only exports
properties that were already marked acquisition_qualified = 1 upstream.
It does re-check the core buy-box numbers as a final safety net before
writing each row, in case of a data bug elsewhere.

Run it with:  python scraper/export.py
(fetch.py will also call this automatically once wired in.)
"""

import csv
import os

from scraper import database

OUTPUT_PATH = "data/leads.csv"

CSV_COLUMNS = [
    "owner",
    "property_address",
    "quadrant",
    "normalized_property_type",
    "building_area",
    "land_area",
    "tax_assessed_value",
    "vacant",
    "last_sale_date",
    "last_sale_price",
    "ssl",
]


def _passes_safety_check(row):
    """Second layer of protection — a qualified row must still make sense."""
    if row.get("quadrant") not in ("NW", "NE"):
        return False
    if row.get("normalized_property_type") not in ("SINGLE_FAMILY", "TOWNHOME"):
        return False
    if row.get("building_area") is None or row["building_area"] < 1300:
        return False
    if row.get("tax_assessed_value") is None or row["tax_assessed_value"] < 350000:
        return False
    return True


def export_leads_csv():
    qualified = database.get_qualified_properties()
    safe_rows = [r for r in qualified if _passes_safety_check(r)]

    if not safe_rows and os.path.exists(OUTPUT_PATH):
        # Don't overwrite a known-good CSV with an empty one on a bad run.
        print(f"[export] 0 safe rows to export — leaving existing {OUTPUT_PATH} untouched.")
        return 0

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in safe_rows:
            writer.writerow(row)

    print(f"[export] wrote {len(safe_rows)} qualified properties to {OUTPUT_PATH}")
    return len(safe_rows)


if __name__ == "__main__":
    export_leads_csv()

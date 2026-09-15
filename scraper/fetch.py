"""
scraper/fetch.py

WHAT THIS FILE DOES (plain English):
This is the "master switch." Running this one file does the entire job:

  1. Pull raw data from the 3 DCGIS sources (dcgis.py)
  2. Merge + clean it into one record per property (normalize.py)
  3. Run every property through the buy-box filter (normalize.py)
  4. Save everything to the SQLite database (database.py)
  5. Print a plain-English summary of what happened

If ANY one source fails, the run keeps going with whatever sources DID
succeed, and the failure is clearly reported at the end — a bad DCGIS
request should never silently wipe out a good day's data.

Run it with:  python scraper/fetch.py
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from scraper import dcgis, normalize, database, export


def load_config():
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


def main():
    run_started_at = datetime.now(timezone.utc).isoformat()
    print("DC ACQUISITION ENGINE")
    print("=" * 40)
    print(f"Run: {run_started_at}\n")

    config = load_config()
    criteria = {
        "geography_quadrants": config["geography"]["quadrants"],
        "property_types": config["acquisition_criteria"]["property_types"],
        "minimum_building_area": config["acquisition_criteria"]["minimum_building_area"],
        "minimum_tax_assessed_value": config["acquisition_criteria"]["minimum_tax_assessed_value"],
    }

    sources_status = {}
    cama_rows, vacant_rows, quadrant_rows = [], [], []

    print("Fetching sources...")
    try:
        cama_rows = dcgis.fetch_residential_cama()
        sources_status["Residential CAMA"] = "SUCCESS"
    except Exception as e:
        sources_status["Residential CAMA"] = f"FAILED ({e})"

    try:
        vacant_rows = dcgis.fetch_vacant_property()
        sources_status["Vacant Property"] = "SUCCESS"
    except Exception as e:
        sources_status["Vacant Property"] = f"FAILED ({e})"

    try:
        quadrant_rows = dcgis.fetch_tax_lots_quadrant()
        sources_status["Tax Lots (Quadrant)"] = "SUCCESS"
    except Exception as e:
        sources_status["Tax Lots (Quadrant)"] = f"FAILED ({e})"

    failed_sources = [name for name, status in sources_status.items() if status != "SUCCESS"]

    print("\nMerging + normalizing...")
    properties = normalize.merge_sources(cama_rows, vacant_rows, quadrant_rows)
    properties = normalize.run_qualification(properties, criteria)

    total_retrieved = len(properties)
    qualified = {ssl: p for ssl, p in properties.items() if p["acquisition_qualified"]}

    print("Saving to database...")
    database.init_db()
    database.upsert_properties(properties)

    print("Exporting CSV...")
    export.export_leads_csv()

    overall_status = "SUCCESS" if not failed_sources else "PARTIAL"
    database.log_run(run_started_at, overall_status, total_retrieved, len(qualified), failed_sources)

    # ---- Summary ----
    print("\nSources:")
    for name, status in sources_status.items():
        print(f"  {name:<25} {status}")

    print(f"\nProperties Retrieved: {total_retrieved}")
    print(f"Properties Qualified: {len(qualified)}")

    nw_count = sum(1 for p in qualified.values() if p["quadrant"] == "NW")
    ne_count = sum(1 for p in qualified.values() if p["quadrant"] == "NE")
    vacant_count = sum(1 for p in qualified.values() if p["vacant"])
    print(f"  NW: {nw_count}")
    print(f"  NE: {ne_count}")
    print(f"  Vacant: {vacant_count}")

    print(f"\nStatus:\n{overall_status}")
    if failed_sources:
        print(f"\nFailed:\n{', '.join(failed_sources)}")


if __name__ == "__main__":
    main()

"""
scraper/dcgis.py

WHAT THIS FILE DOES (plain English):
DC's government publishes property data through "ArcGIS FeatureServer" web
services. Think of each one as a giant spreadsheet you can query over the
internet. This file knows how to ask each spreadsheet for ALL of its rows
(they only give you 2,000 rows at a time, so we have to ask repeatedly,
which is called "pagination") and hand back plain Python dictionaries.

This file does NOT decide who qualifies for anything. It only fetches raw
data. normalize.py is where raw data gets turned into clean property
records, and where the buy-box filter gets applied.

THREE LAYERS THIS FILE TALKS TO:

1. RESIDENTIAL_CAMA   - building characteristics (square footage, style)
2. VACANT_PROPERTY     - address, owner, assessed value, vacancy
                         (NOTE: only covers properties currently vacant —
                         see README "Known Gaps" for why this is a problem
                         we still need to solve)
3. TAX_LOTS            - the official QUADRANT (NW/NE/SW/SE) field

MaxRecordCount for these services is 2000, so fetch_all_records() below
loops, asking for records 0-1999, then 2000-3999, etc., until the server
sends back fewer rows than we asked for (which means we've reached the end).
"""

import requests
import time

RESIDENTIAL_CAMA_URL = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/"
    "Property_and_Land_WebMercator/FeatureServer/25/query"
)
VACANT_PROPERTY_URL = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/"
    "Property_and_Land_WebMercator/FeatureServer/58/query"
)
TAX_LOTS_URL = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/"
    "Property_and_Land_WebMercator/MapServer/39/query"
)

PAGE_SIZE = 2000
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30


def _fetch_page(base_url, out_fields, offset, where="1=1"):
    """
    Ask the server for one page (up to PAGE_SIZE rows) starting at `offset`.
    Retries up to MAX_RETRIES times if the request fails or times out.
    Returns a list of dicts, one per row. Returns None if all retries failed
    (the caller decides what "the whole source failed" means).
    """
    params = {
        "where": where,
        "outFields": out_fields,
        "f": "json",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(base_url, params=params, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()

            if "error" in payload:
                raise RuntimeError(f"ArcGIS returned an error: {payload['error']}")

            features = payload.get("features", [])
            # Each "feature" wraps the real data in an "attributes" dict.
            return [f["attributes"] for f in features]

        except Exception as e:
            last_error = e
            print(f"  [retry {attempt}/{MAX_RETRIES}] {base_url} offset={offset} failed: {e}")
            time.sleep(2 * attempt)  # back off a little longer each retry

    print(f"  [FAILED] {base_url} offset={offset} — giving up after {MAX_RETRIES} retries: {last_error}")
    return None


def fetch_all_records(base_url, out_fields="*", where="1=1"):
    """
    Pages through an entire ArcGIS layer and returns every row as a list of
    dicts. Raises RuntimeError if any page fails, so the caller (fetch.py)
    can mark that whole source as FAILED without crashing the entire run.
    """
    all_rows = []
    offset = 0

    while True:
        page = _fetch_page(base_url, out_fields, offset, where=where)
        if page is None:
            raise RuntimeError(f"Could not fully fetch {base_url} (failed at offset {offset})")

        all_rows.extend(page)

        if len(page) < PAGE_SIZE:
            # Got back fewer rows than we asked for -> that was the last page.
            break

        offset += PAGE_SIZE

    return all_rows


def fetch_residential_cama():
    """Building characteristics: SSL, GBA (building sq ft), style, land area."""
    fields = "SSL,GBA,LANDAREA,USECODE,STYLE_D,STRUCT_D,STORIES,SALEDATE,PRICE,BLDG_NUM"
    return fetch_all_records(RESIDENTIAL_CAMA_URL, out_fields=fields)


def fetch_vacant_property():
    """
    Address, owner, and CURRENT assessed value — but ONLY for properties
    currently flagged vacant. See README "Known Gaps": we still need the
    full (non-vacant-only) version of this table for the rest of the
    property universe.
    """
    fields = (
        "SSL,PROPERTY_ADDRESS,OWNER_NAME_PRIMARY,OWNER_NAME_SECONDARY,"
        "APPRAISED_VALUE_CURRENT_TOTAL,LAND_USE_CODE,LAND_USE_DESCRIPTION,"
        "LAST_SALE_DATE,LAST_SALE_PRICE,VACANT_USE"
    )
    return fetch_all_records(VACANT_PROPERTY_URL, out_fields=fields)


def fetch_tax_lots_quadrant():
    """The official QUADRANT field (NW/NE/SW/SE) keyed by SSL."""
    fields = "SSL,QUADRANT"
    return fetch_all_records(TAX_LOTS_URL, out_fields=fields)


if __name__ == "__main__":
    # Quick manual smoke test: fetch a handful of rows from each source and
    # print counts. Run with: python scraper/dcgis.py
    print("Fetching Residential CAMA...")
    cama = fetch_residential_cama()
    print(f"  -> {len(cama)} rows")

    print("Fetching Vacant Property...")
    vacant = fetch_vacant_property()
    print(f"  -> {len(vacant)} rows")

    print("Fetching Tax Lots (quadrant)...")
    lots = fetch_tax_lots_quadrant()
    print(f"  -> {len(lots)} rows")

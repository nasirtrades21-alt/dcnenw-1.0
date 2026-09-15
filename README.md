# DC Acquisition Engine

A daily screener for Washington, DC properties that:
1. Pulls official DCGIS property data
2. Filters to NW/NE, single-family or townhome, 1,300+ SF, $350K+ assessed value
3. Flags vacancy as a distress signal
4. Outputs a clean list of qualified properties

**Mortgage status is NOT checked.** The original spec called for excluding
properties with an active mortgage, but that requirement was dropped by the
project owner — parsing DC land records for deed-of-trust releases/
satisfactions is out of scope for this build. There is no `deeds.py` and no
mortgage field gates qualification.

## How to run it

```bash
pip install -r requirements.txt
python scraper/fetch.py
```

This fetches fresh data, applies the buy-box filter, saves results to
`data/dc_acquisition.db` (SQLite), and prints a summary.

## Official data sources used

| Data | Source | Field(s) |
|---|---|---|
| Building size, style | [Residential CAMA](https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Property_and_Land_WebMercator/FeatureServer/25) | `GBA`, `STRUCT_D` |
| Address, owner, assessed value, vacancy | [Vacant Property](https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Property_and_Land_WebMercator/FeatureServer/58) | `PROPERTY_ADDRESS`, `OWNER_NAME_PRIMARY`, `APPRAISED_VALUE_CURRENT_TOTAL` |
| Quadrant | [Tax Lots](https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Property_and_Land_WebMercator/MapServer/39) | `QUADRANT` (coded values NW/NE/SW/SE) |

All three are queried live — nothing is hardcoded or scraped from a static
export.

## Known gaps (do not treat this as production-ready without addressing these)

1. **Non-vacant properties aren't fully covered yet.** The "Vacant Property"
   layer above is explicitly documented by DC as *a subset of the full
   ITSPE tax roll containing only vacant properties*. That means right now
   the pipeline can only assign `tax_assessed_value` and `owner` to
   properties that happen to be vacant. We still need to find and wire in
   the full (all-properties) ITSPE/assessment-roll layer so occupied
   qualifying properties get an assessed value too. Until that's done,
   **qualified results will be biased toward vacant properties** and will
   undercount the true acquisition universe.

2. **Property-type mapping is an unverified draft.** `normalize.py` maps
   DC's free-text `STRUCT_D` field to `SINGLE_FAMILY` / `TOWNHOME` using
   keyword matching (e.g. "row", "town", "detached"). This was written
   without access to real sample rows to confirm exact wording DC uses.
   **Before trusting output, pull 50-100 real rows and check the mapping
   catches what you expect and excludes what you don't.**

3. **Code violations are not built yet.** The original spec calls for a
   `code_violations.py` connector against an official (non-311) DC source.
   That source still needs to be identified.

4. **Scoring, CSV export, dashboard, and GitHub Actions are not built yet.**
   This phase covers fetch → normalize → buy-box filter → SQLite only.

## Project structure so far

```
dc-acquisition-engine/
├── scraper/
│   ├── dcgis.py       # fetches raw data from the 3 sources above
│   ├── normalize.py   # merges sources, maps property type, buy-box gate
│   ├── database.py    # SQLite storage (upsert, never recreates)
│   └── fetch.py        # runs the whole pipeline end to end
├── config/
│   └── settings.yaml   # buy-box criteria + data source URLs
├── requirements.txt
└── README.md
```

Not yet built: `data/leads.csv` export, `dashboard/`, `.github/workflows/scrape.yml`.

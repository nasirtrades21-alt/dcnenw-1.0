"""
scraper/normalize.py

WHAT THIS FILE DOES (plain English):
dcgis.py hands us three separate lists of raw rows (building info, vacant/
owner info, quadrant info). This file:

  1. Merges those three lists together by SSL (the property ID) into ONE
     clean dictionary per property.
  2. Converts DC's raw property-type text into just two buckets we care
     about: SINGLE_FAMILY or TOWNHOME (everything else gets excluded).
  3. Runs the "buy box" gate (NW/NE, >=1300 SF, >=$350k assessed value) and
     records a plain-English reason for every property that gets excluded.

IMPORTANT — READ THIS BEFORE TRUSTING PROPERTY-TYPE RESULTS:
DC's official numeric USECODE -> property type mapping was NOT verified
against real sample data (we only inspected the field LIST, not actual
values, since this environment has no way to run Python against the live
service). The mapping below uses the human-readable STRUCT_D text field as
a stand-in and is a best-effort guess, not a confirmed mapping. Per the
project spec's own instruction ("do not guess the DC property-type
classification"), TREAT THIS AS A DRAFT and verify it against real rows
before relying on it for real acquisition decisions. See README.md
"Known Gaps".
"""

# Draft mapping — VERIFY AGAINST REAL DATA, do not trust blindly.
# Keys are lowercased substrings we look for in STRUCT_D / LAND_USE_DESCRIPTION.
_SINGLE_FAMILY_HINTS = ["single family", "single-family", "detached"]
_TOWNHOME_HINTS = ["row", "town", "semi-detached", "attached"]

_EXCLUDE_HINTS = ["condo", "apartment", "multi", "commercial", "vacant land"]


def normalize_property_type(struct_d, land_use_description):
    """
    Best-effort mapping from DC's free-text structure/land-use description
    to our two allowed buckets. Returns SINGLE_FAMILY, TOWNHOME, or UNKNOWN.

    UNVERIFIED — see module docstring. UNKNOWN properties get excluded by
    the buy-box gate below, which is the safe default per the spec
    ("do not guess... exclude unless definitively mapped").
    """
    text = f"{struct_d or ''} {land_use_description or ''}".lower()

    if any(hint in text for hint in _EXCLUDE_HINTS):
        return "UNKNOWN"
    if any(hint in text for hint in _SINGLE_FAMILY_HINTS):
        return "SINGLE_FAMILY"
    if any(hint in text for hint in _TOWNHOME_HINTS):
        return "TOWNHOME"
    return "UNKNOWN"


def merge_sources(cama_rows, vacant_rows, quadrant_rows):
    """
    Combines the three raw row lists into one dict keyed by SSL.
    Every property that appears in ANY of the three sources gets an entry;
    missing pieces are just left as None (handled later by the buy-box gate).
    """
    properties = {}

    def get_or_create(ssl):
        if ssl not in properties:
            properties[ssl] = {
                "ssl": ssl,
                "property_address": None,
                "owner": None,
                "quadrant": None,
                "building_area": None,
                "land_area": None,
                "tax_assessed_value": None,
                "struct_d": None,
                "land_use_description": None,
                "vacant": False,
                "last_sale_date": None,
                "last_sale_price": None,
            }
        return properties[ssl]

    for row in cama_rows:
        ssl = row.get("SSL")
        if not ssl:
            continue
        p = get_or_create(ssl)
        p["building_area"] = row.get("GBA")
        p["land_area"] = row.get("LANDAREA")
        p["struct_d"] = row.get("STRUCT_D")

    for row in vacant_rows:
        ssl = row.get("SSL")
        if not ssl:
            continue
        p = get_or_create(ssl)
        p["property_address"] = row.get("PROPERTY_ADDRESS")
        p["owner"] = row.get("OWNER_NAME_PRIMARY")
        p["tax_assessed_value"] = row.get("APPRAISED_VALUE_CURRENT_TOTAL")
        p["land_use_description"] = row.get("LAND_USE_DESCRIPTION")
        p["last_sale_date"] = row.get("LAST_SALE_DATE")
        p["last_sale_price"] = row.get("LAST_SALE_PRICE")
        # This source is VACANT-PROPERTY-ONLY, so if a property shows up
        # here at all, it is currently vacant.
        p["vacant"] = True

    for row in quadrant_rows:
        ssl = row.get("SSL")
        if not ssl:
            continue
        p = get_or_create(ssl)
        p["quadrant"] = row.get("QUADRANT")

    return properties


def apply_buy_box(property_record, criteria):
    """
    Runs one property through the hard buy-box gate.
    Returns (qualified: bool, exclusion_reason: str or None).

    `criteria` is the acquisition_criteria block from config/settings.yaml.
    """
    p = property_record

    if p["quadrant"] not in criteria["geography_quadrants"]:
        return False, "OUTSIDE_TARGET_QUADRANT" if p["quadrant"] else "UNKNOWN_QUADRANT"

    normalized_type = normalize_property_type(p["struct_d"], p["land_use_description"])
    p["normalized_property_type"] = normalized_type
    if normalized_type not in criteria["property_types"]:
        return False, "UNKNOWN_PROPERTY_TYPE" if normalized_type == "UNKNOWN" else "PROPERTY_TYPE_NOT_TARGET"

    if p["building_area"] is None:
        return False, "MISSING_BUILDING_AREA"
    if p["building_area"] < criteria["minimum_building_area"]:
        return False, "UNDER_1300_SF"

    if p["tax_assessed_value"] is None:
        return False, "MISSING_ASSESSED_VALUE"
    if p["tax_assessed_value"] < criteria["minimum_tax_assessed_value"]:
        return False, "ASSESSED_VALUE_BELOW_350000"

    return True, None


def run_qualification(properties, criteria):
    """
    Takes the merged property dict (from merge_sources) and stamps every
    property with acquisition_qualified / acquisition_exclusion_reason.
    Returns the same dict, mutated in place, for convenience.
    """
    for ssl, p in properties.items():
        qualified, reason = apply_buy_box(p, criteria)
        p["acquisition_qualified"] = qualified
        p["acquisition_exclusion_reason"] = reason
    return properties

"""
scraper/database.py

WHAT THIS FILE DOES (plain English):
Stores properties in a SQLite database file (data/dc_acquisition.db).
SQLite is just a database that lives in a single file — no server to set up.

We use "upsert" (update-or-insert): if a property (by SSL) is already in
the database, we update it; if it's new, we insert it. We NEVER delete or
recreate the table, so history is preserved run over run, per the spec.
"""

import sqlite3
from datetime import datetime, timezone

DB_PATH = "data/dc_acquisition.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
    ssl TEXT PRIMARY KEY,
    property_address TEXT,
    owner TEXT,
    quadrant TEXT,
    normalized_property_type TEXT,
    building_area REAL,
    land_area REAL,
    tax_assessed_value REAL,
    vacant INTEGER,
    last_sale_date TEXT,
    last_sale_price REAL,
    acquisition_qualified INTEGER,
    acquisition_exclusion_reason TEXT,
    first_seen TEXT,
    last_seen TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_properties_qualified ON properties(acquisition_qualified);
CREATE INDEX IF NOT EXISTS idx_properties_quadrant ON properties(quadrant);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_started_at TEXT,
    run_finished_at TEXT,
    status TEXT,
    properties_retrieved INTEGER,
    properties_qualified INTEGER,
    failed_sources TEXT
);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def upsert_properties(properties: dict):
    """
    properties: dict of {ssl: property_record_dict}, as produced by
    normalize.run_qualification().
    """
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

    for ssl, p in properties.items():
        existing = conn.execute(
            "SELECT first_seen FROM properties WHERE ssl = ?", (ssl,)
        ).fetchone()
        first_seen = existing[0] if existing else now

        conn.execute(
            """
            INSERT INTO properties (
                ssl, property_address, owner, quadrant, normalized_property_type,
                building_area, land_area, tax_assessed_value, vacant,
                last_sale_date, last_sale_price,
                acquisition_qualified, acquisition_exclusion_reason,
                first_seen, last_seen, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ssl) DO UPDATE SET
                property_address=excluded.property_address,
                owner=excluded.owner,
                quadrant=excluded.quadrant,
                normalized_property_type=excluded.normalized_property_type,
                building_area=excluded.building_area,
                land_area=excluded.land_area,
                tax_assessed_value=excluded.tax_assessed_value,
                vacant=excluded.vacant,
                last_sale_date=excluded.last_sale_date,
                last_sale_price=excluded.last_sale_price,
                acquisition_qualified=excluded.acquisition_qualified,
                acquisition_exclusion_reason=excluded.acquisition_exclusion_reason,
                last_seen=excluded.last_seen,
                updated_at=excluded.updated_at
            """,
            (
                ssl,
                p.get("property_address"),
                p.get("owner"),
                p.get("quadrant"),
                p.get("normalized_property_type"),
                p.get("building_area"),
                p.get("land_area"),
                p.get("tax_assessed_value"),
                1 if p.get("vacant") else 0,
                p.get("last_sale_date"),
                p.get("last_sale_price"),
                1 if p.get("acquisition_qualified") else 0,
                p.get("acquisition_exclusion_reason"),
                first_seen,
                now,
                now,
            ),
        )

    conn.commit()
    conn.close()


def log_run(run_started_at, status, properties_retrieved, properties_qualified, failed_sources):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO runs (run_started_at, run_finished_at, status,
                           properties_retrieved, properties_qualified, failed_sources)
        VALUES (?,?,?,?,?,?)
        """,
        (
            run_started_at,
            datetime.now(timezone.utc).isoformat(),
            status,
            properties_retrieved,
            properties_qualified,
            ",".join(failed_sources) if failed_sources else "",
        ),
    )
    conn.commit()
    conn.close()


def get_qualified_properties():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM properties WHERE acquisition_qualified = 1"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

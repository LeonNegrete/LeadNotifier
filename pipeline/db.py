"""
Persistence layer: SQLite database that lives at the repo root as leads.db
and gets committed/pushed by the GitHub Action, then git-pulled by the CLI.
"""

import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).resolve().parent.parent / "leads.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identifier_hash TEXT UNIQUE NOT NULL,
    property_type TEXT,
    lead_type TEXT,
    property_name TEXT,
    location TEXT,
    project_stage TEXT,
    interior_studio TEXT,
    investor_chain TEXT,
    source_url TEXT,
    lead_status TEXT DEFAULT 'New',
    detection_date TEXT,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT,
    articles_scanned INTEGER,
    new_leads INTEGER,
    notes TEXT
);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _migrate(conn):
    """Add columns to an existing leads.db that predates them. Safe to run every time."""
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(leads)")}
    if "property_type" not in existing_cols:
        conn.execute("ALTER TABLE leads ADD COLUMN property_type TEXT")
    if "lead_type" not in existing_cols:
        conn.execute("ALTER TABLE leads ADD COLUMN lead_type TEXT")


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    conn.close()


def make_hash(source_url: str, property_name: str) -> str:
    """Stable identifier so the same property/article doesn't get inserted twice."""
    key = f"{source_url.strip().lower()}|{(property_name or '').strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def lead_exists(conn, identifier_hash: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM leads WHERE identifier_hash = ? LIMIT 1", (identifier_hash,)
    )
    return cur.fetchone() is not None


def insert_lead(conn, lead: dict) -> bool:
    """
    Insert a lead dict with keys matching the schema.
    Returns True if a new row was inserted, False if it was a duplicate (skipped).
    """
    identifier_hash = make_hash(lead.get("source_url", ""), lead.get("property_name", ""))

    if lead_exists(conn, identifier_hash):
        return False

    conn.execute(
        """
        INSERT INTO leads (
            identifier_hash, property_type, lead_type, property_name, location, project_stage,
            interior_studio, investor_chain, source_url, lead_status,
            detection_date, summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'New', ?, ?)
        """,
        (
            identifier_hash,
            lead.get("property_type"),
            lead.get("lead_type"),
            lead.get("property_name"),
            lead.get("location"),
            lead.get("project_stage"),
            lead.get("interior_studio"),
            lead.get("investor_chain"),
            lead.get("source_url"),
            datetime.now(timezone.utc).isoformat(),
            lead.get("summary"),
        ),
    )
    return True


def log_run(conn, articles_scanned: int, new_leads: int, notes: str = ""):
    conn.execute(
        "INSERT INTO run_log (run_date, articles_scanned, new_leads, notes) VALUES (?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), articles_scanned, new_leads, notes),
    )


def get_new_leads(conn):
    cur = conn.execute(
        "SELECT * FROM leads WHERE lead_status = 'New' ORDER BY detection_date DESC"
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def mark_reviewed(conn, lead_ids: list):
    if not lead_ids:
        return
    placeholders = ",".join("?" for _ in lead_ids)
    conn.execute(
        f"UPDATE leads SET lead_status = 'Reviewed' WHERE id IN ({placeholders})",
        lead_ids,
    )

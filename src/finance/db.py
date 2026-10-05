"""SQLite connection and schema."""

import sqlite3
from pathlib import Path

from finance.sources import SOURCES

SCHEMA = """
CREATE TABLE IF NOT EXISTS income_source (
    key      TEXT PRIMARY KEY,
    label    TEXT NOT NULL,
    in_netto INTEGER NOT NULL,
    sort     INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS import_log (
    id                   INTEGER PRIMARY KEY,
    kind                 TEXT NOT NULL,          -- 'income'
    filename             TEXT NOT NULL,
    sha256               TEXT NOT NULL,
    imported_at          TEXT NOT NULL,          -- ISO local time
    year                 INTEGER NOT NULL,
    months               INTEGER NOT NULL,
    estimate_months_json TEXT NOT NULL,
    warnings_json        TEXT NOT NULL,
    mismatches_json      TEXT NOT NULL,
    changes_json         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS income_entry (
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    source_key  TEXT NOT NULL REFERENCES income_source(key),
    amount_ore  INTEGER NOT NULL,
    is_estimate INTEGER NOT NULL,
    import_id   INTEGER NOT NULL REFERENCES import_log(id),
    PRIMARY KEY (year, month, source_key)
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # One connection per request; FastAPI may run the dependency and the endpoint on
    # different threads, but never concurrently, so the same-thread check is not needed.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    seed_sources(conn)


def seed_sources(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executemany(
            """INSERT INTO income_source (key, label, in_netto, sort) VALUES (?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET label = excluded.label,
                   in_netto = excluded.in_netto, sort = excluded.sort""",
            [(s.key, s.label, int(s.in_netto), s.sort) for s in SOURCES],
        )

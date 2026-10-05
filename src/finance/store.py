"""Reading and writing income data. Every import replaces its year in one transaction."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from finance.importers.income import ParsedIncome
from finance.income import MonthRow, netto_mismatches
from finance.sources import SOURCES_BY_KEY


@dataclass
class ImportOutcome:
    import_id: int
    identical: bool  # same file as the latest import for this year; nothing was written


def _latest_import(conn: sqlite3.Connection, year: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, sha256 FROM import_log WHERE kind = 'income' AND year = ? ORDER BY id DESC LIMIT 1",
        (year,),
    ).fetchone()


def _compute_changes(old: dict[tuple[int, str], tuple[int, bool]], parsed: ParsedIncome) -> list[dict]:
    new = {(m.month, k): (v, m.is_estimate) for m in parsed.months for k, v in m.amounts.items()}
    changes: list[dict] = []
    display_order = lambda ms: (ms[0], SOURCES_BY_KEY[ms[1]].sort if ms[1] in SOURCES_BY_KEY else 999, ms[1])
    for month, source in sorted(old.keys() | new.keys(), key=display_order):
        old_ore = old.get((month, source), (0, False))[0]
        new_ore = new.get((month, source), (0, False))[0]
        if old_ore != new_ore:
            changes.append({"month": month, "source": source, "old_ore": old_ore, "new_ore": new_ore})

    old_est = {}
    for (month, _), (_, est) in old.items():
        old_est[month] = old_est.get(month, False) or est
    for m in parsed.months:
        if m.month in old_est and old_est[m.month] != m.is_estimate:
            changes.append({"month": m.month, "estimate_to_actual": not m.is_estimate})
    return changes


def _insert_entries(conn: sqlite3.Connection, parsed: ParsedIncome, import_id: int) -> None:
    conn.executemany(
        """INSERT INTO income_entry (year, month, source_key, amount_ore, is_estimate, import_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (parsed.year, m.month, key, ore, int(m.is_estimate), import_id)
            for m in parsed.months
            for key, ore in m.amounts.items()
        ],
    )


def save_income_import(
    conn: sqlite3.Connection, parsed: ParsedIncome, filename: str, sha256: str, now: datetime
) -> ImportOutcome:
    """Replace `parsed.year` atomically. Re-uploading the same file writes nothing."""
    latest = _latest_import(conn, parsed.year)
    if latest is not None and latest["sha256"] == sha256:
        return ImportOutcome(import_id=latest["id"], identical=True)

    with conn:
        old = {
            (r["month"], r["source_key"]): (r["amount_ore"], bool(r["is_estimate"]))
            for r in conn.execute(
                "SELECT month, source_key, amount_ore, is_estimate FROM income_entry WHERE year = ?",
                (parsed.year,),
            )
        }
        changes = _compute_changes(old, parsed) if latest is not None else []
        mismatches = [
            {"month": month, "computed_ore": computed, "sheet_ore": sheet}
            for month, computed, sheet in netto_mismatches(parsed)
        ]
        cur = conn.execute(
            """INSERT INTO import_log (kind, filename, sha256, imported_at, year, months,
                   estimate_months_json, warnings_json, mismatches_json, changes_json)
               VALUES ('income', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                filename,
                sha256,
                now.isoformat(timespec="seconds"),
                parsed.year,
                len(parsed.months),
                json.dumps([m.month for m in parsed.months if m.is_estimate]),
                json.dumps(parsed.warnings, ensure_ascii=False),
                json.dumps(mismatches),
                json.dumps(changes),
            ),
        )
        import_id = cur.lastrowid
        conn.execute("DELETE FROM income_entry WHERE year = ?", (parsed.year,))
        _insert_entries(conn, parsed, import_id)
    return ImportOutcome(import_id=import_id, identical=False)


def load_year(conn: sqlite3.Connection, year: int) -> list[MonthRow]:
    rows: dict[int, MonthRow] = {}
    for r in conn.execute(
        "SELECT month, source_key, amount_ore, is_estimate FROM income_entry WHERE year = ? ORDER BY month",
        (year,),
    ):
        row = rows.setdefault(r["month"], MonthRow(r["month"], {}, bool(r["is_estimate"])))
        row.amounts[r["source_key"]] = r["amount_ore"]
    return list(rows.values())


def years(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute("SELECT DISTINCT year FROM income_entry ORDER BY year DESC")]


def has_imports(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM import_log LIMIT 1").fetchone() is not None


def list_imports(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    return [
        {
            "id": r["id"],
            "imported_at": r["imported_at"],
            "filename": r["filename"],
            "year": r["year"],
            "months": r["months"],
            "warning_count": len(json.loads(r["warnings_json"])),
        }
        for r in conn.execute("SELECT * FROM import_log ORDER BY id DESC LIMIT ?", (limit,))
    ]


def get_import(conn: sqlite3.Connection, import_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM import_log WHERE id = ?", (import_id,)).fetchone()
    if r is None:
        return None
    first = conn.execute(
        "SELECT 1 FROM import_log WHERE kind = ? AND year = ? AND id < ? LIMIT 1",
        (r["kind"], r["year"], r["id"]),
    ).fetchone() is None
    return {
        "id": r["id"],
        "filename": r["filename"],
        "sha256": r["sha256"],
        "imported_at": r["imported_at"],
        "year": r["year"],
        "months": r["months"],
        "first_for_year": first,
        "estimate_months": json.loads(r["estimate_months_json"]),
        "warnings": json.loads(r["warnings_json"]),
        "mismatches": json.loads(r["mismatches_json"]),
        "changes": json.loads(r["changes_json"]),
    }

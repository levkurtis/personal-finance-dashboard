from datetime import date, datetime

import pytest

from finance import store
from finance.db import connect, init_schema
from finance.importers.income import parse_income_workbook
from finance.income import year_summary
from helpers import make_income_xlsx

NOW = datetime(2026, 9, 28, 12, 0)
HEADERS = ["Total Income (Netto)", "Salary (Brutto)", "Salary (Netto)", "Interest"]


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "sub" / "test.db")
    init_schema(c)
    yield c
    c.close()


def _parsed(rows, year="2026", today=date(2026, 9, 15)):
    return parse_income_workbook(make_income_xlsx(year, HEADERS, rows), "x.xlsx", today)


def _count(conn, sql):
    return conn.execute(sql).fetchone()[0]


def test_init_schema_is_idempotent_and_seeds_sources(conn):
    init_schema(conn)
    assert _count(conn, "SELECT COUNT(*) FROM income_source") == 9
    assert _count(conn, "SELECT in_netto FROM income_source WHERE key = 'pension'") == 0


def test_reimport_replaces_year_without_double_counting(conn):
    first = _parsed([["January", 300, 500, 300, None], ["February", 300, 500, 300, None]])
    out1 = store.save_income_import(conn, first, "a.xlsx", "sha-a", NOW)
    assert not out1.identical
    assert store.get_import(conn, out1.import_id)["first_for_year"] is True
    assert store.get_import(conn, out1.import_id)["changes"] == []

    second = _parsed([["January", 310, 500, 300, 10], ["February", 300, 500, 300, None]])
    out2 = store.save_income_import(conn, second, "b.xlsx", "sha-b", NOW)

    s = year_summary(store.load_year(conn, 2026), goal_ore=0)
    assert s.total_all.netto == 310_00 + 300_00  # only the second import
    assert _count(conn, "SELECT COUNT(*) FROM income_entry") == 2 * 3
    assert _count(conn, f"SELECT COUNT(*) FROM income_entry WHERE import_id != {out2.import_id}") == 0

    info = store.get_import(conn, out2.import_id)
    assert info["first_for_year"] is False
    assert info["changes"] == [{"month": 1, "source": "interest", "old_ore": 0, "new_ore": 10_00}]


def test_changes_include_estimate_flips_and_removed_months(conn):
    store.save_income_import(
        conn, _parsed([["September", 1, 1, 1, 0], ["October", 1, 1, 1, 0]], today=date(2026, 9, 1)),
        "a.xlsx", "a", NOW,
    )
    out = store.save_income_import(
        conn, _parsed([["October", 1, 1, 1, 0]], today=date(2026, 10, 1)), "b.xlsx", "b", NOW
    )
    changes = store.get_import(conn, out.import_id)["changes"]
    assert {"month": 10, "estimate_to_actual": True} in changes
    assert {"month": 9, "source": "salary_brutto", "old_ore": 100, "new_ore": 0} in changes


def test_identical_upload_writes_nothing(conn):
    parsed = _parsed([["January", 1, 1, 1, 0]])
    out1 = store.save_income_import(conn, parsed, "a.xlsx", "same", NOW)
    out2 = store.save_income_import(conn, parsed, "a.xlsx", "same", NOW)
    assert out2.identical and out2.import_id == out1.import_id
    assert _count(conn, "SELECT COUNT(*) FROM import_log") == 1


def test_failure_mid_transaction_keeps_previous_data(conn, monkeypatch):
    store.save_income_import(conn, _parsed([["January", 1, 1, 1, 0]]), "a.xlsx", "a", NOW)
    before = [tuple(r) for r in conn.execute("SELECT * FROM income_entry ORDER BY month, source_key")]

    def boom(conn, parsed, import_id):
        conn.execute(
            "INSERT INTO income_entry VALUES (2026, 5, 'interest', 1, 0, ?)", (import_id,)
        )
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(store, "_insert_entries", boom)
    with pytest.raises(RuntimeError):
        store.save_income_import(conn, _parsed([["January", 9, 9, 9, 0]]), "b.xlsx", "b", NOW)

    after = [tuple(r) for r in conn.execute("SELECT * FROM income_entry ORDER BY month, source_key")]
    assert after == before
    assert _count(conn, "SELECT COUNT(*) FROM import_log") == 1


def test_years_are_independent(conn):
    store.save_income_import(conn, _parsed([["January", 1, 1, 1, 0]], year="2025"), "a.xlsx", "a", NOW)
    store.save_income_import(conn, _parsed([["January", 2, 2, 2, 0]]), "b.xlsx", "b", NOW)
    store.save_income_import(conn, _parsed([["January", 3, 3, 3, 0]]), "c.xlsx", "c", NOW)
    assert store.years(conn) == [2026, 2025]
    assert store.load_year(conn, 2025)[0].amounts["salary_netto"] == 100
    assert store.load_year(conn, 2026)[0].amounts["salary_netto"] == 300


def test_log_details(conn):
    parsed = _parsed([["January", 999, 1, 1, 0], ["December", 1, 1, 1, 0]])
    out = store.save_income_import(conn, parsed, "Financial 2026.xlsx", "abc", NOW)
    info = store.get_import(conn, out.import_id)
    assert info["months"] == 2
    assert info["estimate_months"] == [12]
    assert info["mismatches"] == [{"month": 1, "computed_ore": 100, "sheet_ore": 99_900}]
    assert any("Months missing" in w for w in info["warnings"])
    assert info["imported_at"] == "2026-09-28T12:00:00"
    listed = store.list_imports(conn)
    assert listed[0]["id"] == out.import_id and listed[0]["warning_count"] == len(info["warnings"])
    assert store.get_import(conn, 12345) is None
    assert store.has_imports(conn)

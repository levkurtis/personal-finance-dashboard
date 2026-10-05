from datetime import date

import pytest

from finance.demo import build_demo_workbook, workbook_to_bytes
from finance.importers.income import IncomeImportError, is_estimate, parse_income_workbook
from helpers import make_income_xlsx

TODAY = date(2026, 9, 15)


def parse(data, filename="Financial 2026.xlsx", today=TODAY):
    return parse_income_workbook(data, filename, today)


def by_month(parsed):
    return {m.month: m for m in parsed.months}


# --- Demo workbook: full round trip ------------------------------------------------------


def test_demo_workbook_parses_to_expected():
    wb, expected = build_demo_workbook(2026, seed=3)
    parsed = parse(workbook_to_bytes(wb))
    assert parsed.year == 2026
    assert [m.month for m in parsed.months] == list(range(1, 13))
    for m in parsed.months:
        assert m.amounts == expected["months"][m.month]
        assert m.sheet_netto == expected["sheet_netto"][m.month]
    assert "income_avg" not in parsed.sources
    assert set(parsed.sources) == set(expected["months"][1])
    assert parsed.warnings == []


def test_estimate_flags_from_today():
    wb, _ = build_demo_workbook(2026)
    parsed = parse(workbook_to_bytes(wb), today=date(2026, 9, 15))
    assert [m.month for m in parsed.months if m.is_estimate] == [10, 11, 12]


@pytest.mark.parametrize(
    "year, month, today, expected",
    [
        (2026, 9, date(2026, 9, 1), False),  # current month is actual
        (2026, 10, date(2026, 9, 30), True),
        (2025, 12, date(2026, 1, 5), False),  # past year: all actual
        (2027, 1, date(2026, 12, 31), True),  # future year: all estimate
    ],
)
def test_is_estimate(year, month, today, expected):
    assert is_estimate(year, month, today) is expected


# --- Headers ------------------------------------------------------------------------------


def test_headers_matched_by_name_in_any_order_with_spaces():
    data = make_income_xlsx(
        "2026",
        ["Interest ", "salary (brutto)", "Salary (Netto)"],
        [["January ", 12.5, 50000, 30000]],
    )
    m = parse(data).months[0]
    assert m.amounts == {"interest": 1250, "salary_brutto": 5_000_000, "salary_netto": 3_000_000}


def test_unknown_header_warns_and_is_ignored():
    data = make_income_xlsx("2026", ["Salary (Netto)", "Overtime"], [["January", 100, 999]])
    parsed = parse(data)
    assert parsed.months[0].amounts == {"salary_netto": 10000}
    assert any('Unknown column "Overtime"' in w for w in parsed.warnings)


def test_missing_pension_column_is_fine():
    data = make_income_xlsx("2026", ["Salary (Brutto)", "Salary (Netto)"], [["January", 100, 60]])
    parsed = parse(data)
    assert "pension" not in parsed.sources
    assert "pension" not in parsed.months[0].amounts


def test_income_avg_ignored_without_warning():
    data = make_income_xlsx(
        "2026", ["Total Income (Netto)", "Salary (Netto)", "Income avg."], [["January", 100, 100, 7]]
    )
    parsed = parse(data)
    assert parsed.sources == ["salary_netto"]
    assert not any("column" in w.casefold() for w in parsed.warnings)


def test_blank_header_with_values_warns():
    data = make_income_xlsx("2026", ["Salary (Netto)", None], [["January", 100, 5]])
    assert any("Column C has values but no header" in w for w in parse(data).warnings)


def test_duplicate_source_header_is_fatal():
    data = make_income_xlsx("2026", ["Stock program", "stock program "], [["January", 1, 2]])
    with pytest.raises(IncomeImportError, match="twice"):
        parse(data)


def test_no_known_columns_is_fatal():
    data = make_income_xlsx("2026", ["Foo", "Bar"], [["January", 1, 2]])
    with pytest.raises(IncomeImportError, match="No known income columns"):
        parse(data)


# --- Cells --------------------------------------------------------------------------------


def test_blank_cells_are_zero():
    data = make_income_xlsx("2026", ["Salary (Netto)", "Stock program"], [["January", 100, None]])
    assert parse(data).months[0].amounts == {"salary_netto": 10000, "stock_program": 0}


def test_text_cell_warns_and_counts_as_zero_without_leaking_amounts():
    data = make_income_xlsx("2026", ["Salary (Netto)", "Stock program"], [["January", 12345, "#REF!"]])
    parsed = parse(data)
    assert parsed.months[0].amounts["stock_program"] == 0
    assert any("Cell C2 is not a number" in w for w in parsed.warnings)
    assert not any("12345" in w or "123" in w for w in parsed.warnings)


def test_negative_values_kept():
    data = make_income_xlsx("2026", ["Tax"], [["April", -875.5]])
    assert parse(data).months[0].amounts == {"tax": -87550}


def test_sheet_netto_blank_warns_once():
    data = make_income_xlsx(
        "2026", ["Total Income (Netto)", "Salary (Netto)"], [["January", None, 1], ["February", None, 1]]
    )
    parsed = parse(data)
    assert all(m.sheet_netto is None for m in parsed.months)
    assert sum("unavailable for 2 month(s)" in w for w in parsed.warnings) == 1


# --- Rows ---------------------------------------------------------------------------------


def test_total_and_blank_rows_skipped():
    data = make_income_xlsx(
        "2026", ["Salary (Netto)"], [["January", 1], [None, None], ["Total", 1], ["TOTAL ", 1]]
    )
    parsed = parse(data)
    assert [m.month for m in parsed.months] == [1]
    assert not any("Row" in w for w in parsed.warnings)


def test_non_month_label_warns():
    data = make_income_xlsx("2026", ["Salary (Netto)"], [["January", 1], ["Notes", 5]])
    assert any('Row 3 ("notes") is not a month' in w for w in parse(data).warnings)


def test_missing_months_warn():
    data = make_income_xlsx("2026", ["Salary (Netto)"], [["January", 1], ["March", 1]])
    parsed = parse(data)
    assert any("Months missing" in w and "February" in w and "December" in w for w in parsed.warnings)


def test_duplicate_month_is_fatal():
    data = make_income_xlsx("2026", ["Salary (Netto)"], [["January", 1], ["january ", 2]])
    with pytest.raises(IncomeImportError, match="twice"):
        parse(data)


# --- Workbook / year ----------------------------------------------------------------------


def test_income_sheet_found_among_others_case_insensitive():
    data = make_income_xlsx("2026", ["Salary (Netto)"], [["January", 1]], sheet_name="income ",
                            extra_sheets=["Expenses"])
    assert parse(data).year == 2026


def test_no_income_sheet_is_fatal():
    data = make_income_xlsx("2026", ["Salary (Netto)"], [["January", 1]], sheet_name="Expenses")
    with pytest.raises(IncomeImportError, match='no "Income" sheet'):
        parse(data)


@pytest.mark.parametrize("year_cell", [2026, "2026", " 2026 ", 2026.0])
def test_year_as_text_or_number(year_cell):
    data = make_income_xlsx(year_cell, ["Salary (Netto)"], [["January", 1]])
    assert parse(data).year == 2026


@pytest.mark.parametrize("year_cell", [None, "Income", "26", 1999, "2026x"])
def test_bad_year_is_fatal(year_cell):
    data = make_income_xlsx(year_cell, ["Salary (Netto)"], [["January", 1]])
    with pytest.raises(IncomeImportError, match="A1"):
        parse(data)


def test_filename_year_mismatch_warns():
    data = make_income_xlsx("2026", ["Salary (Netto)"], [["January", 1]])
    assert any("different year" in w for w in parse(data, filename="Financial 2025.xlsx").warnings)
    assert not any("different year" in w for w in parse(data, filename="export.xlsx").warnings)


@pytest.mark.parametrize("data", [b"", b"not a spreadsheet", b"PK\x03\x04garbage"])
def test_garbage_bytes_are_fatal(data):
    with pytest.raises(IncomeImportError, match="Not a valid .xlsx"):
        parse(data)


def test_past_and_future_year_estimates():
    data = make_income_xlsx("2025", ["Salary (Netto)"], [["December", 1]])
    assert parse(data, filename="x.xlsx").months[0].is_estimate is False
    data = make_income_xlsx("2027", ["Salary (Netto)"], [["January", 1]])
    assert parse(data, filename="x.xlsx").months[0].is_estimate is True


def test_header_aliases_map_personal_header_names():
    data = make_income_xlsx("2026", ["Example Corp Salary (Netto)", "Example Bank"], [["January", 100, 5]])
    aliases = {"salary_netto": ["Example Corp Salary (Netto)"], "bank_benefits": ["Example Bank"]}
    parsed = parse_income_workbook(data, "x.xlsx", TODAY, aliases)
    assert parsed.months[0].amounts == {"salary_netto": 10000, "bank_benefits": 500}
    assert not any("Unknown column" in w for w in parsed.warnings)

    with pytest.raises(IncomeImportError, match="No known income columns"):
        parse(data)  # without aliases both columns are unknown

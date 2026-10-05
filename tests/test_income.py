from finance.importers.income import ParsedIncome, ParsedMonth
from finance.income import MonthRow, netto, netto_mismatches, total_pay, year_summary

GOAL = 1_234_500


def test_netto_excludes_brutto_and_pension_and_includes_negative_tax():
    amounts = {"salary_netto": 30_000_00, "salary_brutto": 50_000_00, "pension": 5_000_00,
               "interest": 100_00, "tax": -1_000_00}
    assert netto(amounts) == 29_100_00


def test_total_pay_is_brutto_plus_pension():
    assert total_pay({"salary_brutto": 50_000_00, "pension": 5_000_00, "salary_netto": 1}) == 55_000_00
    assert total_pay({"salary_brutto": 50_000_00}) == 50_000_00
    assert total_pay({}) == 0


def _parsed(*months):
    return ParsedIncome(year=2026, months=list(months), sources=["salary_netto"])


def test_netto_mismatches_tolerance_boundary():
    parsed = _parsed(
        ParsedMonth(1, {"salary_netto": 1000}, 1005, False),  # diff 5: ok
        ParsedMonth(2, {"salary_netto": 1000}, 1006, False),  # diff 6: mismatch
        ParsedMonth(3, {"salary_netto": 1000}, 994, False),  # diff -6: mismatch
        ParsedMonth(4, {"salary_netto": 1000}, None, False),  # unavailable: skipped
    )
    assert netto_mismatches(parsed) == [(2, 1000, 1006), (3, 1000, 994)]
    assert netto_mismatches(parsed, tolerance_ore=0) == [(1, 1000, 1005), (2, 1000, 1006), (3, 1000, 994)]


def _row(month, brutto, *, est=False, **extra):
    return MonthRow(month, {"salary_brutto": brutto, "pension": 1_000, "salary_netto": 500, **extra}, est)


def test_year_summary_totals_and_average():
    rows = [
        _row(2, 300, tax=-100),
        _row(1, 100),
        _row(3, 999_999, est=True),
    ]
    s = year_summary(rows, GOAL)
    assert [r.month for r in s.rows] == [1, 2, 3]
    assert s.sources == ["salary_netto", "tax", "salary_brutto", "pension"]  # registry order
    assert s.netto_sources == ["salary_netto", "tax"]
    assert s.rows[0].amounts["tax"] == 0  # filled in for months without it
    assert s.rows[1].netto == 400
    assert s.rows[1].total_pay == 1_300

    assert s.actual_months == 2
    assert s.avg_brutto_actual == 200  # estimate month ignored
    assert s.total_actual.brutto == 400
    assert s.total_actual.netto == 900
    assert s.total_all.brutto == 400 + 999_999
    assert s.total_all.pension == 3_000
    assert s.goal_ore == GOAL
    assert s.goal_diff_ore == 200 - GOAL


def test_average_rounds_half_up():
    assert year_summary([_row(1, 100), _row(2, 101)], GOAL).avg_brutto_actual == 101  # 100.5 -> 101


def test_no_actual_months():
    s = year_summary([_row(1, 100, est=True)], GOAL)
    assert s.avg_brutto_actual is None
    assert s.goal_diff_ore is None
    assert s.total_actual.brutto == 0


def test_empty():
    s = year_summary([], GOAL)
    assert s.rows == [] and s.sources == [] and s.avg_brutto_actual is None

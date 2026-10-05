"""Pure income calculations. All amounts are integer øre."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from finance.importers.income import ParsedIncome
from finance.sources import SOURCES, SOURCES_BY_KEY


@dataclass
class MonthRow:
    """One month as stored: amounts per source key."""

    month: int
    amounts: dict[str, int]
    is_estimate: bool


@dataclass
class Figures:
    amounts: dict[str, int]
    netto: int
    brutto: int
    pension: int
    total_pay: int


@dataclass
class SummaryRow(Figures):
    month: int
    is_estimate: bool


@dataclass
class YearSummary:
    sources: list[str]  # keys present in the data, registry (display) order
    rows: list[SummaryRow]
    total_actual: Figures
    total_all: Figures
    actual_months: int
    avg_brutto_actual: int | None
    goal_ore: int
    goal_diff_ore: int | None

    @property
    def netto_sources(self) -> list[str]:
        """The sources that make up netto (brutto and pension get their own columns)."""
        return [k for k in self.sources if SOURCES_BY_KEY[k].in_netto]


def netto(amounts: dict[str, int]) -> int:
    """Sum of every source that counts towards netto (everything except brutto and pension)."""
    return sum(v for k, v in amounts.items() if SOURCES_BY_KEY[k].in_netto)


def total_pay(amounts: dict[str, int]) -> int:
    """Brutto salary + employer pension contribution."""
    return amounts.get("salary_brutto", 0) + amounts.get("pension", 0)


def netto_mismatches(parsed: ParsedIncome, tolerance_ore: int = 5) -> list[tuple[int, int, int]]:
    """(month, computed, sheet) for months where our netto differs from the sheet's column B."""
    out = []
    for m in parsed.months:
        if m.sheet_netto is None:
            continue
        computed = netto(m.amounts)
        if abs(computed - m.sheet_netto) > tolerance_ore:
            out.append((m.month, computed, m.sheet_netto))
    return out


def _figures(amounts: dict[str, int]) -> Figures:
    return Figures(
        amounts=amounts,
        netto=netto(amounts),
        brutto=amounts.get("salary_brutto", 0),
        pension=amounts.get("pension", 0),
        total_pay=total_pay(amounts),
    )


def _sum_amounts(rows: list[MonthRow], keys: list[str]) -> dict[str, int]:
    return {k: sum(r.amounts.get(k, 0) for r in rows) for k in keys}


def _round_div(total: int, n: int) -> int:
    return int((Decimal(total) / n).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def year_summary(rows: list[MonthRow], goal_ore: int) -> YearSummary:
    rows = sorted(rows, key=lambda r: r.month)
    present = {k for r in rows for k in r.amounts}
    sources = [s.key for s in SOURCES if s.key in present]
    actual = [r for r in rows if not r.is_estimate]

    summary_rows = []
    for r in rows:
        f = _figures({k: r.amounts.get(k, 0) for k in sources})
        summary_rows.append(SummaryRow(**vars(f), month=r.month, is_estimate=r.is_estimate))

    avg = _round_div(sum(r.amounts.get("salary_brutto", 0) for r in actual), len(actual)) if actual else None
    return YearSummary(
        sources=sources,
        rows=summary_rows,
        total_actual=_figures(_sum_amounts(actual, sources)),
        total_all=_figures(_sum_amounts(rows, sources)),
        actual_months=len(actual),
        avg_brutto_actual=avg,
        goal_ore=goal_ore,
        goal_diff_ore=None if avg is None else avg - goal_ore,
    )

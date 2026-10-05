"""Parse the "Income" sheet of a "Financial <year>.xlsx" into øre amounts.

Pure: bytes in, ParsedIncome out. No database, no web. Warnings name cells, never amounts.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from finance.money import to_ore
from finance.sources import header_index, is_ignored_header, is_sheet_netto_header, source_for_header

MONTH_NAMES = {
    name: i
    for i, name in enumerate(
        ["january", "february", "march", "april", "may", "june",
         "july", "august", "september", "october", "november", "december"],
        start=1,
    )
}
SHEET_NAME = "income"


class IncomeImportError(Exception):
    """Fatal import problem; the message is shown to the user."""


@dataclass
class ParsedMonth:
    month: int
    amounts: dict[str, int]  # source key -> øre, for every recognised column
    sheet_netto: int | None  # the sheet's own "Total Income (Netto)", if available
    is_estimate: bool


@dataclass
class ParsedIncome:
    year: int
    months: list[ParsedMonth]
    sources: list[str]  # keys of recognised columns present, in sheet order
    warnings: list[str] = field(default_factory=list)


def is_estimate(year: int, month: int, today: date) -> bool:
    """Months after the month of the import are estimates; the current month is actual."""
    if year != today.year:
        return year > today.year
    return month > today.month


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _parse_year(value) -> int:
    text = str(value).strip() if value is not None else ""
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    if not re.fullmatch(r"\d{4}", text) or not 2000 <= int(text) <= 2100:
        raise IncomeImportError("Cell A1 of the Income sheet must contain the year (e.g. 2026).")
    return int(text)


def parse_income_workbook(
    data: bytes, filename: str, today: date, header_aliases: dict[str, list[str]] | None = None
) -> ParsedIncome:
    """`header_aliases` (source key -> extra header names) comes from the local config."""
    index = header_index(header_aliases)  # ValueError on a bad alias, before touching the file
    try:
        wb = load_workbook(BytesIO(data), data_only=True, read_only=True)
    except Exception:
        raise IncomeImportError("Not a valid .xlsx file.") from None
    try:
        return _parse(wb, filename, today, index)
    finally:
        wb.close()


def _parse(wb, filename: str, today: date, index) -> ParsedIncome:
    sheet = next((wb[n] for n in wb.sheetnames if n.strip().casefold() == SHEET_NAME), None)
    if sheet is None:
        raise IncomeImportError('The workbook has no "Income" sheet.')

    rows = [list(r) for r in sheet.iter_rows(values_only=True)]
    if not rows:
        raise IncomeImportError("The Income sheet is empty.")
    warnings: list[str] = []

    year = _parse_year(rows[0][0] if rows[0] else None)
    file_years = {int(y) for y in re.findall(r"(?<!\d)(\d{4})(?!\d)", filename)}
    if file_years and year not in file_years:
        warnings.append(f"The file name suggests a different year than A1 ({year}).")

    # --- Header row: map columns by name, not position.
    source_cols: dict[int, str] = {}  # column index (0-based) -> source key
    netto_col: int | None = None
    blank_cols: list[int] = []
    for idx, header in enumerate(rows[0][1:], start=1):
        letter = get_column_letter(idx + 1)
        if _is_blank(header):
            blank_cols.append(idx)
            continue
        header = str(header)
        if is_ignored_header(header):
            continue
        if is_sheet_netto_header(header):
            if netto_col is not None:
                raise IncomeImportError(f'Column "{header.strip()}" appears twice.')
            netto_col = idx
            continue
        source = source_for_header(header, index)
        if source is None:
            warnings.append(f'Unknown column "{header.strip()}" ({letter}) ignored.')
            continue
        if source.key in source_cols.values():
            raise IncomeImportError(f'Column "{header.strip()}" appears twice.')
        source_cols[idx] = source.key
    if not source_cols:
        raise IncomeImportError("No known income columns found in row 1 of the Income sheet.")

    for idx in blank_cols:
        if any(len(r) > idx and not _is_blank(r[idx]) for r in rows[1:]):
            warnings.append(f"Column {get_column_letter(idx + 1)} has values but no header; ignored.")

    # --- Month rows.
    def cell(row: list, idx: int):
        return row[idx] if idx < len(row) else None

    def amount(row: list, idx: int, row_no: int) -> int | None:
        try:
            return to_ore(cell(row, idx))
        except ValueError:
            warnings.append(f"Cell {get_column_letter(idx + 1)}{row_no} is not a number; treated as 0.")
            return None

    months: dict[int, ParsedMonth] = {}
    for row_no, row in enumerate(rows[1:], start=2):
        label = cell(row, 0)
        label = "" if label is None else str(label).strip().casefold()
        if label == "total":
            continue
        if not label:
            if any(not _is_blank(v) for v in row[1:]):
                warnings.append(f"Row {row_no} has values but no month name; ignored.")
            continue
        month = MONTH_NAMES.get(label)
        if month is None:
            warnings.append(f'Row {row_no} ("{label}") is not a month; ignored.')
            continue
        if month in months:
            raise IncomeImportError(f"Month {label.title()} appears twice (row {row_no}).")

        amounts = {key: amount(row, idx, row_no) or 0 for idx, key in source_cols.items()}
        sheet_netto = None
        if netto_col is not None and not _is_blank(cell(row, netto_col)):
            sheet_netto = amount(row, netto_col, row_no)
        months[month] = ParsedMonth(month, amounts, sheet_netto, is_estimate(year, month, today))

    if not months:
        raise IncomeImportError("No month rows (January–December) found in column A.")
    missing = [m for m in range(1, 13) if m not in months]
    if missing:
        names = ", ".join(n.title() for n, i in MONTH_NAMES.items() if i in missing)
        warnings.append(f"Months missing from the sheet: {names}.")
    unavailable = sum(1 for m in months.values() if m.sheet_netto is None)
    if unavailable:
        warnings.append(
            f"Sheet netto total unavailable for {unavailable} month(s); check skipped for those."
        )

    return ParsedIncome(
        year=year,
        months=[months[m] for m in sorted(months)],
        sources=list(source_cols.values()),
        warnings=warnings,
    )

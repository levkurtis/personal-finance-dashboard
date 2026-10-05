"""Income source registry: the single source of truth for sheet header -> key -> label -> in_netto.

Adding a new income column to the sheet = one new line in SOURCES.
"""

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class IncomeSource:
    key: str
    header: str  # as written in the sheet's header row
    label: str  # shown in the UI
    in_netto: bool  # counts towards "Total Income (Netto)"
    sort: int  # display order


# Order = display order.
SOURCES: tuple[IncomeSource, ...] = (
    IncomeSource("salary_netto", "Salary (Netto)", "Salary (netto)", True, 10),
    IncomeSource("stock_program", "Stock program", "Stock program", True, 20),
    IncomeSource("interest", "Interest", "Interest", True, 30),
    IncomeSource("tax", "Tax", "Tax", True, 40),
    IncomeSource("side_income", "Side income", "Side income", True, 50),
    IncomeSource("stocks_realization", "Stocks Realization", "Stocks realization", True, 60),
    IncomeSource("bank_benefits", "Bank benefits", "Bank benefits", True, 70),
    IncomeSource("salary_brutto", "Salary (Brutto)", "Salary (brutto)", False, 80),
    IncomeSource("pension", "Pension", "Pension", False, 90),
)

SOURCES_BY_KEY: dict[str, IncomeSource] = {s.key: s for s in SOURCES}

# The sheet's own netto total (column B); used only to cross-check our computed netto.
SHEET_NETTO_HEADER = "Total Income (Netto)"
# Columns that are the user's own ad-hoc calculations; never imported.
IGNORED_HEADERS = {"Income avg."}


def normalise_header(s: str) -> str:
    """NFC, strip, collapse internal whitespace, casefold."""
    return " ".join(unicodedata.normalize("NFC", s).split()).casefold()


def header_index(aliases: dict[str, list[str]] | None = None) -> dict[str, IncomeSource]:
    """Normalised header -> source. `aliases` (source key -> extra headers) come from the
    gitignored local config, so personal header names never live in the public code."""
    index = {normalise_header(s.header): s for s in SOURCES}
    reserved = {normalise_header(SHEET_NETTO_HEADER)} | {normalise_header(h) for h in IGNORED_HEADERS}
    for key, headers in (aliases or {}).items():
        source = SOURCES_BY_KEY.get(key)
        if source is None:
            raise ValueError(f'Unknown income source "{key}" in header aliases.')
        for header in headers:
            norm = normalise_header(header)
            if norm in reserved or index.get(norm, source) is not source:
                raise ValueError(f'Header alias "{header}" for "{key}" clashes with another column.')
            index[norm] = source
    return index


_DEFAULT_INDEX = header_index()


def source_for_header(header: str, index: dict[str, IncomeSource] | None = None) -> IncomeSource | None:
    return (_DEFAULT_INDEX if index is None else index).get(normalise_header(header))


def is_sheet_netto_header(header: str) -> bool:
    return normalise_header(header) == normalise_header(SHEET_NETTO_HEADER)


def is_ignored_header(header: str) -> bool:
    return normalise_header(header) in {normalise_header(h) for h in IGNORED_HEADERS}

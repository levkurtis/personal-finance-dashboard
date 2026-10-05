import unicodedata

import pytest

from finance.sources import (
    SOURCES,
    header_index,
    is_ignored_header,
    is_sheet_netto_header,
    normalise_header,
    source_for_header,
)


def test_registry_keys_unique_and_netto_flags():
    keys = [s.key for s in SOURCES]
    assert len(keys) == len(set(keys))
    not_netto = {s.key for s in SOURCES if not s.in_netto}
    assert not_netto == {"salary_brutto", "pension"}


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.key)
def test_every_header_maps_to_its_source(source):
    assert source_for_header(source.header) is source


@pytest.mark.parametrize(
    "header, key",
    [
        ("Salary (Netto) ", "salary_netto"),
        ("  stock program", "stock_program"),
        ("salary (BRUTTO)", "salary_brutto"),
        ("side  INCOME ", "side_income"),
        ("Tax", "tax"),
        ("PENSION", "pension"),
    ],
)
def test_header_matching_is_forgiving(header, key):
    assert source_for_header(header).key == key


@pytest.mark.parametrize("header", ["Income avg.", "Total Income (Netto)", "Overtime", ""])
def test_non_source_headers(header):
    assert source_for_header(header) is None


def test_special_headers():
    assert is_sheet_netto_header(" total income (netto)")
    assert is_ignored_header("income AVG. ")
    assert not is_ignored_header("Interest")


def test_normalise_header():
    assert normalise_header("  Foo \t  Bar ") == "foo bar"


def test_header_aliases_extend_the_index():
    index = header_index({"salary_netto": ["Example Corp Salary (Netto)"], "bank_benefits": ["Example Bank"]})
    assert source_for_header(" example corp salary (NETTO)", index).key == "salary_netto"
    assert source_for_header("Example Bank", index).key == "bank_benefits"
    assert source_for_header("Salary (Netto)", index).key == "salary_netto"  # default still works
    assert source_for_header("Example Bank") is None  # default index has no aliases


def test_alias_matching_is_unicode_normalised():
    index = header_index({"side_income": ["Øvrige indtægter"]})
    assert source_for_header(unicodedata.normalize("NFD", "øvrige  INDTÆGTER "), index).key == "side_income"


@pytest.mark.parametrize(
    "aliases",
    [
        {"nope": ["X"]},  # unknown source key
        {"interest": ["Stock program"]},  # clashes with another source's header
        {"interest": ["Income avg."]},  # clashes with an ignored column
        {"interest": ["Total Income (Netto)"]},  # clashes with the sheet's netto column
    ],
)
def test_bad_header_aliases_rejected(aliases):
    with pytest.raises(ValueError):
        header_index(aliases)

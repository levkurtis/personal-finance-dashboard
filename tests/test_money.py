from decimal import Decimal

import pytest

from finance.money import format_dkk, to_ore


@pytest.mark.parametrize("value", [None, "", "   ", "\xa0"])
def test_blank_is_zero(value):
    assert to_ore(value) == 0


@pytest.mark.parametrize(
    "value, expected",
    [
        (0, 0),
        (55000, 5_500_000),
        (1234.56, 123456),
        (-1234.56, -123456),
        (0.1 + 0.2, 30),
        (0.005, 1),  # half-up
        (-0.005, -1),
        (Decimal("12.345"), 1235),
        ("1.234,56", 123456),
        ("-1.234,56", -123456),
        ("1234,5", 123450),
        ("1234.56", 123456),
        ("55.000,00 kr.", 5_500_000),
        (" 250 kr", 25000),
    ],
)
def test_to_ore(value, expected):
    assert to_ore(value) == expected


@pytest.mark.parametrize("value", ["#REF!", "abc", "1,2,3", "12.34,5,6", True, float("nan"), float("inf"), [1]])
def test_to_ore_rejects_non_amounts(value):
    with pytest.raises(ValueError):
        to_ore(value)


@pytest.mark.parametrize(
    "ore, expected",
    [
        (5_500_000, "55.000,00 kr."),
        (-123456, "-1.234,56 kr."),
        (0, "0,00 kr."),
        (5, "0,05 kr."),
        (-5, "-0,05 kr."),
        (123_456_789_00, "123.456.789,00 kr."),
    ],
)
def test_format_dkk(ore, expected):
    assert format_dkk(ore) == expected

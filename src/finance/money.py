"""Money helpers. Amounts are integer øre everywhere inside the app; convert only at the edges."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_DANISH_NUMBER = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+(,\d+)?$")


def to_ore(value) -> int:
    """Convert a cell value (kroner) to integer øre.

    None, "" and whitespace are 0. Accepts int/float/Decimal and numeric strings in
    Danish ("1.234,56") or plain ("1234.56") format, with an optional "kr."/"kr" suffix.
    Anything else raises ValueError.
    """
    if value is None:
        return 0
    if isinstance(value, bool):
        raise ValueError(f"not an amount: {value!r}")
    if isinstance(value, (int, float, Decimal)):
        amount = Decimal(str(value))
    elif isinstance(value, str):
        text = value.replace("\xa0", " ").strip()
        text = re.sub(r"\s*kr\.?$", "", text, flags=re.IGNORECASE).strip()
        if not text:
            return 0
        if "," in text:
            if not _DANISH_NUMBER.match(text):
                raise ValueError(f"not an amount: {value!r}")
            text = text.replace(".", "").replace(",", ".")
        try:
            amount = Decimal(text)
        except InvalidOperation:
            raise ValueError(f"not an amount: {value!r}") from None
    else:
        raise ValueError(f"not an amount: {value!r}")

    if not amount.is_finite():
        raise ValueError(f"not an amount: {value!r}")
    return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def format_dkk(ore: int) -> str:
    """Format øre in Danish style: 5_500_000 -> "55.000,00 kr."."""
    sign = "-" if ore < 0 else ""
    kroner, rest = divmod(abs(ore), 100)
    return f"{sign}{kroner:,}".replace(",", ".") + f",{rest:02d} kr."

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_CENT = Decimal("0.01")


def q2(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def parse_money(text: str) -> Decimal:
    t = text.strip()
    negative = (t.startswith("(") and t.endswith(")")) or t.startswith("-")
    digits = re.sub(r"[^\d.]", "", t)
    if not digits:
        raise ValueError(f"not a money value: {text!r}")
    try:
        value = Decimal(digits)
    except InvalidOperation as exc:
        raise ValueError(f"not a money value: {text!r}") from exc
    return -value if negative else value

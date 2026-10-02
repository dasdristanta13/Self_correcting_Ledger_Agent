import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_CENT = Decimal("0.01")


def q2(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def parse_money(text: str) -> Decimal:
    t = text.strip().replace("−", "-").replace("–", "-")
    negative = bool(
        re.search(r"\(\s*\D{0,4}\d[\d.,]*\s*\)", t)      # (50.00) or $(50.00)
        or re.search(r"(?<!\w)-\s*\D{0,4}?\d", t)          # -50, $-50, USD -50, -$50
        or re.search(r"\d\s*-\s*$", t)                      # 50.00-
    )
    core = re.sub(r"[^\d.,]", "", t)
    if re.fullmatch(r"\d+,\d{1,2}", core) or re.search(r"\d\.\d{3},\d{1,2}", core):
        raise ValueError(f"ambiguous decimal comma format: {text!r}")
    digits = re.sub(r"[^\d.]", "", t)
    if not digits:
        raise ValueError(f"not a money value: {text!r}")
    try:
        value = Decimal(digits)
    except InvalidOperation as exc:
        raise ValueError(f"not a money value: {text!r}") from exc
    return -value if negative else value

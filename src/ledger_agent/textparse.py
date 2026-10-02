import re
from dataclasses import dataclass
from decimal import Decimal

from ledger_agent.money import parse_money

_LINE = re.compile(
    r"^\s*(?P<label>sub\s*total|discount|shipping|fees?|grand\s+total|total|tax|vat|gst)"
    r"\s*(?:\(\s*(?P<rate>\d+(?:\.\d+)?)\s*%\s*\))?\s*[:\-]?\s*"
    r"(?P<amount>[-(]?\s*[$€£]?\s*[\d,]+\.\d{2}\)?)\s*(?:[A-Z]{3})?\s*$",
    re.IGNORECASE,
)
_FIELD = {
    "subtotal": "subtotal", "discount": "discount", "shipping": "shipping",
    "fee": "fees", "fees": "fees", "grandtotal": "total", "total": "total",
    "tax": "tax", "vat": "tax", "gst": "tax",
}


@dataclass(frozen=True)
class LabeledAmount:
    field: str            # subtotal|discount|shipping|fees|total|tax
    amount: Decimal       # discount is normalised to a positive number
    rate: Decimal | None  # 0.10 for "(10%)"
    raw: str


def parse_labeled_line(line: str) -> LabeledAmount | None:
    m = _LINE.match(line)
    if not m:
        return None
    field = _FIELD[re.sub(r"\s+", "", m.group("label").lower())]
    amount = parse_money(m.group("amount"))
    if field == "discount":
        amount = abs(amount)
    rate = Decimal(m.group("rate")) / 100 if m.group("rate") else None
    return LabeledAmount(field=field, amount=amount, rate=rate, raw=line.strip())


_NUM_COMMA = re.compile(r"(?<=\d),(?=\d)")
_TOKEN = re.compile(r"[a-z0-9_]+(?:\.[a-z0-9_]+)*")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(_NUM_COMMA.sub("", text.lower()))

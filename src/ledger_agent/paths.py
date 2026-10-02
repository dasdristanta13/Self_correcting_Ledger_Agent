import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from ledger_agent.models import Ledger

SCALARS = ("subtotal", "discount", "tax", "shipping", "fees", "total")
_ITEM_ATTRS = ("quantity", "unit_price", "amount")
_TAX_ATTRS = ("amount", "rate")
_COLL = re.compile(r"^(items|tax_lines)\[([^\]]+)\]\.(\w+)$")


class PathError(ValueError):
    pass


class PathRef(BaseModel):
    kind: Literal["item", "tax", "scalar"]
    id: str | None = None
    attr: str


def parse_path(path: str) -> PathRef:
    m = _COLL.match(path)
    if m:
        coll, id_, attr = m.groups()
        allowed = _ITEM_ATTRS if coll == "items" else _TAX_ATTRS
        if attr not in allowed:
            raise PathError(f"unsupported attribute in path: {path!r}")
        return PathRef(kind="item" if coll == "items" else "tax", id=id_, attr=attr)
    if path in SCALARS:
        return PathRef(kind="scalar", attr=path)
    raise PathError(f"unknown field path: {path!r}")


def _find(ledger: Ledger, ref: PathRef):
    coll = ledger.items if ref.kind == "item" else ledger.tax_lines
    for element in coll:
        if element.id == ref.id:
            return element
    raise PathError(f"no such element for path with id {ref.id!r}")


def get_field(ledger: Ledger, path: str) -> Decimal | None:
    ref = parse_path(path)
    if ref.kind == "scalar":
        return getattr(ledger, ref.attr)
    return getattr(_find(ledger, ref), ref.attr)


def set_field(ledger: Ledger, path: str, value: Decimal) -> Ledger:
    ref = parse_path(path)
    new = ledger.model_copy(deep=True)
    if ref.kind == "scalar":
        setattr(new, ref.attr, value)
        return new
    setattr(_find(new, ref), ref.attr, value)
    if ref.kind == "tax" and ref.attr == "amount":
        new.tax = sum((t.amount for t in new.tax_lines), Decimal("0"))
    return new

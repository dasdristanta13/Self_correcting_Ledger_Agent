from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ValidationRules(BaseModel):
    tolerance: Decimal = Decimal("0.01")
    total_terms: dict[str, int] = Field(default_factory=lambda: {
        "subtotal": 1, "discount": -1, "tax": 1, "shipping": 1, "fees": 1,
    })


class Config(BaseModel):
    max_revisions: int = 3
    confidence_threshold: float = 0.90
    top_k: int = 5
    ocr_min_chars: int = 30
    validation: ValidationRules = Field(default_factory=ValidationRules)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        return cls(**(yaml.safe_load(Path(path).read_text()) or {}))

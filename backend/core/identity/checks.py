"""A named check result, shared by every identity-document module."""
from __future__ import annotations

from dataclasses import dataclass, field

PASS, FAIL, REVIEW, NOT_SUPPORTED, UNAVAILABLE, NOT_CHECKED = (
    "PASS", "FAIL", "REVIEW_REQUIRED", "NOT_SUPPORTED", "UNAVAILABLE", "NOT_CHECKED")
_RANK = {NOT_CHECKED: -1, PASS: 0, NOT_SUPPORTED: 1, UNAVAILABLE: 1, REVIEW: 2, FAIL: 3}


def worst(statuses) -> str:
    statuses = list(statuses)
    return max(statuses, key=lambda s: _RANK[s]) if statuses else NOT_CHECKED


@dataclass
class Check:
    category: str     # file_integrity | image_quality | ocr | parsing | data_format | dates | consistency | external
    code: str         # stable identifier, e.g. "mrz.check_digit.birth_date" (Phase 9 turns these into versioned rules)
    name: str         # what a person reads
    status: str
    detail: str
    positions: list = field(default_factory=list)  # [(line, index), ...] for MRZ characters this check covers

    def as_dict(self) -> dict:
        return {"category": self.category, "code": self.code, "name": self.name, "status": self.status,
                "detail": self.detail, "positions": [list(p) for p in self.positions]}

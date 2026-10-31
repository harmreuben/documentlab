"""Collects errors (which block generation) and warnings (which don't), each tied to a field."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Issue:
    field: str
    message: str

    def as_dict(self) -> dict:
        return {"field": self.field, "message": self.message}


@dataclass
class Issues:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    def error(self, field_name: str, message: str) -> None:
        self.errors.append(Issue(field_name, message))

    def warning(self, field_name: str, message: str) -> None:
        self.warnings.append(Issue(field_name, message))

    @property
    def ok(self) -> bool:
        return not self.errors

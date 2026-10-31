"""Neutral payload schemas for QR and PDF417 test barcodes.

These are DocumentLab's own documented layouts for assets, shipments and test fixtures.
None of them describe a person or follow a government document layout. A structured
payload is encoded as compact JSON with the schema identifier first, for example:

    {"schema":"documentlab.asset-tag.v1","asset_id":"TEST-0042","name":"Bench scanner"}
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

from .issues import Issues

TEXT_SCHEMA = "documentlab.text.v1"


@dataclass(frozen=True)
class SchemaField:
    name: str
    label: str
    kind: str = "text"  # text | integer | number | date | choice
    required: bool = False
    max_length: int = 64
    pattern: str | None = None
    pattern_hint: str = ""
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    help: str = ""

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "", ())}


@dataclass(frozen=True)
class PayloadSchema:
    id: str
    name: str
    description: str
    fields: tuple[SchemaField, ...] = field(default_factory=tuple)

    @property
    def structured(self) -> bool:
        return self.id != TEXT_SCHEMA

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description,
                "structured": self.structured, "fields": [f.as_dict() for f in self.fields]}


_CODE = r"^[A-Z0-9][A-Z0-9-]{1,31}$"
_CODE_HINT = "2–32 capitals, digits or hyphens"

SCHEMAS: dict[str, PayloadSchema] = {s.id: s for s in [
    PayloadSchema(TEXT_SCHEMA, "Plain text", "Encodes exactly the text you enter."),
    PayloadSchema("documentlab.asset-tag.v1", "Asset tag", "Labels for equipment and stock items.", (
        SchemaField("asset_id", "Asset ID", required=True, max_length=32, pattern=_CODE, pattern_hint=_CODE_HINT),
        SchemaField("name", "Item name", required=True, max_length=60),
        SchemaField("location", "Location", max_length=60),
        SchemaField("acquired", "Date acquired", kind="date"),
    )),
    PayloadSchema("documentlab.shipment-label.v1", "Shipment label", "Parcel and pallet reference labels.", (
        SchemaField("shipment_ref", "Shipment reference", required=True, max_length=32, pattern=_CODE, pattern_hint=_CODE_HINT),
        SchemaField("origin", "Origin depot", required=True, max_length=40),
        SchemaField("destination", "Destination depot", required=True, max_length=40),
        SchemaField("pieces", "Pieces", kind="integer", required=True, minimum=1, maximum=9999),
        SchemaField("weight_kg", "Weight (kg)", kind="number", minimum=0, maximum=100000),
    )),
    PayloadSchema("documentlab.test-fixture.v1", "Test fixture", "Labels test inputs for the Testing Laboratory.", (
        SchemaField("test_id", "Test ID", required=True, max_length=32, pattern=_CODE, pattern_hint=_CODE_HINT),
        SchemaField("description", "Description", required=True, max_length=120),
        SchemaField("expected_result", "Expected result", kind="choice", required=True,
                    choices=("PASS", "FAIL", "REVIEW_REQUIRED")),
        SchemaField("notes", "Notes", max_length=200),
    )),
]}


def get_schema(schema_id: str) -> PayloadSchema | None:
    return SCHEMAS.get(schema_id)


def build_payload(schema: PayloadSchema, values: dict, issues: Issues) -> str:
    """Validate field values and return the encoded JSON text. Errors go into `issues`."""
    out: dict[str, object] = {"schema": schema.id}
    known = {f.name for f in schema.fields}
    for extra in sorted(set(values) - known):
        issues.error(extra, f"'{extra}' is not part of the {schema.name} schema.")

    for f in schema.fields:
        raw = values.get(f.name, "")
        raw = "" if raw is None else str(raw).strip()
        if raw == "":
            if f.required:
                issues.error(f.name, f"{f.label} is required.")
            continue
        if len(raw) > f.max_length:
            issues.error(f.name, f"{f.label} can be at most {f.max_length} characters.")
            continue
        value: object = raw
        if f.kind == "integer":
            if not re.fullmatch(r"-?\d+", raw):
                issues.error(f.name, f"{f.label} must be a whole number.")
                continue
            value = int(raw)
        elif f.kind == "number":
            try:
                value = float(raw)
            except ValueError:
                issues.error(f.name, f"{f.label} must be a number.")
                continue
            if value != value or value in (float("inf"), float("-inf")):  # NaN or infinity
                issues.error(f.name, f"{f.label} must be a number.")
                continue
            value = int(value) if float(value).is_integer() else round(float(value), 3)
        elif f.kind == "date":
            try:
                value = date.fromisoformat(raw).isoformat()
            except ValueError:
                issues.error(f.name, f"{f.label} must be a date written as YYYY-MM-DD.")
                continue
        elif f.kind == "choice" and raw not in f.choices:
            issues.error(f.name, f"{f.label} must be one of: {', '.join(f.choices)}.")
            continue
        if f.pattern and not re.fullmatch(f.pattern, raw):
            issues.error(f.name, f"{f.label} must be {f.pattern_hint}.")
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if f.minimum is not None and value < f.minimum:
                issues.error(f.name, f"{f.label} must be at least {f.minimum:g}.")
                continue
            if f.maximum is not None and value > f.maximum:
                issues.error(f.name, f"{f.label} must be at most {f.maximum:g}.")
                continue
        out[f.name] = value
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))
